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
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from ominicontacto_app.tests.utiles import OMLBaseTest

SECRET = 'internal-test-secret'


@override_settings(OML_INTERNAL_SECRET=SECRET)
class NotifyAttendedMultinumCallTest(OMLBaseTest):

    def setUp(self):
        super(NotifyAttendedMultinumCallTest, self).setUp()
        self.url = reverse('api_notify_attended_multinum_call')
        self.agente = self.crear_agente_profile()
        self.data = {'agent_id': self.agente.id, 'phone': '351111111'}

    def _post(self, data=None, secret=None):
        headers = {}
        if secret is not None:
            headers['HTTP_X_OML_INTERNAL_SECRET'] = secret
        return self.client.post(self.url, data or self.data, **headers)

    @patch('api_app.views.system.AgentNotifier')
    def test_sin_header_devuelve_401(self, notifier):
        response = self._post()
        self.assertEqual(response.status_code, 401)
        notifier.assert_not_called()

    @patch('api_app.views.system.AgentNotifier')
    def test_secret_incorrecto_devuelve_401(self, notifier):
        response = self._post(secret='otro')
        self.assertEqual(response.status_code, 401)
        notifier.assert_not_called()

    @patch('api_app.views.system.AgentNotifier')
    def test_secret_vacio_devuelve_401(self, notifier):
        response = self._post(secret='')
        self.assertEqual(response.status_code, 401)
        notifier.assert_not_called()

    @override_settings(OML_INTERNAL_SECRET='')
    @patch('api_app.views.system.AgentNotifier')
    def test_secret_no_configurado_devuelve_401(self, notifier):
        response = self._post(secret='')
        self.assertEqual(response.status_code, 401)
        notifier.assert_not_called()

    @patch('api_app.views.system.AgentNotifier')
    def test_secret_correcto_notifica_al_agente(self, notifier):
        response = self._post(secret=SECRET)
        self.assertEqual(response.status_code, 200)
        notifier.return_value.notify_attended_multinum_call.assert_called_once_with(
            self.agente.user_id, '351111111')

    @patch('api_app.views.system.AgentNotifier')
    def test_agente_inexistente_devuelve_400(self, notifier):
        response = self._post(data={'agent_id': 999999, 'phone': '1'}, secret=SECRET)
        self.assertEqual(response.status_code, 400)
        notifier.assert_not_called()
