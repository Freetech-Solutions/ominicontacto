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
from __future__ import unicode_literals

import time
import redis
from django.conf import settings

from ominicontacto_app.models import QueueMember, Pausa
from ominicontacto_app.services.asterisk.redis_database import AgenteFamily
from ominicontacto_app.services.asterisk.asterisk_ami import AMIManagerConnector
from notification_app.notification import RedisStreamNotifier, AgentNotifier

import logging
logger = logging.getLogger(__name__)


class AgentActivityAmiManager(object):
    redis_connection = None

    def __init__(self, *args, **kwargs):
        self.manager = AMIManagerConnector()
        self.redis_stream_notifier = RedisStreamNotifier()

    def connect_manager(self):
        self.manager.connect()

    def disconnect_manager(self):
        self.manager.disconnect()

    def login_agent(self, agente_profile, manage_connection=False):
        # Solo actualiza el estado en Redis, sin ejecutar comandos AMI
        error = self._set_agent_redis_status(agente_profile, 'login')
        return error

    def logout_agent(self, agente_profile, manage_connection=False):
        # Solo actualiza el estado en Redis, sin ejecutar comandos AMI
        insert_redis_error = self._set_agent_redis_status(agente_profile, 'logout')
        return False, insert_redis_error

    def set_agent_ringing(self, agente_profile, ringing, manage_connection=False):
        # Sin conexión AMI; solo actualiza estado en Redis
        if ringing:
            insert_redis_error = self._set_agent_redis_status(agente_profile, 'RINGING')
        else:
            insert_redis_error = self._set_agent_redis_status(agente_profile, 'READY')
        return insert_redis_error

    def pause_agent(self, agente_profile, pause_id, manage_connection=False, supervisor=False):
        pause_name = ''
        if pause_id == '0':
            pause_name = 'ACW'
        elif pause_id == '00':
            pause_name = 'Supervision'
        elif pause_id == 'OW':
            pause_name = 'On Whatsapp'
        else:
            pause_name = Pausa.objects.activa_by_pauseid(pause_id).nombre

        # Solo actualiza el estado en Redis, sin ejecutar comandos AMI
        insert_redis_error = self._set_agent_pause_redis_status(
            agente_profile, pause_name, pause_id)

        if not insert_redis_error and supervisor:
            AgentNotifier().notify_pause(agente_profile.user.id, pause_id, pause_name)
        return False, insert_redis_error

    def unpause_agent(self, agente_profile, pause_id, manage_connection=False, supervisor=False):
        # Me aseguro q exista la pausa activa:
        if pause_id not in ('0', '00', 'OW'):
            pause_id = Pausa.objects.activa_by_pauseid(pause_id).id

        # Solo actualiza el estado en Redis, sin ejecutar comandos AMI
        insert_redis_error = self._set_agent_redis_status(agente_profile, 'unpause')
        if not insert_redis_error and supervisor:
            AgentNotifier().notify_unpause(agente_profile.user.id, pause_id)
        return False, insert_redis_error

    def set_agent_as_unavailable(self, agente_profile):
        self._set_agent_redis_status(agente_profile, 'UNAVAILABLE')

    def set_agent_as_disabled(self, agente_profile):
        self._set_agent_redis_status(agente_profile, 'DISABLED')

    def set_agent_as_ready(self, agente_profile):
        """
        Establece el estado del agente en READY sin realizar acciones sobre
        las colas de Asterisk. Solo actualiza el estado en Redis.
        """
        # Reutilizamos la semántica de 'login', que en Redis mapea a READY
        self._set_agent_redis_status(agente_profile, 'login')

    def hangup_current_call(self, agente_profile):
        # Django no conecta a Asterisk; hangup debe hacerse vía Redis/ACD si se implementa
        logger.debug(
            "hangup_current_call: omitido (sin conexión AMI); agente=%s",
            agente_profile.id,
        )
        return False

    def _get_family(self, agente_profile):
        agente_family = AgenteFamily()
        return agente_family._get_nombre_family(agente_profile)

    def _get_redis_status_data(self, action):
        status = action
        if action == 'login' or action == 'unpause':
            status = 'READY'
        elif action == 'logout':
            status = 'OFFLINE'
        elif 'PAUSE' in action:
            status = action
        elif 'UNAVAILABLE' in action:
            status = action
        elif 'DISABLE' in action:
            status = action
        return {
            'STATUS': status,
            'TIMESTAMP': str(int(time.time()))
        }

    def _get_queue_data(self, agente_profile):
        agent_id = agente_profile.id
        member_name = agente_profile.get_asterisk_caller_id()
        queues = QueueMember.objects.obtener_queue_por_agent(agent_id)
        penalties = QueueMember.objects.obtener_penalty_por_agent(agent_id)
        sip_extension = agente_profile.sip_extension
        interface = "PJSIP/" + str(sip_extension).strip('[]')
        content = [agent_id, member_name, queues, penalties, interface]
        return content

    def _queue_add_remove(self, agente_profile, action):
        # Sincronización con Asterisk la hace el ACD (p. ej. asterisk_transition.py)
        return False

    def _queue_pause_unpause(self, agente_profile, pause_id, action):
        # Sincronización con Asterisk la hace el ACD
        return False

    def _close_open_session(self, agente_profile):
        # Sin AMI; la sincronización de colas con Asterisk la hace el ACD
        return False

    def get_redis_connection(self):
        if self.redis_connection is None:
            self.redis_connection = redis.Redis(
                host=settings.REDIS_HOSTNAME,
                port=settings.CONSTANCE_REDIS_CONNECTION['port'],
                decode_responses=True)
        return self.redis_connection

    def _save_agent_data(self, agente_profile, data):
        error = False
        family = self._get_family(agente_profile)
        redis_connection = self.get_redis_connection()
        try:
            redis_connection.hset(family, mapping=data)
        except redis.exceptions.RedisError:
            error = True
        return error

    def _set_agent_redis_status(self, agente_profile, action):
        data = self._get_redis_status_data(action)
        if data['STATUS'] == 'READY' or (('PAUSE' in data['STATUS'])
                                         and ('ACW' not in data['STATUS'])):
            data['CAMPAIGN'] = ''
            data['CONTACT_NUMBER'] = ''
        return self._save_agent_data(agente_profile, data)

    def _set_agent_pause_redis_status(self, agente_profile, pause_name, pause_id):
        action = 'PAUSE-' + pause_name
        data = self._get_redis_status_data(action)
        data['PAUSE_ID'] = pause_id
        return self._save_agent_data(agente_profile, data)

    def _get_redis_agent_status(self, agente_profile):
        family = self._get_family(agente_profile)
        redis_connection = self.get_redis_connection()
        status = None
        error = False
        try:
            status = redis_connection.hget(family, 'STATUS')
            if status is None:
                error = True
        except redis.exceptions.RedisError:
            error = True

        return status, error
