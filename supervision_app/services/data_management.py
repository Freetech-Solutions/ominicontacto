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

from ominicontacto_app.models import Campana
from reportes_app.models import LlamadaLog
from ominicontacto_app.services.dialer import wombat_habilitado, get_dialer_service
from ominicontacto_app.services.redis.connection import create_redis_connection


def get_event_subscription_key(event_code):
    return f'OML:SUPERVISION:EVENT_SUBSCRIPTIONS:{event_code}'


class SupervisionDataManager:
    AGENTS = 'agents'
    OUTBOUND = 'outbound'
    DIALER = 'dialer'
    INBOUND = 'inbound'
    SECTIONS = [AGENTS, OUTBOUND, DIALER, INBOUND, ]
    """ Calcula la información a actualizar en Supervisión de acuerdo a cada evento ocurrido """

    def __init__(self, redis_oml_connection, redis_calldata_connection):
        self.agents = AgentsDataManager(redis_oml_connection, redis_calldata_connection)
        self.outbound = OutboundDataManager(redis_oml_connection, redis_calldata_connection)
        self.dialer = DialerDataManager(redis_oml_connection, redis_calldata_connection)
        self.inbound = InboundDataManager(redis_oml_connection, redis_calldata_connection)

    def add_subscription(self, user, section):
        # print('Subscribing: ', user)
        campaigns = self._current_campaigns(user)
        if section == self.AGENTS:
            initial_data = self.agents.subscribe(campaigns, user)
        if section == self.OUTBOUND:
            initial_data = self.outbound.subscribe(campaigns, user)
        if section == self.DIALER:
            initial_data = self.dialer.subscribe(campaigns, user)
        if section == self.INBOUND:
            initial_data = self.inbound.subscribe(campaigns, user)
        return initial_data

    def remove_subscription(self, user, section):
        # print('Unsubscribing: ', user)
        campaigns = self._current_campaigns(user)
        if section == self.AGENTS:
            self.agents.unsubscribe(campaigns, user)
        if section == self.OUTBOUND:
            self.outbound.unsubscribe(campaigns, user)
        if section == self.DIALER:
            self.dialer.unsubscribe(campaigns, user)
        if section == self.INBOUND:
            self.inbound.unsubscribe(campaigns, user)

    def update(self, supervisor_id, section_id, event_data):
        if section_id == AgentsDataManager.ID:
            new_data = self.agents.update(event_data)
        if section_id == OutboundDataManager.ID:
            new_data = self.outbound.update(event_data)
        if section_id == DialerDataManager.ID:
            new_data = self.dialer.update(event_data)
        if section_id == InboundDataManager.ID:
            new_data = self.inbound.update(event_data)
        return new_data

    def _current_campaigns(self, user):
        if user.get_is_administrador():
            return Campana.objects.obtener_actuales()
        else:
            supervisor = user.get_supervisor_profile()
            return supervisor.campanas_asignadas_actuales()


class AbstractDataManager():
    def __init__(self, redis_oml_connection, redis_calldata_connection):
        self.redis_calldata_connection = redis_calldata_connection
        self.redis_oml_connection = redis_oml_connection

    def _manager_id(self, user):
        return f'{self.ID}:{user.id}'

    def subscribe(self, campaigns, user):
        raise NotImplementedError()

    def unsubscribe(self, campaigns, user):
        raise NotImplementedError()


class AgentsDataManager(AbstractDataManager):
    ID = 'AGENTS'


