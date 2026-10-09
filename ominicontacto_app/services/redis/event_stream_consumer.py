# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions
#
# This file is part of OMniLeads
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#

"""
Async Redis Streams consumer (XREADGROUP / XACK / XAUTOCLAIM) for
supervision and omnidialer event listeners.
"""
from __future__ import unicode_literals

import asyncio
import json
import logging
import os
import time

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from ominicontacto_app.services.redis.ha_lock import node_id
from ominicontacto_app.services.redis.redis_streams import EVENT_STREAM_DB

logger = logging.getLogger(__name__)

DEFAULT_AUTOCLAIM_IDLE_MS = 60 * 1000
DEFAULT_AUTOCLAIM_INTERVAL_SEC = 30
DEFAULT_BLOCK_MS = 2000
DEFAULT_COUNT = 10


def event_stream_autoclaim_idle_ms():
    try:
        return int(os.getenv('OML_EVENT_STREAM_AUTOCLAIM_MS', DEFAULT_AUTOCLAIM_IDLE_MS))
    except (TypeError, ValueError):
        return DEFAULT_AUTOCLAIM_IDLE_MS


def event_stream_autoclaim_interval_sec():
    try:
        return int(os.getenv(
            'OML_EVENT_STREAM_AUTOCLAIM_INTERVAL_SEC',
            DEFAULT_AUTOCLAIM_INTERVAL_SEC,
        ))
    except (TypeError, ValueError):
        return DEFAULT_AUTOCLAIM_INTERVAL_SEC


def is_nogroup_error(exception):
    """True when Redis reports missing stream/consumer group (NOGROUP)."""
    return 'NOGROUP' in str(exception)


class EventStreamConsumer(object):
    """Read one stream with a consumer group; invoke async callback per event."""

    def __init__(
            self, redis_client, stream_name, group_name, callback,
            consumer_name=None, autoclaim_idle_ms=None, block_ms=DEFAULT_BLOCK_MS,
            count=DEFAULT_COUNT, autoclaim_interval_sec=None):
        self.redis_client = redis_client
        self.stream_name = stream_name
        self.group_name = group_name
        self.callback = callback
        self.consumer_name = consumer_name or node_id()
        self.autoclaim_idle_ms = (
            autoclaim_idle_ms if autoclaim_idle_ms is not None
            else event_stream_autoclaim_idle_ms()
        )
        self.autoclaim_interval_sec = (
            autoclaim_interval_sec if autoclaim_interval_sec is not None
            else event_stream_autoclaim_interval_sec()
        )
        self.block_ms = block_ms
        self.count = count
        self._stop = False

    def stop(self):
        self._stop = True

    async def ensure_consumer_group(self):
        try:
            await self.redis_client.xgroup_create(
                self.stream_name,
                self.group_name,
                id='$',
                mkstream=True,
            )
            logger.info(
                'event-stream group created stream=%s group=%s',
                self.stream_name, self.group_name,
            )
        except ResponseError as exception:
            if 'BUSYGROUP' not in str(exception):
                raise

    async def _handle_message(self, msgid, fields):
        raw = fields.get('value')
        if raw is None:
            logger.warning(
                'event-stream missing value stream=%s id=%s',
                self.stream_name, msgid,
            )
            await self.redis_client.xack(self.stream_name, self.group_name, msgid)
            return
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        event_data = json.loads(raw)
        await self.callback(event_data)
        await self.redis_client.xack(self.stream_name, self.group_name, msgid)

    async def autoclaim_pending(self):
        """Claim idle PEL entries; paginate until the cursor is exhausted."""
        start_id = '0-0'
        while not self._stop:
            try:
                result = await self.redis_client.xautoclaim(
                    name=self.stream_name,
                    groupname=self.group_name,
                    consumername=self.consumer_name,
                    min_idle_time=self.autoclaim_idle_ms,
                    start_id=start_id,
                    count=self.count,
                )
            except ResponseError as exception:
                if is_nogroup_error(exception):
                    logger.warning(
                        'event-stream autoclaim NOGROUP stream=%s group=%s; recreating',
                        self.stream_name, self.group_name,
                    )
                    await self.ensure_consumer_group()
                    return
                logger.info(
                    'event-stream autoclaim skipped stream=%s err=%r',
                    self.stream_name, exception,
                )
                return
            next_id = '0-0'
            messages = []
            if isinstance(result, (list, tuple)):
                if len(result) >= 1:
                    next_id = result[0] or '0-0'
                if len(result) >= 2 and isinstance(result[1], list):
                    messages = result[1]
            for msgid, fields in messages:
                try:
                    await self._handle_message(msgid, fields)
                except Exception:
                    logger.exception(
                        'event-stream autoclaim handler failed stream=%s id=%s',
                        self.stream_name, msgid,
                    )
            if not messages:
                return
            if len(messages) < self.count:
                return
            if next_id in ('0-0', 0, b'0-0'):
                return
            start_id = next_id

    async def run(self):
        logger.info(
            'event-stream reader start stream=%s group=%s consumer=%s',
            self.stream_name, self.group_name, self.consumer_name,
        )
        await self.ensure_consumer_group()
        await self.autoclaim_pending()
        last_autoclaim = time.monotonic()
        while not self._stop:
            try:
                now = time.monotonic()
                if now - last_autoclaim >= self.autoclaim_interval_sec:
                    await self.autoclaim_pending()
                    last_autoclaim = now
                response = await self.redis_client.xreadgroup(
                    groupname=self.group_name,
                    consumername=self.consumer_name,
                    streams={self.stream_name: '>'},
                    count=self.count,
                    block=self.block_ms,
                )
                if not response:
                    continue
                for _stream, messages in response:
                    for msgid, fields in messages:
                        try:
                            await self._handle_message(msgid, fields)
                        except Exception:
                            logger.exception(
                                'event-stream handler failed stream=%s id=%s',
                                self.stream_name, msgid,
                            )
            except ResponseError as exception:
                if self._stop:
                    break
                if is_nogroup_error(exception):
                    logger.warning(
                        'event-stream NOGROUP stream=%s group=%s; recreating',
                        self.stream_name, self.group_name,
                    )
                    try:
                        await self.ensure_consumer_group()
                    except Exception:
                        logger.exception(
                            'event-stream failed recreating group stream=%s',
                            self.stream_name,
                        )
                        await asyncio.sleep(1)
                    continue
                logger.exception(
                    'event-stream reader error stream=%s', self.stream_name)
                await asyncio.sleep(1)
            except Exception:
                if self._stop:
                    break
                logger.exception(
                    'event-stream reader error stream=%s', self.stream_name)
                await asyncio.sleep(1)
        logger.info('event-stream reader stop stream=%s', self.stream_name)


def create_async_redis(db=EVENT_STREAM_DB):
    """Build redis.asyncio client for event streams (DB 2 by default)."""
    from django.conf import settings
    host = getattr(settings, 'REDIS_HOSTNAME', 'redis')
    port = 6379
    try:
        port = settings.CONSTANCE_REDIS_CONNECTION['port']
    except Exception:
        port = int(os.getenv('REDIS_PORT', '6379'))
    return Redis(host=host, port=port, db=db, decode_responses=True)
