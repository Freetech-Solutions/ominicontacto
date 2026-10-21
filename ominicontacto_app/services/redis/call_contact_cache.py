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

import logging as _logging
import redis
from redis.exceptions import RedisError, ConnectionError

from django.conf import settings
from django.utils.timezone import datetime, timedelta

logger = _logging.getLogger(__name__)


class CallContactCache(object):
    """  Permite guardar en Redis durante 2 horas el id_contacto relacionado a un callid
    """
    KEY = 'OML:CALL_CONTACT_CACHE:{0}'
    KEY_EXPIRE = 60 * 60 * 2  # Datos expiran en 2 horas

    def __init__(self, redis_connection=None):
        self.redis_connection = redis_connection

    def get_redis_connection(self):
        if not self.redis_connection:
            self.redis_connection = redis.Redis(
                host=settings.REDIS_HOSTNAME,
                port=settings.CONSTANCE_REDIS_CONNECTION['port'],
                decode_responses=True)
        return self.redis_connection

    def get_hour_key(self, hour):
        return self.KEY.format(hour)

    def set_call_contact_id(self, callid, contact_id):
        hour = datetime.utcnow().hour
        redis_connection = self.get_redis_connection()
        hour_key = self.get_hour_key(hour)
        try:
            redis_connection.hset(hour_key, callid, contact_id)
            # Guardo datos de llamadas de la hora actual solamente por 2 horas
            redis_connection.expire(hour_key, self.KEY_EXPIRE)
            return
        except RedisError as e:
            raise e
        except ConnectionError as e:
            logger.exception(e)

    @classmethod
    def link_call_to_contact(cls, callid, contact_id, redis_connection=None):
        """
        Asocia callid → contact_id si ambos son válidos.

        Usado por APIs de calificación (voicebot / new_contact) para que, en handoff
        con id_contacto=-1, calificar_llamada resuelva el contacto sin caer en
        contactos_telefono_repetido.
        """
        if callid is None or contact_id is None:
            return False
        callid_str = str(callid).strip()
        contact_str = str(contact_id).strip()
        if not callid_str or not contact_str or contact_str in ('-1', '0', 'None', 'null'):
            return False
        try:
            cls(redis_connection=redis_connection).set_call_contact_id(
                callid_str, contact_str
            )
            logger.info(
                'CallContactCache: callid=%s → contact_id=%s',
                callid_str,
                contact_str,
            )
            return True
        except Exception:
            logger.exception(
                'CallContactCache: no se pudo asociar callid=%s contact_id=%s',
                callid_str,
                contact_str,
            )
            return False

    def get_call_contact_id(self, callid):
        time = datetime.utcnow()
        hour = time.hour
        # Busco contact_id para el callid en la KEY correspondiente a la hora actual
        contact_id = self.get_call_contact_id_at(callid, hour)
        if contact_id is None:
            # Si no la encuentro busco en la hora anterior
            previous_hour = (time - timedelta(hours=1)).hour % 24
            return self.get_call_contact_id_at(callid, previous_hour)
        return contact_id

    def get_call_contact_id_at(self, callid, hour):
        redis_connection = self.get_redis_connection()
        hour_key = self.get_hour_key(hour)
        try:
            return redis_connection.hget(hour_key, callid)
        except RedisError as e:
            raise e
        except ConnectionError as e:
            logger.exception(e)
