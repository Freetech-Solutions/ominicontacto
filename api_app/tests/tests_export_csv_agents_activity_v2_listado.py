# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

from __future__ import unicode_literals

import json

from django.urls import reverse

from mock import patch

from ominicontacto_app.models import Campana
from ominicontacto_app.tests.factories import (
    AgenteProfileFactory,
    CampanaFactory,
    GrupoFactory,
    QueueFactory,
    QueueMemberFactory,
)
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class ExportCSVAgentsActivityV2ListadoAPITest(OMLBaseTest):
    def setUp(self):
        super(ExportCSVAgentsActivityV2ListadoAPITest, self).setUp()
        admin = self.crear_administrador(username='admin_export_agents_activity_v2')
        self.client.login(username=admin.username, password=PASSWORD)
        self.url = reverse('api_exportar_csv_agents_activity_v2_listado')

        self.group_visible_a = GrupoFactory.create(nombre='grp_visible_a')
        self.group_visible_b = GrupoFactory.create(nombre='grp_visible_b')
        self.group_hidden = GrupoFactory.create(nombre='grp_hidden')

        self.agent_visible_a = AgenteProfileFactory.create(grupo=self.group_visible_a)
        self.agent_visible_b = AgenteProfileFactory.create(grupo=self.group_visible_b)
        self.agent_hidden = AgenteProfileFactory.create(grupo=self.group_hidden)

        self.campana_visible = CampanaFactory.create(estado=Campana.ESTADO_ACTIVA)
        self.queue_visible = QueueFactory.create(campana=self.campana_visible)

        QueueMemberFactory.create(member=self.agent_visible_a, queue_name=self.queue_visible)
        QueueMemberFactory.create(member=self.agent_visible_b, queue_name=self.queue_visible)

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
        )

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2.threading.Thread')
    def test_post_valido_devuelve_ok_y_arranca_thread(self, mock_thread, _mock_permission):
        task_id = 'task-valid-001'
        response = self._post({
            'task_id': task_id,
            'desde': '01/02/2025',
            'hasta': '01/02/2025',
            'agente': ['__all_agents__'],
            'grupo_agente': ['__all_groups__'],
        })

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode('utf-8'))
        self.assertEqual(body['status'], 'OK')
        self.assertEqual(body['id'], task_id)

        self.assertTrue(mock_thread.called)
        thread_kwargs = mock_thread.call_args[1].get('kwargs')
        self.assertEqual(
            thread_kwargs.get('key_task'),
            'OML:STATUS_CSV_REPORT:AGENTS_ACTIVITY_LISTADO:cc:{0}'.format(task_id),
        )
        self.assertEqual(thread_kwargs.get('task_id'), task_id)
        self.assertEqual(
            thread_kwargs.get('allowed_agent_ids'),
            sorted([self.agent_visible_a.id, self.agent_visible_b.id]),
        )
        mock_thread.return_value.start.assert_called_once_with()

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    def test_falta_task_id_retorna_400(self, _mock_permission):
        response = self._post({
            'desde': '01/02/2025',
            'hasta': '01/02/2025',
            'agente': ['__all_agents__'],
            'grupo_agente': ['__all_groups__'],
        })
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content.decode('utf-8'))
        self.assertIn('task_id', body.get('error', ''))

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    def test_rango_mayor_a_31_dias_retorna_400(self, _mock_permission):
        response = self._post({
            'task_id': 'task-range-001',
            'desde': '01/01/2025',
            'hasta': '10/02/2025',
            'agente': ['__all_agents__'],
            'grupo_agente': ['__all_groups__'],
        })
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content.decode('utf-8'))
        self.assertIn('31', body.get('error', ''))

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    def test_agente_fuera_de_visibilidad_retorna_400(self, _mock_permission):
        response = self._post({
            'task_id': 'task-invalid-agent-001',
            'desde': '01/02/2025',
            'hasta': '01/02/2025',
            'agente': [str(self.agent_hidden.id)],
            'grupo_agente': ['__all_groups__'],
        })
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content.decode('utf-8'))
        self.assertIn('Agente', body.get('error', ''))

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2.threading.Thread')
    def test_filtro_agente_y_grupo_aplica_interseccion(self, mock_thread, _mock_permission):
        response = self._post({
            'task_id': 'task-intersection-001',
            'desde': '01/02/2025',
            'hasta': '01/02/2025',
            'agente': [str(self.agent_visible_b.id)],
            'grupo_agente': [str(self.group_visible_a.id)],
        })
        self.assertEqual(response.status_code, 200)
        thread_kwargs = mock_thread.call_args[1].get('kwargs')
        self.assertEqual(thread_kwargs.get('allowed_agent_ids'), [])