class DialerDataManager(AbstractDataManager):
    ID = 'DIALER'
    EVENTOS_ATENDIDAS = ('EXIT_ANSWERED_HUMAN', 'EXIT_ANSWERED_BOT', 'EXIT_ANSWERED_MIX')
    # Eventos que suman en la columna "Perdidas" (Redis CALL_TYPE:2:*) y se actualizan en tiempo real
    PERDIDAS_DIALER_EVENTS = (
        'EXIT_TIMEOUT',
        'EXIT_ABANDON',
        'EXIT_HANDOFF_TIMEOUT',
        'EXIT_HANDOFF_ABANDON',
    )
    # Eventos extra en CALLDATA del panel (no están en EVENTOS_NO_CONTACTACION / NO_DIALOGO)
    EXTRA_PANEL_CALL_EVENTS = ('EXIT_BUSY', 'EXIT_CONGESTION')
    # Mapeo fino hacia keys de Llamadas Outbound (panel-general); campanas_dialers ignora outbound_field
    OUTBOUND_FIELD_BY_EVENT = {
        'DIAL': 'discadas',
        'EXIT_ANSWERED_HUMAN': 'atendidas_human',
        'EXIT_ANSWERED_BOT': 'atendidas_bot',
        'EXIT_ANSWERED_MIX': 'atendidas_mix',
        'EXIT_AMD': 'contestadores',
        'BUSY': 'ocupado',
        'EXIT_BUSY': 'ocupado',
        'NOANSWER': 'timeout',
        'EXIT_TIMEOUT': 'timeout',
        'EXIT_HANDOFF_TIMEOUT': 'timeout',
        'CANCEL': 'canceladas',
        'EXIT_SHORTCALL': 'shortcall',
        'CONGESTION': 'congestion',
        'EXIT_CONGESTION': 'congestion',
        'CHANUNAVAIL': 'chanunavail',
        'NONDIALPLAN': 'num_sin_ruta',
        'FAIL': 'errores',
        'OTHER': 'errores',
        'BLACKLIST': 'errores',
    }
    # EXIT_SHORTCALL: escrito por el logger ACD; contar como fin de llamada para canales y como no atendida en tiempo real
    # EXIT_AMD: contestador (columna "Contestador"); el logger publica CAMP en CALLEVENTS para tiempo real
    CALL_EVENTS = ('DIAL', 'CONNECT') + EVENTOS_ATENDIDAS + ('EXIT_SHORTCALL', 'EXIT_AMD') \
        + LlamadaLog.EVENTOS_NO_CONEXION \
        + LlamadaLog.EVENTOS_NO_CONTACTACION \
        + LlamadaLog.EVENTOS_NO_DIALOGO \
        + EXTRA_PANEL_CALL_EVENTS
    PENDING_RETRIES = 'NO CONTACTS WITH PENDING ATTEMPTS'
    PENDING_INITIAL = 'PENDING_INITIAL_CONTACT_ATTEMPTS'
    # Eventos que el logger ACD escribe en Redis como fin de llamada (sin EVENTOS_FIN_CONEXION legacy)
    ENDING_EVENTS = [f'CALL_TYPE:{Campana.TYPE_DIALER}:{event}' for event in
                     list(EVENTOS_ATENDIDAS) + ['EXIT_SHORTCALL']
                     + list(LlamadaLog.EVENTOS_NO_CONEXION) + list(EXTRA_PANEL_CALL_EVENTS)]

    def _with_outbound_field(self, data, event):
        outbound_field = self.OUTBOUND_FIELD_BY_EVENT.get(event)
        if outbound_field:
            data['outbound_field'] = outbound_field
        return data

    def __init__(self, redis_oml_connection, redis_calldata_connection):
        super().__init__(redis_oml_connection, redis_calldata_connection)
        if not wombat_habilitado():
            self.redis_dialer_connection = create_redis_connection(db=3)

    # canales: Obtener el valor de dialer_pstn_calls dentro de OML:CAMP:<id>

    def subscribe(self, campaigns, user):
        manager_id = self._manager_id(user)
        initial_data = {}

        campaigns = campaigns.filter(type=Campana.TYPE_DIALER).filter(
            estado__in=[Campana.ESTADO_ACTIVA, Campana.ESTADO_PAUSADA, Campana.ESTADO_INACTIVA])

        # TODO: Se pueden optimizar las llamadas a Redis utilizando Pipelines o llamando
        # a MGET en vez de multiples GET por ejemplo.
        precomputations = self._precomputate_initial_values(campaigns)

        campaigns_by_id = {}
        for campaign in campaigns:

            campaigns_by_id[campaign.id] = campaign
            # Call Events
            for event in self.CALL_EVENTS:
                event_code = f'CAMP:{campaign.id}:{event}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.sadd(key, manager_id)
            # Disposiion Events
            event_code = f'DISPOSITION:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.sadd(key, manager_id)
            # OMniDialer Events
            if not wombat_habilitado():
                event_code = f'STATS:{campaign.id}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.sadd(key, manager_id)
                event_code = f'STATUSCHANGE:{campaign.id}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.sadd(key, manager_id)
                event_code = f'CALLS:{campaign.id}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.sadd(key, manager_id)

            initial_data[campaign.id] = self._get_initial_data(campaign, precomputations)

        if wombat_habilitado():
            # Uso servicio de Wombat para obtener las llamadas pendientes
            dialer_service = get_dialer_service()
            pendings_by_id = dialer_service.obtener_llamadas_pendientes_por_id(campaigns_by_id)
            self._set_wombat_pendings(initial_data, pendings_by_id)

        # TODO Analizar solo enviar data de campañas con datos
        return initial_data

    def unsubscribe(self, campaigns, user):
        # Analizar recorrer todas las suscripciones usando un
        # scan('OML:SUPERVISION:EVENT_SUBSCRIPTIONS:*') eliminando el manager_id de todas.
        # Así no quedarian suscripciones fantasmas en caso de que cambien asignaciones de campañas.

        manager_id = self._manager_id(user)
        campaigns = campaigns.filter(type=Campana.TYPE_DIALER)
        for campaign in campaigns:
            # CAMP event Types
            for event in self.CALL_EVENTS:
                event_code = f'CAMP:{campaign.id}:{event}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.srem(key, manager_id)
            # DISPOSITION (misma clave que en subscribe)
            event_code = f'DISPOSITION:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.srem(key, manager_id)
            # OMniDialer Events
            if not wombat_habilitado():
                event_code = f'STATS:{campaign.id}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.srem(key, manager_id)
                event_code = f'STATUSCHANGE:{campaign.id}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.srem(key, manager_id)
                event_code = f'CALLS:{campaign.id}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.srem(key, manager_id)

    def get_campaigns_calldata(self, campaigns):
        campaign_ids = []
        calldata_keys = []
        for campaign in campaigns:
            campaign_ids.append(campaign.id)
            calldata_keys.append('OML:CALLDATA:CAMP:{0}'.format(campaign.id))

        pipeline = self.redis_calldata_connection.pipeline()
        for key in calldata_keys:
            pipeline.hgetall(key)
        calldata_results = pipeline.execute()

        return dict(zip(campaign_ids, calldata_results))

    def _precomputate_initial_values(self, campaigns):
        # Agrupar requests a Redis para reducir cantidad de requests
        precomputations = {
            'calldata': {},
            'channels': {}
        }
        calldata_by_id = self.get_campaigns_calldata(campaigns)
        precomputations['calldata'] = calldata_by_id

        if wombat_habilitado():
            for id, calldata in calldata_by_id.items():
                precomputations['channels'][id] = self.compute_channels_from_calldata(calldata)

        return precomputations

    def _get_initial_data(self, campaign, precomputations):
        dialed = 0
        attended = 0
        not_attended = 0
        amd = 0
        connections_lost = 0
        dispositions = 0
        pending = 0
        shortcall = 0
        status = campaign.estado

        calldata = precomputations['calldata'][campaign.id]
        # Get CALLDATA sums
        for key, value in calldata.items():
            _key = key.split(':')  # CALL_TYPE:<call_type>:<event>
            if len(_key) >= 3 and _key[0] == 'CALL_TYPE' and _key[1] == str(LlamadaLog.LLAMADA_DIALER):
                event = _key[-1]
                if event == 'DIAL':
                    dialed = value
                elif event in self.EVENTOS_ATENDIDAS:
                    attended += int(value)
                elif event in LlamadaLog.EVENTOS_NO_CONTACTACION:
                    not_attended += int(value)
                elif event == 'EXIT_AMD':
                    amd = value
                elif event in self.PERDIDAS_DIALER_EVENTS:
                    connections_lost += int(value)
        # Shortcall: CALL_TYPE:1:EXIT_SHORTCALL + CALL_TYPE:2:EXIT_SHORTCALL (Redis DB2)
        for key, value in calldata.items():
            _key = key.split(':')
            if len(_key) >= 3 and _key[0] == 'CALL_TYPE' and _key[-1] == 'EXIT_SHORTCALL':
                shortcall += int(value or 0)
        # Get dispositions
        # TODO: Optimizar precalculando todas las DISPOSITIONDATA-> Engaged por id
        #       dispositions = precomputations['calldata'][campaign.id]
        dispositiondata_key = 'OML:DISPOSITIONDATA:CAMP:{0}'.format(campaign.id)
        response = self.redis_calldata_connection.hget(dispositiondata_key, 'ENGAGED')
        if response:
            dispositions = response

        initial_data = {
            'dialed': dialed,
            'attended': attended,
            'not_attended': not_attended,
            'shortcall': shortcall,
            'amd': amd,
            'connections_lost': connections_lost,
            'dispositions': dispositions,
            'status': status,
            'pending': pending,
            'channels': '-'
        }

        # Get pending
        if not wombat_habilitado():
            # TODO: Optimizar precalculando CAMP:{0}:COUNTER ->PENDING... x id
            pending_initial, pending_retries = self._get_omnidialer_pending(campaign)
            initial_data['pending_initial'] = pending_initial
            initial_data['pending_retries'] = pending_retries
            initial_data['pending'] = pending_initial + pending_retries
            initial_data['channels'] = self._get_omnidialer_channels(campaign)
        else:
            initial_data['channels'] = precomputations['channels'][campaign.id]
        return initial_data

    def _get_omnidialer_pending(self, campaign):
        CAMP_STATS_KEY = 'CAMP:{0}:COUNTER'
        key = CAMP_STATS_KEY.format(campaign.id)
        initial = self.redis_dialer_connection.hget(key, self.PENDING_INITIAL)
        retries = self.redis_dialer_connection.hget(key, self.PENDING_RETRIES)
        initial = int(initial) if initial else 0
        retries = int(retries) if retries else 0
        return [initial, retries]

    def _get_omnidialer_channels(self, campaign):
        CAMP_CHANNELS_KEY = 'OML:CALLS:{0}:DIALER'
        key = CAMP_CHANNELS_KEY.format(campaign.id)
        calls = self.redis_dialer_connection.get(key)
        return int(calls) if calls else 0

    def _set_wombat_pendings(self, initial_data, pendings_by_id):
        """ Copies pending data in initial_data for each campaign from pendings_by id"""
        for id, data in initial_data.items():
            data['pending'] = pendings_by_id.get(id, '-')

    def get_channels_from_calldata(self, campaign_id):
        """ Fetchs campign CALLDATA to calculate channels in use """
        key = 'OML:CALLDATA:CAMP:{0}'.format(campaign_id)
        calldata = self.redis_calldata_connection.hgetall(key)
        return self.compute_channels_from_calldata(calldata)

    def compute_channels_from_calldata(self, calldata):
        dialed = int(calldata.get(f'CALL_TYPE:{Campana.TYPE_DIALER}:DIAL', 0))
        finished = 0
        for key, value in calldata.items():
            if key in self.ENDING_EVENTS:
                finished += int(value)
        active = dialed - finished
        return max(active, 0)

    def update(self, event_data):
        if event_data['type'] == 'CAMP':
            if event_data['call_type'] != str(LlamadaLog.LLAMADA_DIALER):
                return
            event = event_data['event']
            campaign_id = event_data['id']
            if event == 'DIAL':
                data = {'campaign_id': campaign_id, 'field': 'dialed'}
                if wombat_habilitado():
                    data['channels'] = self.get_channels_from_calldata(campaign_id)
                return self._with_outbound_field(data, event)
            if event in self.EVENTOS_ATENDIDAS:
                return self._with_outbound_field(
                    {'campaign_id': campaign_id, 'field': 'attended'}, event)
            if event == 'CONNECT':
                # Tabla dialer cuenta CONNECT; el panel Outbound solo usa EXIT_ANSWERED_*
                return {'campaign_id': campaign_id, 'field': 'attended'}
            if event == 'EXIT_SHORTCALL':
                # Solo actualizar shortcall; no contar como No atendida
                return self._with_outbound_field(
                    {'campaign_id': campaign_id, 'field': 'shortcall', 'delta': 1}, event)
            if event in LlamadaLog.EVENTOS_NO_CONTACTACION:
                return self._with_outbound_field(
                    {'campaign_id': campaign_id, 'field': 'not_attended'}, event)
            if event in self.EXTRA_PANEL_CALL_EVENTS:
                # EXIT_BUSY / EXIT_CONGESTION: panel Occupado/Congestion; tabla dialer = no atendida
                return self._with_outbound_field(
                    {'campaign_id': campaign_id, 'field': 'not_attended'}, event)
            if event == 'EXIT_AMD':
                return self._with_outbound_field(
                    {'campaign_id': campaign_id, 'field': 'amd'}, event)
            if event in self.PERDIDAS_DIALER_EVENTS:
                return self._with_outbound_field(
                    {'campaign_id': campaign_id, 'field': 'connections_lost'}, event)
        if event_data['type'] == 'DISPOSITION':
            delta = 0
            if event_data['engaged']:
                delta = 1
            elif not event_data['engaged'] and event_data['has_previous_different']:
                delta = -1
            if delta:
                return {
                    'campaign_id': event_data['id'],
                    'field': 'dispositions',
                    'delta': delta
                }
        if event_data['type'] == 'STATS':  # OMniDialer Only
            update_data = {'campaign_id': event_data['camp_id'], }
            if self.PENDING_INITIAL in event_data:
                update_data['field'] = 'pending'
                update_data['pending_initial'] = event_data[self.PENDING_INITIAL]
            if self.PENDING_RETRIES in event_data:
                update_data['field'] = 'pending'
                update_data['pending_retries'] = event_data[self.PENDING_RETRIES]
            return update_data
        if event_data['type'] == 'STATUSCHANGE':
            update_data = {'campaign_id': event_data['camp_id'],
                           'field': 'status',
                           'value': event_data['status']}
            return update_data
        if event_data['type'] == 'CALLS':
            update_data = {'campaign_id': event_data['camp_id'],
                           'field': 'channels',
                           'channels': event_data['calls']}
            return update_data


