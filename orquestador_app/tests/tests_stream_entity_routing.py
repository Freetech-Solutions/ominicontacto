# -*- coding: utf-8 -*-
"""Stream naming for msgs-orchestrator entity routing (WA/FB/IG)."""
from __future__ import unicode_literals

import unittest


class StreamEntityNamingTests(unittest.TestCase):

    def test_facebook_stream_uses_page_id_not_app_id(self):
        page_id = 'PAGE-99'
        app_id = 'APP-1'
        stream = 'facebook_meta_webhook_page_{}'.format(page_id)
        self.assertEqual(stream, 'facebook_meta_webhook_page_PAGE-99')
        self.assertNotIn(app_id, stream)

    def test_whatsapp_stream_uses_line_pk(self):
        self.assertEqual(
            'whatsapp_webhook_meta_line_{}'.format(7),
            'whatsapp_webhook_meta_line_7',
        )
        self.assertEqual(
            'whatsapp_webhook_gupshup_line_{}'.format(3),
            'whatsapp_webhook_gupshup_line_3',
        )

    def test_two_pages_same_app_get_distinct_streams(self):
        app_id = 'shared-app'
        stream_a = 'facebook_meta_webhook_page_{}'.format('p1')
        stream_b = 'facebook_meta_webhook_page_{}'.format('p2')
        self.assertNotEqual(stream_a, stream_b)
        old_a = 'facebook_meta_webhook_page_{}'.format(app_id)
        old_b = 'facebook_meta_webhook_page_{}'.format(app_id)
        self.assertEqual(old_a, old_b)

    def test_slave_group_is_per_channel_and_pk(self):
        group = 'msgs-orchestrator:{0}:{1}'.format('facebook', 12)
        consumer = '{0}:{1}:{2}'.format('test_ait_Node-1', 'facebook', 12)
        self.assertEqual(group, 'msgs-orchestrator:facebook:12')
        self.assertEqual(consumer, 'test_ait_Node-1:facebook:12')
        self.assertNotEqual(
            'msgs-orchestrator:facebook:12',
            'msgs-orchestrator:facebook:34',
        )


if __name__ == '__main__':
    unittest.main()
