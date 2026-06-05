# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from mock import patch, MagicMock

from django.urls import reverse
from rest_framework import status

from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD
from ominicontacto_app.models import User


class VoicebotSupervisionApiTest(OMLBaseTest):

    def setUp(self):
        super(VoicebotSupervisionApiTest, self).setUp()
        usr_supervisor = self.crear_user_supervisor(username='sup_voicebot')
        self.supervisor = self.crear_supervisor_profile(user=usr_supervisor, rol=User.SUPERVISOR)
        self.client.login(username=usr_supervisor.username, password=PASSWORD)

        self.agent_id = 11
        self.call_id = '1780600599.140'
        self.node_id = 'acd-node-test'
        self.voicebot_payload = json.dumps({
            'call_id': self.call_id,
            'node_id': self.node_id,
            'status': 'ONCALL',
            'bridge_id': 'bridge-1',
            'campaign_id': '20',
            'contact_number': '5551234',
        })

    @patch('api_app.views.transfer._get_redis_client')
    def test_spy_with_call_id_uses_voicebot_hash(self, mock_redis_client):
        redis_conn = MagicMock()
        mock_redis_client.return_value = redis_conn
        redis_conn.hget.return_value = self.voicebot_payload
        redis_conn.publish.return_value = 1

        url = reverse('api_call_spy')
        response = self.client.post(url, {
            'supervisor_id': self.supervisor.id,
            'agent_id': self.agent_id,
            'call_id': self.call_id,
            'whisper': 'none',
        }, content_type='application/json')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        redis_conn.publish.assert_called_once()
        channel, message = redis_conn.publish.call_args[0]
        self.assertEqual(channel, 'acd:commands:{0}'.format(self.node_id))
        payload = json.loads(message)
        self.assertEqual(payload['action'], 'spy')
        self.assertEqual(payload['callid'], self.call_id)
        self.assertEqual(payload['whisper'], 'none')

    @patch('api_app.views.transfer._get_redis_client')
    def test_voicebot_hangup_publishes_hangup_to_node(self, mock_redis_client):
        redis_conn = MagicMock()
        mock_redis_client.return_value = redis_conn
        redis_conn.hget.return_value = self.voicebot_payload
        redis_conn.publish.return_value = 1

        url = reverse('api_call_voicebot_hangup')
        response = self.client.post(url, {
            'agent_id': self.agent_id,
            'call_id': self.call_id,
        }, content_type='application/json')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        redis_conn.publish.assert_called_once()
        channel, message = redis_conn.publish.call_args[0]
        self.assertEqual(channel, 'acd:commands:{0}'.format(self.node_id))
        payload = json.loads(message)
        self.assertEqual(payload['action'], 'HANGUP')
        self.assertEqual(payload['callid'], self.call_id)

    @patch('api_app.views.transfer._get_redis_client')
    def test_voicebot_hangup_missing_call_returns_400(self, mock_redis_client):
        redis_conn = MagicMock()
        mock_redis_client.return_value = redis_conn
        redis_conn.hget.return_value = None

        url = reverse('api_call_voicebot_hangup')
        response = self.client.post(url, {
            'agent_id': self.agent_id,
            'call_id': 'missing-call',
        }, content_type='application/json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        redis_conn.publish.assert_not_called()
