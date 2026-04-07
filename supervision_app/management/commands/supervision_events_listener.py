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

import json
import logging

from django.core.management.base import BaseCommand
from ominicontacto_app.services.redis.connection import create_redis_connection
from supervision_app.services.events_management import SupervisionEventManager
from ominicontacto_app.services.dialer import wombat_habilitado

from asyncio import get_event_loop
from orquestador_app.core.asyncio import create_task
# AGENT_EVENTS_CHANNEL = 'OML:CHANNEL:AGENTEVENTS'
CALL_EVENTS_CHANNEL = 'OML:CHANNEL:CALLEVENTS'
DISPOSITIONS_EVENTS_CHANNEL = 'OML:CHANNEL:DISPOSITIONEVENTS'
OMNIDIALER_EVENTS_CHANNEL = 'OML:CHANNEL:DIALER'
logger = logging.getLogger(__name__)


class Command(BaseCommand):

    help = 'Atiende eventos de varios canales para actualizar datos de Supervision'

    async def manage_events(self, channels, redis_connection, loop):
        event_manager = SupervisionEventManager(redis_connection)
        # Subscribe to a channel
        pubsub = redis_connection.pubsub(ignore_subscribe_messages=True)

        pubsub.subscribe(channels)
        print("Subscribe channels: ", channels)

        # Listen for messages indefinitely
        for message in pubsub.listen():
            if message['type'] == 'message':
                message_data = message['data']
                try:
                    event_data = json.loads(message_data)
                    await event_manager.manage_event(event_data)
                except Exception as e:
                    logging.error(e, exc_info=True)

    async def subscribe_channels(self, channels, redis, loop):
        create_task(loop, await self.manage_events(channels, redis, loop))

    def handle(self, *args, **options):
        try:
            # Connect to Redis server
            redis_connection = create_redis_connection(db=2)
            loop = get_event_loop()
            try:
                channels = [CALL_EVENTS_CHANNEL, DISPOSITIONS_EVENTS_CHANNEL, ]
                # Assumo que si no se usa Wombat, se usa OMniDialer
                if not wombat_habilitado():
                    channels.append(OMNIDIALER_EVENTS_CHANNEL)
                loop.run_until_complete(self.subscribe_channels(channels, redis_connection, loop))
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
        except Exception as e:
            logger.error('Fallo del comando: {0}'.format(e))
