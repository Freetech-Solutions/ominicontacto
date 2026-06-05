# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.test import SimpleTestCase

from supervision_app.services.voicebot_stream_events import (
    agent_id_from_active_calls_key,
    build_delete_event,
    build_upsert_event,
    diff_voicebot_hash_events,
    row_id,
    stream_payload_str,
)


class VoicebotStreamEventsTest(SimpleTestCase):

    def test_agent_id_from_active_calls_key(self):
        self.assertEqual(
            agent_id_from_active_calls_key('OML:VOICEBOT-ACTIVE-CALLS:11'),
            '11',
        )

    def test_row_id_sanitizes_call_id(self):
        self.assertEqual(row_id(11, '1780600599.140'), '11__1780600599.140')

    def test_diff_emits_upsert_on_new_call(self):
        payload = json.dumps({
            'call_id': 'call-1',
            'campaign_id': '20',
            'contact_number': '555',
            'status': 'ONCALL',
            'timestamp': 1000,
            'node_id': 'acd01',
        })
        events = diff_voicebot_hash_events('11', {}, {'call-1': payload})

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['action'], 'upsert')
        self.assertEqual(events[0]['row_id'], '11__call-1')
        self.assertEqual(events[0]['CAMPAIGN'], '20')

    def test_diff_emits_delete_on_removed_call(self):
        payload = json.dumps({'call_id': 'call-1', 'status': 'ONCALL'})
        events = diff_voicebot_hash_events('11', {'call-1': payload}, {})

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['action'], 'delete')
        self.assertEqual(events[0]['row_id'], '11__call-1')

    def test_diff_concurrent_calls_delete_one(self):
        payload_1 = json.dumps({'call_id': 'call-1', 'status': 'ONCALL'})
        payload_2 = json.dumps({'call_id': 'call-2', 'status': 'ONCALL'})
        previous = {'call-1': payload_1, 'call-2': payload_2}
        current = {'call-2': payload_2}

        events = diff_voicebot_hash_events('11', previous, current)

        self.assertEqual(events[0]['action'], 'delete')
        self.assertEqual(events[0]['row_id'], '11__call-1')
        self.assertEqual(events[1]['action'], 'upsert')
        self.assertEqual(events[1]['call_id'], 'call-2')

    def test_build_upsert_event_fields(self):
        payload = json.dumps({
            'call_id': 'call-1',
            'campaign_id': '23',
            'contact_number': '123456713',
            'status': 'ONCALL',
            'timestamp': 2000,
            'bridge_id': 'bridge-1',
            'node_id': 'acd-node-1',
        })
        event = build_upsert_event(11, 'call-1', payload)

        self.assertEqual(event['CONTACT_NUMBER'], '123456713')
        self.assertEqual(event['node_id'], 'acd-node-1')

    def test_build_delete_event(self):
        event = build_delete_event(11, 'call-1')
        self.assertEqual(event, {'action': 'delete', 'row_id': '11__call-1'})

    def test_stream_payload_str_format(self):
        payload = stream_payload_str({
            'action': 'delete',
            'row_id': '11__call-1',
        })
        self.assertIn("'action': 'delete'", payload)
        self.assertIn("'row_id': '11__call-1'", payload)
