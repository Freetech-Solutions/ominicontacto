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

import asyncio
import json
import logging
import sys

from django.core.management.base import BaseCommand

from ominicontacto_app.services.dialer import wombat_habilitado
from ominicontacto_app.services.redis.connection import create_redis_connection
from ominicontacto_app.services.redis.event_stream_consumer import (
    EventStreamConsumer,
    create_async_redis,
)
from ominicontacto_app.services.redis.redis_streams import (
    GROUP_SUPERVISION_EVENTS,
    STREAM_CALLEVENTS,
    STREAM_DIALER,
    STREAM_DISPOSITIONEVENTS,
)
from supervision_app.services.events_management import SupervisionEventManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    help = (
        'Atiende streams Redis (CALLEVENTS / DISPOSITIONEVENTS / DIALER) '
        'para actualizar datos de Supervisión'
    )

    async def _run(self):
        redis_sync = create_redis_connection(db=2)
        event_manager = SupervisionEventManager(redis_sync)
        redis_async = create_async_redis(db=2)
        await redis_async.ping()

        streams = [STREAM_CALLEVENTS, STREAM_DISPOSITIONEVENTS]
        if not wombat_habilitado():
            streams.append(STREAM_DIALER)

        def _on_event(stream_name):
            async def on_event(event_data):
                logger.info(
                    'evento procesado stream=%s payload=%s',
                    stream_name,
                    json.dumps(event_data, default=str, ensure_ascii=False),
                )
                await event_manager.manage_event(event_data)
            return on_event

        consumers = [
            EventStreamConsumer(
                redis_async,
                stream_name,
                GROUP_SUPERVISION_EVENTS,
                _on_event(stream_name),
            )
            for stream_name in streams
        ]
        logger.info(
            'supervision_events_listener streams=%s group=%s',
            streams, GROUP_SUPERVISION_EVENTS,
        )
        try:
            await asyncio.gather(*[c.run() for c in consumers])
        finally:
            for consumer in consumers:
                consumer.stop()
            await redis_async.aclose()

    def handle(self, *args, **options):
        try:
            asyncio.run(self._run())
        except Exception as e:
            logger.error('Fallo del comando: {0}'.format(e), exc_info=True)
            sys.exit(1)
