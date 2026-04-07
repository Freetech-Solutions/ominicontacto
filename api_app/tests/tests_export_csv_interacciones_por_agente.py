# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

from __future__ import unicode_literals

import json

from django.urls import reverse

from mock import patch

from ominicontacto_app.models import Campana
from ominicontacto_app.tests.factories import CampanaFactory
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class ExportCSVInteraccionesPorAgenteAPITest(OMLBaseTest):
    def setUp(self):
        super(ExportCSVInteraccionesPorAgenteAPITest, self).setUp()
        admin = self.crear_administrador(username='admin_export_interacciones_agente')
        self.client.login(username=admin.username, password=PASSWORD)
        self.url = reverse('api_exportar_csv_interacciones_por_agente')
        self.campana = CampanaFactory.create(estado=Campana.ESTADO_ACTIVA)

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.supervisor.threading.Thread')
    def test_post_valido_devuelve_ok_y_arranca_thread(self, mock_thread, _mock_permission):
        task_id = 'task-interacciones-agente-001'
        response = self.client.post(self.url, data={
            'task_id': task_id,
            'campana_id': self.campana.pk,
            'desde': '01/02/2025',
            'hasta': '01/02/2025',
        })

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode('utf-8'))
        self.assertEqual(body['status'], 'OK')
        self.assertEqual(body['id'], task_id)

        self.assertTrue(mock_thread.called)
        thread_kwargs = mock_thread.call_args[1]
        thread_args = thread_kwargs.get('args')

        self.assertEqual(
            thread_args[0],
            'OML:STATUS_CSV_REPORT:INTERACCIONES_POR_AGENTE:cc:{0}'.format(task_id),
        )
        self.assertEqual(thread_args[1], self.campana)
        self.assertTrue(callable(thread_kwargs.get('target')))
        mock_thread.return_value.start.assert_called_once_with()
