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
from __future__ import unicode_literals

import json
from mock import patch

# from django.utils.translation import gettext as _
from django.urls import reverse

from ominicontacto_app.tests.factories import PausaFactory
from ominicontacto_app.tests.utiles import OMLBaseTest
from ominicontacto_app.tests.utiles import PASSWORD
from reportes_app.models import AgentActivityEventV2


class AgentsAsteriskSessionAPITest(OMLBaseTest):

    def setUp(self):
        super(AgentsAsteriskSessionAPITest, self).setUp()
        usr_agente = self.crear_user_agente(username='agente1')
        self.agente = self.crear_agente_profile(usr_agente)
        url = reverse('api_login')
        post_data = {'username': self.agente.user.username, 'password': PASSWORD}
        response = self.client.post(url, post_data)
        self.auth_header = 'Bearer ' + response.json()['token']
        self.pausa = PausaFactory(nombre='pausa')

    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.login_agent')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'disconnect_manager')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'connect_manager')
    def test_asterisk_session_login_ok(self, connect_manager, disconnect_manager, login_agent):
        connect_manager.return_value = False
        disconnect_manager.return_value = False
        login_agent.return_value = False
        url = reverse('api_agent_asterisk_login')
        response = self.client.post(url, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.json())
        self.assertEqual(response.json()['status'], 'OK')
        login_agent.assert_called_once_with(self.agente, manage_connection=True)

    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.login_agent')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'disconnect_manager')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'connect_manager')
    def test_asterisk_session_login_error(self, connect_manager, disconnect_manager, login_agent):
        connect_manager.return_value = False
        disconnect_manager.return_value = False
        login_agent.return_value = True
        url = reverse('api_agent_asterisk_login')
        response = self.client.post(url, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.json())
        self.assertEqual(response.json()['status'], 'ERROR')
        login_agent.assert_called_once_with(self.agente, manage_connection=True)

    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'set_agent_as_ready')
    def test_asterisk_session_ready_ok(self, set_agent_as_ready):
        set_agent_as_ready.return_value = False
        url = reverse('api_agent_asterisk_ready')
        response = self.client.post(url, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.json())
        self.assertEqual(response.json()['status'], 'OK')
        set_agent_as_ready.assert_called_once_with(self.agente)

    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'set_agent_as_ready')
    def test_asterisk_session_ready_error(self, set_agent_as_ready):
        set_agent_as_ready.return_value = True
        url = reverse('api_agent_asterisk_ready')
        response = self.client.post(url, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.json())
        self.assertEqual(response.json()['status'], 'ERROR')
        set_agent_as_ready.assert_called_once_with(self.agente)

    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'logout_agent')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'disconnect_manager')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'connect_manager')
    def test_asterisk_session_logout_ok(self, connect_manager, disconnect_manager, logout_agent):
        connect_manager.return_value = False
        disconnect_manager.return_value = False
        logout_agent.return_value = False, False
        url = reverse('api_agent_asterisk_logout')
        response = self.client.post(url, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.json())
        self.assertEqual(response.json()['status'], 'OK')
        logout_agent.assert_called_once_with(self.agente, manage_connection=True)

    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'logout_agent')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'disconnect_manager')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'connect_manager')
    def test_asterisk_session_logout_error(self, connect_manager, disconnect_manager, logout_agent):
        connect_manager.return_value = False
        disconnect_manager.return_value = False
        logout_agent.return_value = False, True
        url = reverse('api_agent_asterisk_logout')
        response = self.client.post(url, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.json())
        self.assertEqual(response.json()['status'], 'ERROR')
        logout_agent.assert_called_once_with(self.agente, manage_connection=True)

    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'pause_agent')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'disconnect_manager')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'connect_manager')
    def test_asterisk_session_pause_agent(self, connect_manager, disconnect_manager, pause_agent):
        cant_v2 = AgentActivityEventV2.objects.count()
        connect_manager.return_value = False
        disconnect_manager.return_value = False
        pause_agent.return_value = False, False
        url = reverse('api_make_pause')
        response = self.client.post(url, data={'pause_id': self.pausa.id},
                                    HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.json())
        self.assertEqual(response.json()['status'], 'OK')
        pause_agent.assert_called_once_with(self.agente, str(self.pausa.id), manage_connection=True)
        self.assertEqual(AgentActivityEventV2.objects.count(), cant_v2 + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.agente_id, self.agente.id)
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.STATE_PAUSED)
        self.assertEqual(last_event.pause_id, self.pausa.id)

    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           '_set_agent_pause_redis_status')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           '_set_agent_redis_status')
    def test_asterisk_session_login_pause_on_first_login(
            self, set_agent_redis_status, set_agent_pause_redis_status):
        self.agente.grupo.pause_on_first_login = True
        self.agente.grupo.save()
        set_agent_pause_redis_status.return_value = False

        cant_v2 = AgentActivityEventV2.objects.count()
        url = reverse('api_agent_asterisk_login')
        response = self.client.post(url, HTTP_AUTHORIZATION=self.auth_header)

        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.json())
        self.assertEqual(response.json()['status'], 'OK')

        set_agent_redis_status.assert_not_called()
        set_agent_pause_redis_status.assert_called_once_with(self.agente, 'ACW', '0')
        self.assertEqual(AgentActivityEventV2.objects.count(), cant_v2 + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.agente_id, self.agente.id)
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.STATE_ACW)
        self.assertIsNone(last_event.pause_id)

    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'unpause_agent')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'disconnect_manager')
    @patch('ominicontacto_app.services.asterisk.agent_activity.AgentActivityAmiManager.'
           'connect_manager')
    def test_asterisk_session_unpause_agent(self, connect_manager, disconnect_manager,
                                            unpause_agent):
        cant_v2 = AgentActivityEventV2.objects.count()
        connect_manager.return_value = False
        disconnect_manager.return_value = False
        unpause_agent.return_value = False, False
        url = reverse('api_make_unpause')
        response = self.client.post(url, data={'pause_id': self.pausa.id},
                                    HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.json())
        self.assertEqual(response.json()['status'], 'OK')
        unpause_agent.assert_called_once_with(self.agente, str(self.pausa.id),
                                              manage_connection=True)
        self.assertEqual(AgentActivityEventV2.objects.count(), cant_v2 + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.agente_id, self.agente.id)
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.STATE_READY)

    @patch('api_app.views.agente.create_redis_connection')
    def test_presence_heartbeat_ok(self, mock_create_redis):
        redis_mock = mock_create_redis.return_value
        redis_mock.hset.return_value = 1
        redis_mock.expire.return_value = True
        redis_mock.setex.return_value = True

        url = reverse('api_agent_presence_heartbeat')
        payload = {
            'browser_id': 'browser-1',
            'tab_id': 'tab-1',
            'leader': True,
            'ui_state': 'Ready',
            'sent_at_ms': 1735689600000,
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'OK')
        self.assertIn('server_ts_ms', response.json())
        self.assertIn('next_heartbeat_sec', response.json())
        self.assertTrue(redis_mock.hset.called)
        self.assertTrue(redis_mock.expire.called)

    def test_presence_heartbeat_invalid_browser_id(self):
        url = reverse('api_agent_presence_heartbeat')
        payload = {
            'browser_id': 'bad id with spaces',
            'tab_id': 'tab-1',
            'leader': True,
            'ui_state': 'Ready',
            'sent_at_ms': 1735689600000,
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get('status'), 'ERROR')
