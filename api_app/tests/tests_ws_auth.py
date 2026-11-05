# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

# This file is part of OMniLeads

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone

from ominicontacto_app.models import User
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class WsAuthTest(OMLBaseTest):

    def setUp(self):
        super(WsAuthTest, self).setUp()
        self.url = reverse('api_ws_auth')
        self.admin = self.crear_administrador()
        self.supervisor = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.otro_supervisor = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.agente = self.crear_agente_profile()
        self.otro_agente = self.crear_agente_profile()
        self.campana = self.crear_campana_manual(user=self.supervisor.user)

    def _login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def _get(self, path):
        return self.client.get(self.url, HTTP_X_ORIGINAL_URI=path)

    def assertStatus(self, path, status):
        self.assertEqual(self._get(path).status_code, status, path)

    def test_sin_sesion_devuelve_401(self):
        self.assertStatus(
            '/consumers/stream/supervisor/{0}/agentes'.format(self.supervisor.id), 401)

    def test_path_fuera_de_allowlist_devuelve_403(self):
        self._login(self.admin)
        for path in ('', '/consumers/stream/asterisk_conf_updater',
                     '/consumers/stream/whatsapp_webhook_meta_1',
                     '/consumers/stream/supervisor_1_agentes',
                     '/consumers/stream/supervisor/1/agentes/../../asterisk_conf_updater',
                     '/consumers/reporte_grafico_campana/grabaciones/1/abc'):
            self.assertStatus(path, 403)

    def test_path_fuera_de_allowlist_sin_sesion_devuelve_403(self):
        self.assertStatus('/consumers/stream/asterisk_conf_updater', 403)

    def test_stream_supervisor(self):
        self._login(self.supervisor.user)
        for stream in ('agentes', 'entrantes', 'salientes', 'dialers'):
            self.assertStatus(
                '/consumers/stream/supervisor/{0}/{1}'.format(self.supervisor.id, stream), 204)
        self.assertStatus(
            '/consumers/stream/supervisor/{0}/agentes/'.format(self.supervisor.id), 204)
        self.assertStatus(
            '/consumers/stream/supervisor/{0}/agentes'.format(self.otro_supervisor.id), 403)

    def test_stream_supervisor_agente_devuelve_403(self):
        self._login(self.agente.user)
        self.assertStatus(
            '/consumers/stream/supervisor/{0}/agentes'.format(self.supervisor.id), 403)

    def test_stream_dashboard(self):
        paths = ('/consumers/stream/auth_event_2026-11-04',
                 '/consumers/stream/calification_event_2026-11-03')
        self._login(self.supervisor.user)
        for path in paths:
            self.assertStatus(path, 204)
        self._login(self.agente.user)
        for path in paths:
            self.assertStatus(path, 403)

    def test_stream_acd_nunca_por_sesion(self):
        self._login(self.admin)
        self.assertStatus('/consumers/stream/asterisk/conf/updater', 403)

    def test_pubsub_reporte_agente(self):
        path = '/consumers/reporte_agente/estadisticas_dia_actual/{0}/dashboard1'
        self._login(self.agente.user)
        self.assertStatus(path.format(self.agente.id), 204)
        self.assertStatus(path.format(self.otro_agente.id), 403)

    def test_pubsub_campana(self):
        paths = (
            '/consumers/reporte_grafico_campana/contactados/{0}/abcd1234',
            '/consumers/reporte_grafico_campana/calificados/{0}/abcd1234',
            '/consumers/reporte_grafico_campana/no_atendidos/{0}/abcd1234',
            '/consumers/reporte_grafico_campana/formulario_gestion/{0}/abcd1234',
            '/consumers/reporte_resultados_de_base_campana/'
            'resultados_de_base_contactados/{0}/abcd1234',
            '/consumers/reporte_resultados_de_base_campana/'
            'resultados_de_base_contactados_todos/{0}/abcd1234',
        )
        for user, status in ((self.supervisor.user, 204), (self.admin, 204),
                             (self.otro_supervisor.user, 403), (self.agente.user, 403)):
            self._login(user)
            for path in paths:
                self.assertStatus(path.format(self.campana.id), status)

    def test_pubsub_descargas_por_usuario(self):
        paths = ('/consumers/genera_csv_auditoria/calificados/{0}/csv',
                 '/consumers/genera_zip_grabaciones/grabaciones/{0}/zip')
        self._login(self.supervisor.user)
        for path in paths:
            self.assertStatus(path.format(self.supervisor.user.id), 204)
            self.assertStatus(path.format(self.otro_supervisor.user.id), 403)

    def test_ws_auth_no_renueva_la_sesion(self):
        self._login(self.supervisor.user)
        session_key = self.client.session.session_key
        expire_date = timezone.now() + timedelta(seconds=60)
        Session.objects.filter(session_key=session_key).update(expire_date=expire_date)

        self.assertStatus(
            '/consumers/stream/supervisor/{0}/agentes'.format(self.supervisor.id), 204)
        session = Session.objects.get(session_key=session_key)
        self.assertEqual(session.expire_date, expire_date)

        # Cualquier otra vista si renueva la sesion (SESSION_SAVE_EVERY_REQUEST)
        self.client.get('/')
        session = Session.objects.get(session_key=session_key)
        self.assertGreater(session.expire_date, expire_date)
