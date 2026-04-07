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
from ominicontacto_app.services.redis.connection import create_redis_connection

from django.utils.timezone import now, localtime
from django.db.models import Count

from ominicontacto_app.utiles import datetime_hora_minima_dia
from reportes_app.models import LlamadaResumen

logger = _logging.getLogger(__name__)


class CallDataGenerator(object):
    """  Regenera en Redis estadisticas de llamadas del día actual
         Las Estadísticas se usarán para efectuar cálculos más eficiente sin acceder a psql
    """
    # Keys de los valores en Redis a regenerar
    CALLDATA_CAMP_KEY = 'OML:CALLDATA:CAMP:{0}'
    CALLDATA_WAIT_KEY = 'OML:CALLDATA:WAIT-TIME:CAMP:{0}'
    CALLDATA_ABANDON_TIME = 'OML:CALLDATA:ABANDON-TIME:CAMP:{0}'
    # CALLDATA_AGENT_KEY = 'OML:CALLDATA:AGENT:{0}'
    CALLDATA_QUEUE_SIZE_KEY = 'OML:CALLDATA:QUEUE-SIZE:{0}'
    CALLDATA_QUEUE_KEY = 'OML:CALLDATA:QUEUE:{0}'
    WHATSAPP_CAMP_KEY = 'OML:WHATSAPP:CAMP:{0}'

    EVENTOS_FIN_CONEXION_ORIGINAL = [
        'COMPLETEAGENT', 'COMPLETEOUTNUM', 'BT-TRY', 'BTOUT-TRY',
        'CAMPT-COMPLETE', 'CAMPT-FAIL', 'COMPLETE-CAMPT', 'CT-COMPLETE', 'CTOUT-COMPLETE'
    ]
    EVENTOS_ABANDONO = ['ABANDON', 'ABANDONWEL']

    def __init__(self, redis_connection=None) -> None:
        self._redis_connection = redis_connection
        self._desde = None

    @property
    def redis_connection(self):
        if not self._redis_connection:
            self._redis_connection = create_redis_connection(2)
        return self._redis_connection

    def eliminar_datos(self):
        """ Eliminar Datos acumulativos del día """
        base_keys = [
            self.CALLDATA_CAMP_KEY,
            self.CALLDATA_WAIT_KEY,
            # self.CALLDATA_AGENT_KEY,
            self.WHATSAPP_CAMP_KEY,
            self.CALLDATA_ABANDON_TIME,
        ]
        for base_key in base_keys:
            keys = self.redis_connection.keys(base_key.format('*'))
            if keys:
                self.redis_connection.delete(*keys)

    def efectuar_cleanup_de_datos(self):
        """ Elimina datos acumulativos y de estado de colas """
        self.eliminar_datos()
        self.eliminar_datos_de_colas()

    def eliminar_datos_de_colas(self):
        """ Elimina datos de los estados de colas """
        base_keys = [self.CALLDATA_QUEUE_SIZE_KEY, self.CALLDATA_QUEUE_KEY]
        for base_key in base_keys:
            keys = self.redis_connection.keys(base_key.format('*'))
            if keys:
                self.redis_connection.delete(*keys)

    def regenerar(self):
        self.eliminar_datos()
        self.regenerar_eventos_por_campana()
        self.regenerar_wait_and_abandon_times()
        # Actualmente no se genera ni se usa esta estadística
        # self.regenerar_eventos_por_agente()

    @property
    def desde(self):
        if self._desde is None:
            hoy = localtime(now())
            self._desde = datetime_hora_minima_dia(hoy)
        return self._desde

    def regenerar_eventos_por_campana(self):
        """ Cantidad de ocurrencias de eventos "relevantes" en LlamadaResumen para cada campaña """
        # TODO: Filtrar eventos "relevantes únicamente"
        # Usar base de datos replica para optimizar consultas
        cantidades = LlamadaResumen.objects.using('replica')\
            .filter(fecha_fin__gt=self.desde)\
            .exclude(campana_id__isnull=True)\
            .values('campana_id', 'tipo_llamada', 'event')\
            .annotate(cantidad=Count('campana_id')).order_by('campana_id')
        eventos_por_campana = {}
        for cantidad in cantidades:
            campana_id = cantidad['campana_id']
            tipo_llamada = cantidad['tipo_llamada']
            evento = cantidad['event']
            # Filtrar valores None
            if campana_id is None or evento is None:
                continue
            key_evento = f'CALL_TYPE:{tipo_llamada}:{evento}'
            if campana_id not in eventos_por_campana:
                eventos_por_campana[campana_id] = {}
            eventos_por_campana[campana_id][key_evento] = cantidad['cantidad']

        for campana_id, eventos in eventos_por_campana.items():
            camp_key = self.CALLDATA_CAMP_KEY.format(campana_id)
            self.redis_connection.hset(camp_key, mapping=eventos)

    def regenerar_wait_and_abandon_times(self):
        wait_times_por_campana = {}
        abandon_times_por_campana = {}
        # Obtener llamadas con eventos de fin de conexión
        llamadas_fin = LlamadaResumen.objects.using('replica')\
            .filter(fecha_fin__gt=self.desde,
                    event__in=self.EVENTOS_FIN_CONEXION_ORIGINAL)\
            .exclude(agente_id=-1)\
            .exclude(campana_id__isnull=True)
        # Obtener llamadas con eventos de abandono
        llamadas_abandon = LlamadaResumen.objects.using('replica')\
            .filter(fecha_fin__gt=self.desde,
                    event__in=self.EVENTOS_ABANDONO)\
            .exclude(campana_id__isnull=True)
        
        for log in llamadas_fin:
            if log.event in self.EVENTOS_FIN_CONEXION_ORIGINAL and log.agente_id != -1:
                if log.campana_id is None:
                    continue
                if log.campana_id not in wait_times_por_campana:
                    wait_times_por_campana[log.campana_id] = []
                # bridge_wait_time es DecimalField en LlamadaResumen, convertir a int para Redis
                wait_time = int(float(log.bridge_wait_time)) if log.bridge_wait_time else 0
                wait_times_por_campana[log.campana_id].append(wait_time)
        
        for log in llamadas_abandon:
            if log.event in self.EVENTOS_ABANDONO:
                if log.campana_id is None:
                    continue
                if log.campana_id not in abandon_times_por_campana:
                    abandon_times_por_campana[log.campana_id] = []
                # bridge_wait_time es DecimalField en LlamadaResumen, convertir a int para Redis
                abandon_time = int(float(log.bridge_wait_time)) if log.bridge_wait_time else 0
                abandon_times_por_campana[log.campana_id].append(abandon_time)

        pipe = self.redis_connection.pipeline(transaction=False)

        for campana_id, wait_times in wait_times_por_campana.items():
            if wait_times:  # Solo agregar si hay valores
                key = self.CALLDATA_WAIT_KEY.format(campana_id)
                pipe.rpush(key, *wait_times)

        for campana_id, abandon_times in abandon_times_por_campana.items():
            if abandon_times:  # Solo agregar si hay valores
                key = self.CALLDATA_ABANDON_TIME.format(campana_id)
                pipe.rpush(key, *abandon_times)

        pipe.execute()
