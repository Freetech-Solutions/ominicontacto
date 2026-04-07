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
import logging as _logging
from datetime import date
from redis.exceptions import RedisError
from ominicontacto_app.services.redis.connection import create_redis_connection
from ominicontacto_app.models import CalificacionCliente
from ominicontacto_app.models import OpcionCalificacion
from django.db import models

logger = _logging.getLogger(__name__)

DISPOSITIONS_EVENTS_CHANNEL = 'OML:CHANNEL:DISPOSITIONEVENTS'
DISPOSITIONDATA_CAMP_KEY = 'OML:DISPOSITIONDATA:CAMP:{0}'


class CampaignDispositionsCache:

    def __init__(self, redis_connection=None):
        self._redis_connection = redis_connection

    @property
    def redis_connection(self):
        if self._redis_connection is None:
            self._redis_connection = create_redis_connection(db=2)
        return self._redis_connection

    def record_disposition(self, campaign_id, is_engaged, has_previous_different=False):
        key = DISPOSITIONDATA_CAMP_KEY.format(campaign_id)
        try:
            self.redis_connection.hincrby(key, 'ENGAGED' if is_engaged else 'NOT-ENGAGED', 1)
            if has_previous_different:
                self.redis_connection.hincrby(key, 'NOT-ENGAGED' if is_engaged else 'ENGAGED', -1)
            self._notify_dispositiondata_event({
                'engaged': is_engaged,
                'id': campaign_id,
                'type': 'DISPOSITION',
                'has_previous_different': has_previous_different,
            })
        except RedisError as e:
            logger.error("Redis record_disposition error: %s", e)

    def eliminar_datos(self):
        base_keys = [
            DISPOSITIONDATA_CAMP_KEY,
        ]
        for base_key in base_keys:
            keys = self.redis_connection.keys(base_key.format('*'))
            if keys:
                self.redis_connection.delete(*keys)

    def regenerar_dispositions_por_campana(self):
        queryset = CalificacionCliente.objects.filter(
            modified__date=date.today(),
        ).annotate(
            campaign_id=models.F("opcion_calificacion__campana_id"),
            is_engaged=models.ExpressionWrapper(
                models.Q(opcion_calificacion__tipo=OpcionCalificacion.GESTION),
                models.BooleanField()
            ),
        ).values_list(
            "campaign_id",
            "is_engaged",
        )
        for campaign_id, is_engaged in queryset:
            self.record_disposition(campaign_id, is_engaged)

    def regenerar(self):
        self.eliminar_datos()
        self.regenerar_dispositions_por_campana()

    def _notify_dispositiondata_event(self, event_data):
        try:
            self.redis_connection.publish(DISPOSITIONS_EVENTS_CHANNEL, json.dumps(event_data))
        except RedisError as e:
            logger.error("Redis _notify_dispositiondata_event error: %s", e)