class InboundDataManager(AbstractDataManager):
    ID = 'IN'

    def subscribe(self, campaigns, user):
        manager_id = self._manager_id(user)
        initial_data = {}
        campaigns_ids = []

        campaigns = campaigns.filter(type=Campana.TYPE_ENTRANTE)
        for campaign in campaigns:
            # Call Events
            event_code = f'CAMP:{campaign.id}:EXIT_TIMEOUT'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.sadd(key, manager_id)
            # Wait time
            event_code = f'WAIT:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.sadd(key, manager_id)
            # Disposiion Events
            event_code = f'DISPOSITION:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.sadd(key, manager_id)
            # Abandon Wait Events
            event_code = f'EXIT_ABANDON:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.sadd(key, manager_id)
            # Queue Size Events
            event_code = f'QUEUE:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.sadd(key, manager_id)

            campaigns_ids.append(campaign.id)
            initial_data[campaign.id] = self._get_initial_data(campaign)
        self._set_initial_queue_sizes(campaigns_ids, initial_data)

        # TODO Analizar solo enviar data de campañas con datos
        return initial_data

    def unsubscribe(self, campaigns, user):
        # Analizar recorrer todas las suscripciones usando un
        # scan('OML:SUPERVISION:EVENT_SUBSCRIPTIONS:*') eliminando el manager_id de todas.
        # Así no quedarian suscripciones fantasmas en caso de que cambien asignaciones de campañas.
        manager_id = self._manager_id(user)
        campaigns = campaigns.filter(type=Campana.TYPE_ENTRANTE)
        for campaign in campaigns:
            # Call Events
            event_code = f'CAMP:{campaign.id}:EXIT_TIMEOUT'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.srem(key, manager_id)
            # Wait time
            event_code = f'WAIT:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.srem(key, manager_id)
            # Disposiion Events
            event_code = f'DISPOSITION:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.srem(key, manager_id)
            # Abandon Wait Events
            event_code = f'EXIT_ABANDON:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.srem(key, manager_id)
            # Queue Size Events
            event_code = f'QUEUE:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.srem(key, manager_id)

    def _get_initial_data(self, campaign):
        attended = 0
        wait_time_sum = 0
        expired = 0
        dispositions = 0
        abandons = 0
        abandons_sum = 0

        # Get expired from CALLDATA:CAMP
        calldata_key = 'OML:CALLDATA:CAMP:{0}'.format(campaign.id)
        field = f'CALL_TYPE:{Campana.TYPE_ENTRANTE}:EXIT_TIMEOUT'
        response = self.redis_calldata_connection.hget(calldata_key, field)
        if response:
            expired = response
        # Get attended + wait times sum:
        wait_time_key = 'OML:CALLDATA:WAIT-TIME:CAMP:{0}'.format(campaign.id)
        wait_times = self.redis_calldata_connection.lrange(wait_time_key, 0, -1)
        for time in wait_times:
            attended += 1
            wait_time_sum += int(time)
        # Get dispositions
        dispositiondata_key = 'OML:DISPOSITIONDATA:CAMP:{0}'.format(campaign.id)
        response = self.redis_calldata_connection.hget(dispositiondata_key, 'ENGAGED')
        if response:
            dispositions = response
        # Get abandons
        abandon_time_key = 'OML:CALLDATA:EXIT_ABANDON-TIME:CAMP:{0}'.format(campaign.id)
        abandon_times = self.redis_calldata_connection.lrange(abandon_time_key, 0, -1)
        for time in abandon_times:
            abandons += 1
            abandons_sum += int(time)

        return {
            'attended': attended,
            'total_wait_time': wait_time_sum,
            'expired': expired,
            'abandons': abandons,
            'total_abandon_time': abandons_sum,
            'dispositions': dispositions,
            'queue_size': 0,
        }

    def update(self, event_data):
        if event_data['type'] == 'CAMP':
            if event_data['event'] == 'EXIT_TIMEOUT':
                return {'campaign_id': event_data['id'], 'field': 'expired'}
        if event_data['type'] == 'WAIT':
            return {'campaign_id': event_data['id'], 'field': 'attended',
                    'wait_time': event_data['time']}
        if event_data['type'] == 'EXIT_ABANDON':
            return {'campaign_id': event_data['id'], 'field': 'abandons',
                    'time': event_data['time']}
        if event_data['type'] == 'DISPOSITION':
            delta = 0
            if event_data['engaged']:
                delta = 1
            elif not event_data['engaged'] and event_data['has_previous_different']:
                delta = -1
            if delta:
                return {
                    'campaign_id': event_data['id'],
                    'field': 'dispositions',
                    'delta': delta
                }
            return
        if event_data['type'] == 'QUEUE':
            return {'campaign_id': event_data['id'], 'field': 'queue_size',
                    'size': event_data['size']}

    def _set_initial_queue_sizes(self, campaigns_ids, initial_data):
        # OML:CALLDATA:QUEUE-SIZE lo escribe ari-app en Redis DB 0
        CALLDATA_QUEUE_SIZE_KEY = 'OML:CALLDATA:QUEUE-SIZE:{0}'
        keys = [CALLDATA_QUEUE_SIZE_KEY.format(campaign_id) for campaign_id in campaigns_ids]
        sizes = self.redis_oml_connection.mget(keys) if self.redis_oml_connection else [None] * len(keys)
        i = 0
        for campaign_id in campaigns_ids:
            size = sizes[i]
            if size is not None:
                initial_data[campaign_id]['queue_size'] = int(size)
            i += 1


