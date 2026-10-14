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
import logging
import sys

from django.core.management.base import BaseCommand

from ominicontacto_app.services.dialer.notification.events_management import (
    OmnidialerEventManager,
)
from ominicontacto_app.services.redis.connection import create_redis_connection
from ominicontacto_app.services.redis.event_stream_consumer import (
    EventStreamConsumer,
    create_async_redis,
)
from ominicontacto_app.services.redis.redis_streams import (
    GROUP_OMNIDIALER_EVENTS,
    STREAM_DIALER,
)

logger = logging.getLogger(__name__)

CALLDATA_DB = 2


class Command(BaseCommand):

    help = (
        'Atiende el stream OML:STREAM:DIALER para actualizar datos de campañas '
        'OMniDialer'
    )

    async def _run(self):
        redis_sync = create_redis_connection(db=CALLDATA_DB)
        event_manager = OmnidialerEventManager(redis_sync)
        redis_async = create_async_redis(db=CALLDATA_DB)
        await redis_async.ping()

        async def on_event(event_data):
            await event_manager.manage_event(event_data)

        consumer = EventStreamConsumer(
            redis_async,
            STREAM_DIALER,
            GROUP_OMNIDIALER_EVENTS,
            on_event,
        )
        logger.info(
            'omnidialer_events_listener stream=%s group=%s',
            STREAM_DIALER, GROUP_OMNIDIALER_EVENTS,
        )
        try:
            await consumer.run()
        finally:
            consumer.stop()
            await redis_async.aclose()

    def handle(self, *args, **options):
        try:
            asyncio.run(self._run())
        except Exception as e:
            logger.error('Fallo del comando: {0}'.format(e), exc_info=True)
            sys.exit(1)
