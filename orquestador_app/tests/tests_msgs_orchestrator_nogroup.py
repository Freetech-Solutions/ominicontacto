# -*- coding: utf-8 -*-
"""NOGROUP recovery for msgs-orchestrator consumer groups."""
from __future__ import unicode_literals

import asyncio
import importlib
import unittest
from unittest.mock import AsyncMock

from redis.exceptions import ResponseError


class MsgsOrchestratorNogroupTests(unittest.IsolatedAsyncioTestCase):

    async def test_read_stream_recreates_group_on_nogroup(self):
        mod = importlib.import_module(
            'orquestador_app.management.commands.msgs-orchestrator'
        )
        EventsProcessor = mod.EventsProcessor

        processor = EventsProcessor()
        processor.redis_client = AsyncMock()
        processor.consumer_name = 'test-node'
        processor.shutdown = asyncio.Event()

        processor.redis_client.xgroup_create.side_effect = [
            ResponseError('BUSYGROUP already'),
            None,
        ]

        async def xautoclaim(**kwargs):
            return ('0-0', [])

        processor.redis_client.xautoclaim.side_effect = xautoclaim

        call_count = {'n': 0}
        handled = []

        async def callback(event):
            handled.append(event)
            processor.shutdown.set()

        async def xreadgroup(**kwargs):
            streams = kwargs.get('streams') or {}
            # drain-own-pending uses stream id '0'
            if streams and list(streams.values())[0] == '0':
                return []
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise ResponseError('NOGROUP No such key or consumer group')
            return [('whatsapp_line_1', [('1-0', {'type': 'msg'})])]

        processor.redis_client.xreadgroup.side_effect = xreadgroup

        await processor.read_stream(
            'whatsapp_line_1',
            callback,
            use_group=True,
            group_name='msgs-orchestrator:wa:1',
            consumer_name='test-node:wa:1',
        )

        self.assertEqual(len(handled), 1)
        self.assertEqual(processor.redis_client.xgroup_create.await_count, 2)