class OutboundDataManager(AbstractDataManager):
    ID = 'OUT'
    CAMP_TYPES = [Campana.TYPE_DIALER, Campana.TYPE_PREVIEW, Campana.TYPE_MANUAL]
    NOT_ATTENDED_EVENTS = LlamadaLog.EVENTOS_NO_CONEXION
    # Alineado con logger ACD (update_redis_call_stats): ya no se acumula ANSWER en Redis;
    # atendidas van a EXIT_ANSWERED_*; dialer también publica CONNECT a CALLEVENTS.
    ATTENDED_EVENTS = (
        'ANSWER',
        'CONNECT',
        'EXIT_ANSWERED_HUMAN',
        'EXIT_ANSWERED_BOT',
        'EXIT_ANSWERED_MIX',
    )
    CALL_EVENTS = ('DIAL',) + ATTENDED_EVENTS + NOT_ATTENDED_EVENTS

    def subscribe(self, campaigns, user):
        manager_id = self._manager_id(user)
        initial_data = {}

        campaigns = campaigns.filter(type__in=self.CAMP_TYPES)
        for campaign in campaigns:
            # Call Events
            for event in self.CALL_EVENTS:
                event_code = f'CAMP:{campaign.id}:{event}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.sadd(key, manager_id)
            # Disposiion Events
            event_code = f'DISPOSITION:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.sadd(key, manager_id)

            initial_data[campaign.id] = self._get_initial_data(campaign)

        # TODO Analizar solo enviar data de campañas con datos
        return initial_data

    def unsubscribe(self, campaigns, user):
        # Analizar recorrer todas las suscripciones usando un
        # scan('OML:SUPERVISION:EVENT_SUBSCRIPTIONS:*') eliminando el manager_id de todas.
        # Así no quedarian suscripciones fantasmas en caso de que cambien asignaciones de campañas.
        manager_id = self._manager_id(user)
        campaigns = campaigns.filter(type__in=self.CAMP_TYPES)
        for campaign in campaigns:
            # CAMP event Types
            for event in self.CALL_EVENTS:
                event_code = f'CAMP:{campaign.id}:{event}'
                key = get_event_subscription_key(event_code)
                self.redis_calldata_connection.srem(key, manager_id)
            # DISPOSITION
            event_code = f'DISPOSITION:{campaign.id}'
            key = get_event_subscription_key(event_code)
            self.redis_calldata_connection.srem(key, manager_id)

    def _count_dialed_from_calldata(self, response):
        """
        Discadas salientes: suma de CALL_TYPE:<tipo>:DIAL (manual, dialer, preview, etc.).
        Si no hay claves CALL_TYPE:*:DIAL, mismo fallback que _get_campaign_call_metrics: DIAL_OUT.
        (La clave plana DIAL_OUT no termina en ':DIAL', por eso no basta con mirar el último segmento.)
        """
        total = 0
        for key, value in response.items():
            parts = key.split(':')
            if len(parts) >= 3 and parts[0] == 'CALL_TYPE' and parts[-1] == 'DIAL':
                try:
                    total += int(float(value or 0))
                except (TypeError, ValueError):
                    continue
        if total == 0:
            raw = response.get('DIAL_OUT')
            if raw is not None:
                try:
                    total = int(float(raw))
                except (TypeError, ValueError):
                    total = 0
        return total

    def _get_initial_data(self, campaign):
        calldata_key = 'OML:CALLDATA:CAMP:{0}'.format(campaign.id)
        response = self.redis_calldata_connection.hgetall(calldata_key)
        attended = 0
        not_attended = 0
        dispositions = 0
        dialed = self._count_dialed_from_calldata(response)
        # Get CALLDATA sums (varios CALL_TYPE:x:* por campaña)
        for key, value in response.items():
            event = key.split(':')[-1]
            if event in self.ATTENDED_EVENTS:
                try:
                    attended += int(float(value or 0))
                except (TypeError, ValueError):
                    continue
            elif event in self.NOT_ATTENDED_EVENTS:
                not_attended += int(value)
        # Get dispositions
        dispositiondata_key = 'OML:DISPOSITIONDATA:CAMP:{0}'.format(campaign.id)
        response = self.redis_calldata_connection.hget(dispositiondata_key, 'ENGAGED')
        if response:
            dispositions = response

        return {
            'dialed': dialed,
            'attended': attended,
            'not_attended': not_attended,
            'dispositions': dispositions,
        }

    def update(self, event_data):
        if event_data['type'] == 'CAMP':
            if event_data['event'] == 'DIAL':
                return {'campaign_id': event_data['id'], 'field': 'dialed'}
            if event_data['event'] in self.ATTENDED_EVENTS:
                return {'campaign_id': event_data['id'], 'field': 'attended'}
            if event_data['event'] in self.NOT_ATTENDED_EVENTS:
                return {'campaign_id': event_data['id'], 'field': 'not_attended'}
        if event_data['type'] == 'DISPOSITION':
            delta = 0
            if event_data['engaged']:
                delta = 1
            elif not event_data['engaged'] and event_data['has_previous_different']:
                delta = -1
            if delta:
                return {
                    'campaign_id': event_data['id'],
                    'field': 'dispositions',
                    'delta': delta
                }
