# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from mock import MagicMock

from django.test import SimpleTestCase

from supervision_app.services.voicebot_calls import (
    get_voicebot_active_call_rows,
    get_voicebot_call_from_hash,
    VOICEBOT_ACTIVE_CALLS_KEY,
)


class VoicebotCallsServiceTest(SimpleTestCase):

    def _agente(self, agent_id=11, nombre='Bot Test'):
        agente = MagicMock()
        agente.id = agent_id
        agente.user.get_full_name.return_value = nombre
        agente.user.username = 'bot11'
        return agente

    def test_get_voicebot_active_call_rows_one_row_per_call(self):
        redis_conn = MagicMock()
        payload_1 = json.dumps({
            'call_id': '1780600599.140',
            'campaign_id': '20',
            'contact_number': '111',
            'status': 'ONCALL',
            'timestamp': 1000,
            'bridge_id': 'bridge-1',
            'node_id': 'acd01',
        })
        payload_2 = json.dumps({
            'call_id': '1780600610.144',
            'campaign_id': '21',
            'contact_number': '222',
            'status': 'ONCALL',
            'timestamp': 2000,
            'bridge_id': 'bridge-2',
            'node_id': 'acd01',
        })
        active_key = VOICEBOT_ACTIVE_CALLS_KEY.format(agent_id=11)
        redis_conn.hgetall.return_value = {
            '1780600599.140': payload_1,
            '1780600610.144': payload_2,
        }

        rows = get_voicebot_active_call_rows(redis_conn, [self._agente()])

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['row_id'], '11__1780600599.140')
        self.assertEqual(rows[1]['CONTACT_NUMBER'], '222')
        redis_conn.hgetall.assert_called_with(active_key)

    def test_get_voicebot_active_call_rows_filters_campaign(self):
        redis_conn = MagicMock()
        payload = json.dumps({
            'call_id': 'call-1',
            'campaign_id': '20',
            'contact_number': '111',
            'status': 'ONCALL',
            'timestamp': 1000,
            'bridge_id': 'bridge-1',
            'node_id': 'acd01',
        })
        redis_conn.hgetall.return_value = {'call-1': payload}

        rows = get_voicebot_active_call_rows(
            redis_conn, [self._agente()], campaign_id='99',
        )

        self.assertEqual(rows, [])

    def test_get_voicebot_call_from_hash(self):
        redis_conn = MagicMock()
        payload = json.dumps({
            'call_id': 'call-1',
            'node_id': 'acd-node-2',
            'status': 'ONCALL',
            'bridge_id': 'bridge-1',
            'campaign_id': '20',
            'contact_number': '555',
        })
        redis_conn.hget.return_value = payload

        result = get_voicebot_call_from_hash(redis_conn, 11, 'call-1')

        self.assertEqual(result['call_id'], 'call-1')
        self.assertEqual(result['node_id'], 'acd-node-2')
        active_key = VOICEBOT_ACTIVE_CALLS_KEY.format(agent_id=11)
        redis_conn.hget.assert_called_with(active_key, 'call-1')

    def test_get_voicebot_call_from_hash_missing(self):
        redis_conn = MagicMock()
        redis_conn.hget.return_value = None

        result = get_voicebot_call_from_hash(redis_conn, 11, 'missing')

        self.assertIsNone(result)
