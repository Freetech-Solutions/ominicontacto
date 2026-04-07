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

from supervision_app.services.data_management import \
    get_event_subscription_key, SupervisionDataManager
from notification_app.notification import SupervisionNotifier
from ominicontacto_app.services.redis.connection import create_redis_connection

CAMPAIGN_EVENT_TYPE = 'CAMP'
DISPOSITION_EVENT_TYPE = 'DISPOSITION'
QUEUE_EVENT_TYPE = 'QUEUE'
ABANDON_EVENT_TYPE = 'ABANDON'
# Publicado por el worker ACD (logger) a CALLEVENTS; debe coincidir con InboundDataManager.subscribe
EXIT_ABANDON_EVENT_TYPE = 'EXIT_ABANDON'
WAIT_EVENT_TYPE = 'WAIT'
DIALER_STATS = 'STATS'
DIALER_STATUSCHANGE = 'STATUSCHANGE'
DIALER_CALLS = 'CALLS'
# AGENT_EVENT_TYPE = 'AGENT'


class SupervisionEventManager(object):

    def __init__(self, redis_connection) -> None:
        self.redis_oml_connection = create_redis_connection(db=0)
        self.redis_connection = redis_connection
        self.notifier = SupervisionNotifier()

    async def manage_event(self, event_data):
        # print('SupervisionEventManager - Evento recibido:', event_data)
        subscriptors = self._get_event_subscriptors(event_data)
        if not subscriptors:
            # print('NO SUBSCRIPTORS')
            return

        data_manager = SupervisionDataManager(
            self.redis_oml_connection, self.redis_connection)
        supervision_data = {}
        for subscriptor_id in subscriptors:
            section_id, supervisor_id = subscriptor_id.split(':')
            new_data = data_manager.update(supervisor_id, section_id, event_data)
            # print('GENERADO: ', new_data)
            if new_data:
                supervisor_data = supervision_data.get(supervisor_id, {})
                # TODO: Analizar si hace falta separar notificación por "section_id".
                # ¿Qué pasa si el supervisor esta suscripto a dos vistas de supervision?
                supervisor_data[section_id] = new_data
                if supervisor_id not in supervision_data:
                    supervision_data[supervisor_id] = supervisor_data
        # Agrupa supervisor_data en una misma notificacion
        for supervisor_id, supervisor_data in supervision_data.items():
            # print('Notify:', supervisor_id, supervisor_data)
            await self.notifier.send_message('update', supervisor_data, supervisor_id)

    def _get_event_subscriptors(self, event_data):
        event_code = self._get_event_code(event_data)
        if event_code:
            # print("Event Code: ", event_code)
            subcriptions_key = get_event_subscription_key(event_code)
            return self.redis_connection.smembers(subcriptions_key)  # db 2

    def _get_event_code(self, event_data):
        type = event_data['type']
        # if type == AGENT_EVENT_TYPE:
        #     # AGENTS:campaign_id
        #     campaign_id = event_data['campaign'].split('_')[0]
        #     agent_id = event_data['agent']
        #     return f'{type}:{agent_id}'
        if type == CAMPAIGN_EVENT_TYPE:
            # CAMP:campaign_id:event
            campaign_id = event_data['id']
            event = event_data['event']
            return f'{type}:{campaign_id}:{event}'
        if type == DISPOSITION_EVENT_TYPE:
            # DISPOSITION:{campaign.id}
            campaign_id = event_data['id']
            return f'{type}:{campaign_id}'
        if type == EXIT_ABANDON_EVENT_TYPE:
            # EXIT_ABANDON:{campaign.id}
            campaign_id = event_data['id']
            return f'{EXIT_ABANDON_EVENT_TYPE}:{campaign_id}'
        if type == ABANDON_EVENT_TYPE:
            # ABANDON:{campaign.id}
            campaign_id = event_data['id']
            return f'{type}:{campaign_id}'
        if type == QUEUE_EVENT_TYPE:
            # QUEUE:{campaign.id}
            campaign_id = event_data['id']
            return f'{type}:{campaign_id}'
        if type == WAIT_EVENT_TYPE:
            # WAIT:{campaign.id}
            campaign_id = event_data['id']
            return f'{type}:{campaign_id}'
        if type == DIALER_STATS:
            # Por el momento solo me interesan los eventos STATS para estos valores
            campaign_id = event_data.get('camp_id', None)
            if campaign_id and 'PENDING_INITIAL_CONTACT_ATTEMPTS' in event_data:
                return f'{type}:{campaign_id}'
            if campaign_id and 'NO CONTACTS WITH PENDING ATTEMPTS' in event_data:
                return f'{type}:{campaign_id}'
        if type == DIALER_STATUSCHANGE:
            campaign_id = event_data.get('camp_id', None)
            return f'{type}:{campaign_id}'
        if type == DIALER_CALLS:
            campaign_id = event_data.get('camp_id', None)
            return f'{type}:{campaign_id}'
