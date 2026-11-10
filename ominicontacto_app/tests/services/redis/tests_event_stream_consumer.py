# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions
#
# This file is part of OMniLeads
#
"""Unit tests for event_stream_consumer (Streams HA for listeners)."""
from __future__ import unicode_literals

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from redis.exceptions import ResponseError

from ominicontacto_app.services.redis.event_stream_consumer import EventStreamConsumer
from ominicontacto_app.services.redis.redis_streams import (
    STREAM_CALLEVENTS,
    STREAM_DIALER,
    event_stream_maxlen,
)


class EventStreamConsumerTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.redis = AsyncMock()
        self.handled = []

        async def callback(event_data):
            self.handled.append(event_data)

        self.callback = callback
        self.consumer = EventStreamConsumer(
            self.redis,
            STREAM_CALLEVENTS,
            'supervision-events',
            self.callback,
            consumer_name='node-a',
            autoclaim_idle_ms=1000,
            block_ms=10,
            count=5,
            autoclaim_interval_sec=3600,
        )

    async def test_ensure_group_ignores_busygroup(self):
        self.redis.xgroup_create.side_effect = ResponseError('BUSYGROUP Consumer Group name already exists')
        await self.consumer.ensure_consumer_group()
        self.redis.xgroup_create.assert_awaited_once()

    async def test_handle_message_acks_on_success(self):
        fields = {'value': json.dumps({'type': 'WAIT', 'id': 5, 'time': 12})}
        await self.consumer._handle_message('1-0', fields)
        self.assertEqual(self.handled, [{'type': 'WAIT', 'id': 5, 'time': 12}])
        self.redis.xack.assert_awaited_once_with(
            STREAM_CALLEVENTS, 'supervision-events', '1-0')

    async def test_handle_message_no_ack_on_handler_error(self):
        async def boom(_event):
            raise RuntimeError('fail')

        self.consumer.callback = boom
        fields = {'value': json.dumps({'type': 'CAMP', 'id': 1, 'event': 'DIAL'})}
        with self.assertRaises(RuntimeError):
            await self.consumer._handle_message('2-0', fields)
        self.redis.xack.assert_not_awaited()

    async def test_run_processes_xreadgroup_once(self):
        self.redis.xgroup_create.side_effect = ResponseError('BUSYGROUP already')
        self.redis.xautoclaim.side_effect = ResponseError('NOGROUP')

        call_count = {'n': 0}

        async def xreadgroup(**kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return [(
                    STREAM_CALLEVENTS,
                    [('9-0', {'value': json.dumps({'type': 'QUEUE', 'id': '5', 'size': 1})})],
                )]
            self.consumer.stop()
            return []

        self.redis.xreadgroup.side_effect = xreadgroup
        await self.consumer.run()
        self.assertEqual(self.handled[0]['type'], 'QUEUE')
        self.redis.xack.assert_awaited()

    async def test_two_consumers_same_group_only_one_gets_message(self):
        """Simulate Redis delivering a message to only one consumer in the group."""
        handled_a = []
        handled_b = []

        async def cb_a(event):
            handled_a.append(event)

        async def cb_b(event):
            handled_b.append(event)

        redis_a = AsyncMock()
        redis_b = AsyncMock()
        redis_a.xgroup_create.side_effect = ResponseError('BUSYGROUP')
        redis_b.xgroup_create.side_effect = ResponseError('BUSYGROUP')
        redis_a.xautoclaim.side_effect = ResponseError('NOGROUP')
        redis_b.xautoclaim.side_effect = ResponseError('NOGROUP')

        msg = [('1-0', {'value': json.dumps({'type': 'DISPOSITION', 'id': 5, 'uuid': 'u1'})})]

        async def read_a(**kwargs):
            cons_a.stop()
            return [(STREAM_DIALER, msg)]

        async def read_b(**kwargs):
            cons_b.stop()
            return []  # other consumer in group gets nothing for this id

        redis_a.xreadgroup.side_effect = read_a
        redis_b.xreadgroup.side_effect = read_b

        cons_a = EventStreamConsumer(
            redis_a, STREAM_DIALER, 'omnidialer-events', cb_a,
            consumer_name='node-a', block_ms=10, autoclaim_interval_sec=3600)
        cons_b = EventStreamConsumer(
            redis_b, STREAM_DIALER, 'omnidialer-events', cb_b,
            consumer_name='node-b', block_ms=10, autoclaim_interval_sec=3600)

        await asyncio.gather(cons_a.run(), cons_b.run())
        self.assertEqual(len(handled_a), 1)
        self.assertEqual(len(handled_b), 0)

    async def test_autoclaim_paginates_until_empty(self):
        pages = [
            ('5-0', [('1-0', {'value': json.dumps({'type': 'WAIT', 'id': 1})}),
                     ('2-0', {'value': json.dumps({'type': 'WAIT', 'id': 2})})]),
            ('0-0', [('3-0', {'value': json.dumps({'type': 'WAIT', 'id': 3})})]),
        ]
        call = {'n': 0}

        async def xautoclaim(**kwargs):
            idx = call['n']
            call['n'] += 1
            return pages[idx]

        self.redis.xautoclaim.side_effect = xautoclaim
        self.consumer.count = 2
        await self.consumer.autoclaim_pending()
        self.assertEqual(call['n'], 2)
        self.assertEqual([e['id'] for e in self.handled], [1, 2, 3])
        self.assertEqual(self.redis.xack.await_count, 3)

    async def test_run_recreates_group_on_nogroup(self):
        """If Redis drops the group after start, recreate and keep reading."""
        self.redis.xgroup_create.side_effect = [
            ResponseError('BUSYGROUP already'),
            None,  # recreate after XREADGROUP NOGROUP
        ]

        async def xautoclaim(**kwargs):
            return ('0-0', [])

        self.redis.xautoclaim.side_effect = xautoclaim

        call_count = {'n': 0}

        async def xreadgroup(**kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise ResponseError(
                    'NOGROUP No such key \'OML:STREAM:CALLEVENTS\' or consumer group'
                )
            if call_count['n'] == 2:
                return [(
                    STREAM_CALLEVENTS,
                    [('10-0', {'value': json.dumps({'type': 'QUEUE', 'id': '7', 'size': 2})})],
                )]
            self.consumer.stop()
            return []

        self.redis.xreadgroup.side_effect = xreadgroup
        await self.consumer.run()

        self.assertEqual(self.handled[0]['type'], 'QUEUE')
        self.assertEqual(self.redis.xgroup_create.await_count, 2)
        self.redis.xack.assert_awaited()

    async def test_autoclaim_recreates_group_on_nogroup(self):
        self.redis.xautoclaim.side_effect = ResponseError(
            'NOGROUP No such key or consumer group'
        )
        await self.consumer.autoclaim_pending()
        self.redis.xgroup_create.assert_awaited_once()


class RedisStreamsConstantsTests(unittest.TestCase):

    def test_event_stream_maxlen_default(self):
        with patch.dict('os.environ', {}, clear=False):
            # may inherit env; just ensure positive int
            self.assertGreater(event_stream_maxlen(), 0)

    def test_write_event_uses_xadd(self):
        from ominicontacto_app.services.redis.redis_streams import RedisStreams
        conn = MagicMock()
        streams = RedisStreams(connection=conn)
        streams.write_event(STREAM_CALLEVENTS, {'type': 'WAIT', 'id': 1}, max_stream_length=50)
        conn.execute_command.assert_called_once()
        args = conn.execute_command.call_args[0]
        self.assertEqual(args[0], 'XADD')
        self.assertEqual(args[1], STREAM_CALLEVENTS)
        self.assertIn('value', args)
