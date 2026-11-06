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
from django.conf import settings
import redis


class RedisGearsService(object):
    SCRIPT_PATH = 'supervision_app/services/redisgears_action_scripts'
    AGENTES_TASK_ID = 'agentes'
    ENTRANTES_TASK_ID = 'entrantes'
    SALIENTES_TASK_ID = 'salientes'
    DIALERS_TASK_ID = 'dialers'
    EVENTOS_SUPERVISION = ('sup_agent', 'sup_entrantes', 'sup_salientes', 'sup_dialers')
    # Listas de streams suscriptos a cada agente / campaña (campo STREAMS de cada hash)
    AGENTE_STREAMS_PREFIX = 'OML:AGENT:'
    ENTRANTES_STREAMS_PREFIX = 'OML:SUPERVISION_CAMPAIGN_STREAMS:'
    SALIENTES_STREAMS_PREFIX = 'OML:SUPERVISION_SALIENTE_STREAMS:'
    DIALERS_STREAMS_PREFIX = 'OML:SUPERVISION_DIALER_STREAMS:'
    # Agentes visibles por cada supervisor (lo regenera el cron actualizar_reporte_supervisores)
    AGENTES_DE_SUPERVISOR_PREFIX = 'OML:SUPERVISOR:'
    SCAN_COUNT = 1000

    def __init__(self):
        self.conn = redis.Redis(host=settings.REDIS_HOSTNAME,
                                port=settings.CONSTANCE_REDIS_CONNECTION['port'],
                                decode_responses=True)

    def registra_stream_supervisor(self, supervisor_id):
        self.__limpia_stream_supervisor(supervisor_id, self.AGENTES_TASK_ID)
        self.__depura_suscripciones_agentes(supervisor_id, self.AGENTES_TASK_ID)
        self.__registra_evento_agente_change()
        self.__prepara_agentes_redis_gears(supervisor_id, self.AGENTES_TASK_ID)

    def registra_stream_supervisor_entrantes(self, supervisor_id, campanas_ids):
        self.__limpia_stream_supervisor(supervisor_id, self.ENTRANTES_TASK_ID)
        self.__depura_suscripciones_agentes(supervisor_id, self.ENTRANTES_TASK_ID)
        self.__depura_suscripciones_campanas(
            supervisor_id, self.ENTRANTES_TASK_ID, self.ENTRANTES_STREAMS_PREFIX, campanas_ids)
        self.__registra_evento_agente_change()
        self.__prepara_agentes_redis_gears(supervisor_id, self.ENTRANTES_TASK_ID)
        self.__registra_evento_supervision_entrantes_change()
        self.__prepara_supervision_entrantes_redis_gears(
            supervisor_id, self.ENTRANTES_TASK_ID, campanas_ids)

    def registra_stream_supervisor_salientes(self, supervisor_id, campanas_ids):
        self.__limpia_stream_supervisor(supervisor_id, self.SALIENTES_TASK_ID)
        self.__depura_suscripciones_campanas(
            supervisor_id, self.SALIENTES_TASK_ID, self.SALIENTES_STREAMS_PREFIX, campanas_ids)
        self.__registra_evento_supervision_salientes_change()
        self.__prepara_supervision_salientes_redis_gears(
            supervisor_id, self.SALIENTES_TASK_ID, campanas_ids)

    def registra_stream_supervisor_dialers(self, supervisor_id, campanas_ids):
        self.__limpia_stream_supervisor(supervisor_id, self.DIALERS_TASK_ID)
        self.__depura_suscripciones_agentes(supervisor_id, self.DIALERS_TASK_ID)
        self.__depura_suscripciones_campanas(
            supervisor_id, self.DIALERS_TASK_ID, self.DIALERS_STREAMS_PREFIX, campanas_ids)
        self.__registra_evento_agente_change()
        self.__prepara_agentes_redis_gears(supervisor_id, self.DIALERS_TASK_ID)
        self.__registra_evento_supervision_dialers_change()
        self.__prepara_supervision_dialers_redis_gears(
            supervisor_id, self.DIALERS_TASK_ID, campanas_ids)

    def __limpia_stream_supervisor(self, supervisor_id, task_id):
        # Los datos ya publicados no sirven: los scripts prepara_* vuelven a publicar
        # el estado actual de cada agente/campaña. Se vacía (sin borrar la clave) antes
        # de correrlos, una sola vez, porque agentes y campañas comparten el stream.
        stream = f'supervisor_{supervisor_id}_{task_id}'
        self.conn.xtrim(stream, maxlen=0, approximate=False)

    def __depura_suscripciones_agentes(self, supervisor_id, task_id):
        """Quita el stream de los agentes que el supervisor ya no tiene asignados"""
        agentes_permitidos = set(
            self.conn.hkeys(f'{self.AGENTES_DE_SUPERVISOR_PREFIX}{supervisor_id}'))
        self.__depura_suscripciones(
            f'supervisor_{supervisor_id}_{task_id}', self.AGENTE_STREAMS_PREFIX,
            agentes_permitidos)

    def __depura_suscripciones_campanas(self, supervisor_id, task_id, prefijo, campanas_ids):
        """Quita el stream de las campañas que el supervisor ya no tiene asignadas"""
        campanas_permitidas = {camp_id for camp_id in campanas_ids.split(',') if camp_id}
        self.__depura_suscripciones(
            f'supervisor_{supervisor_id}_{task_id}', prefijo, campanas_permitidas)

    def __depura_suscripciones(self, stream, prefijo, ids_permitidos):
        # Deny by default: el stream solo queda suscripto a los recursos permitidos ahora.
        # Devuelve la cantidad de listas de las que se quitó el stream.
        quitados = 0
        for clave in self.conn.scan_iter(match=f'{prefijo}*', count=self.SCAN_COUNT,
                                         _type='HASH'):
            if clave[len(prefijo):] not in ids_permitidos:
                quitados += self.__quita_stream_de_lista(clave, stream)
        return quitados

    def __quita_stream_de_lista(self, clave, stream):
        # WATCH para no pisar a otro supervisor que se suscriba al mismo tiempo
        with self.conn.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(clave)
                    streams = pipe.hget(clave, 'STREAMS')
                    lista = streams.split(',') if streams else []
                    if stream not in lista:
                        pipe.unwatch()
                        return 0
                    restantes = [s for s in lista if s != stream]
                    pipe.multi()
                    if restantes:
                        pipe.hset(clave, 'STREAMS', ','.join(restantes))
                    else:
                        pipe.hdel(clave, 'STREAMS')
                    pipe.execute()
                    return 1
                except redis.WatchError:
                    continue

    def __prepara_agentes_redis_gears(self, supervisor_id, task_id):
        SCRIPT_NAME = 'prepara_agentes_para_stream_redis.py'
        script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r') \
            .read() % (task_id, supervisor_id)

        self.conn.execute_command("RG.PYEXECUTE", script)

    def __registra_evento_agente_change(self):
        AGENTE_KEY = 'OML:AGENT:*'
        EVENT_DESC = 'sup_agent'
        SCRIPT_NAME = 'registrar_evento_agente_change.py'

        if not self.__existe_evento_key_change(AGENTE_KEY, EVENT_DESC):
            total_stream_buffer = self._tamano_buffer_stream(AGENTE_KEY)
            script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r') \
                .read() % total_stream_buffer
            self.conn.execute_command("RG.PYEXECUTE", script)

    def __registra_evento_supervision_entrantes_change(self):
        SUP_CAMPAIGN_KEY = 'OML:SUPERVISION_CAMPAIGN:*'
        EVENT_DESC = 'sup_entrantes'
        SCRIPT_NAME = 'registrar_evento_supervision_entrantes.py'
        if not self.__existe_evento_key_change(SUP_CAMPAIGN_KEY, EVENT_DESC):
            total_stream_buffer = self._tamano_buffer_stream(SUP_CAMPAIGN_KEY)
            script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r').read() \
                % (total_stream_buffer, SUP_CAMPAIGN_KEY)
            self.conn.execute_command("RG.PYEXECUTE", script)

    def __registra_evento_supervision_salientes_change(self):
        SUP_CAMPAIGN_KEY = 'OML:SUPERVISION_SALIENTE:*'
        EVENT_DESC = 'sup_salientes'
        SCRIPT_NAME = 'registrar_evento_supervision_salientes.py'
        if not self.__existe_evento_key_change(SUP_CAMPAIGN_KEY, EVENT_DESC):
            script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r').read() \
                % SUP_CAMPAIGN_KEY
            self.conn.execute_command("RG.PYEXECUTE", script)

    def __registra_evento_supervision_dialers_change(self):
        SUP_CAMPAIGN_KEY = 'OML:SUPERVISION_DIALER:*'
        EVENT_DESC = 'sup_dialers'
        SCRIPT_NAME = 'registrar_evento_supervision_dialers.py'
        if not self.__existe_evento_key_change(SUP_CAMPAIGN_KEY, EVENT_DESC):
            total_stream_buffer = self._tamano_buffer_stream(SUP_CAMPAIGN_KEY)
            script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r').read() \
                % (total_stream_buffer, SUP_CAMPAIGN_KEY)
            self.conn.execute_command("RG.PYEXECUTE", script)

    def __prepara_supervision_entrantes_redis_gears(self, supervisor_id, stream_task_id,
                                                    campanas_ids):
        SCRIPT_NAME = 'prepara_supervision_entrantes_para_stream_redis.py'
        script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r').read() \
            % (campanas_ids, stream_task_id, supervisor_id)

        self.conn.execute_command("RG.PYEXECUTE", script)

    def __prepara_supervision_salientes_redis_gears(self, supervisor_id, stream_task_id,
                                                    campanas_ids):
        SCRIPT_NAME = 'prepara_supervision_salientes_para_stream_redis.py'
        script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r').read() \
            % (campanas_ids, stream_task_id, supervisor_id)

        self.conn.execute_command("RG.PYEXECUTE", script)

    def __prepara_supervision_dialers_redis_gears(self, supervisor_id, stream_task_id,
                                                  campanas_ids):
        SCRIPT_NAME = 'prepara_supervision_dialers_para_stream_redis.py'
        script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r').read() \
            % (campanas_ids, stream_task_id, supervisor_id)

        self.conn.execute_command("RG.PYEXECUTE", script)

    def da_de_baja_eventos_supervision(self):
        """
        Da de baja en RedisGears solo los eventos de supervisión (EVENTOS_SUPERVISION).
        Se vuelven a registrar, con los scripts registrar_evento_* vigentes, la próxima vez
        que un supervisor entra a la pantalla que los usa. Mientras tanto no se publican
        eventos en los streams. Devuelve la cantidad de registros dados de baja.
        """
        bajas = 0
        for registro_id, _, desc in list(self.__eventos_registrados()):
            if desc in self.EVENTOS_SUPERVISION:
                self.conn.execute_command("RG.UNREGISTER", registro_id)
                bajas += 1
        return bajas

    def limpia_streams_supervisores(self):
        """Vacía todos los streams de supervisión. Devuelve la cantidad de entradas borradas."""
        borradas = 0
        for stream in self.conn.scan_iter(match='supervisor_*', _type='STREAM'):
            borradas += self.conn.xtrim(stream, maxlen=0, approximate=False)
        return borradas

    def __eventos_registrados(self):
        ID = 1
        DESCRIPTION = 5
        REGISTRATION_DATA = 7
        ARGS = 13
        REGEX = 1
        for evento in self.conn.execute_command("RG.DUMPREGISTRATIONS"):
            yield evento[ID], evento[REGISTRATION_DATA][ARGS][REGEX], evento[DESCRIPTION]

    def __existe_evento_key_change(self, redis_key, desc):
        return any(regex == redis_key and descripcion == desc
                   for _, regex, descripcion in self.__eventos_registrados())

    def _tamano_buffer_stream(self, clave):
        # Margen para varias actualizaciones por registro (agente/campaña) entre lecturas
        return max(self._total_registros_x_clave(clave) * 5, 100)

    def _total_registros_x_clave(self, clave):
        command = f'GearsBuilder().count().run("{clave}")'
        res = self.conn.execute_command("RG.PYEXECUTE", command)
        try:
            total = int(res[0][0])
        except Exception:
            total = 0
        return total
