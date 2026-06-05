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

from supervision_app.services.voicebot_stream_events import (
    build_upsert_event,
    stream_payload_str,
)


class RedisGearsService(object):
    SCRIPT_PATH = 'supervision_app/services/redisgears_action_scripts'
    AGENTES_TASK_ID = 'agentes'
    ENTRANTES_TASK_ID = 'entrantes'
    DIALERS_TASK_ID = 'dialers'
    VOICEBOTS_TASK_ID = 'voicebots'
    VOICEBOT_ACTIVE_KEY = 'OML:VOICEBOT-ACTIVE-CALLS:*'
    VOICEBOT_EVENT_DESC = 'sup_voicebot'

    def __init__(self):
        self.conn = redis.Redis(host=settings.REDIS_HOSTNAME,
                                port=settings.CONSTANCE_REDIS_CONNECTION['port'],
                                decode_responses=True)

    def registra_stream_supervisor(self, supervisor_id):
        self.__registra_evento_agente_change()
        self.__prepara_agentes_redis_gears(supervisor_id, self.AGENTES_TASK_ID)

    def registra_stream_supervisor_voicebots(self, supervisor_id):
        self.__reregistrar_evento_voicebot_active_change()
        self.__prepara_voicebots_redis_gears(supervisor_id, self.VOICEBOTS_TASK_ID)
        self.publicar_voicebots_activos_en_streams()

    def publicar_voicebots_activos_en_streams(self):
        """Republica llamadas activas al stream (útil tras re-registro del gear)."""
        stream_buffer = 100
        for key in self.conn.scan_iter(match='OML:VOICEBOT-ACTIVE-CALLS:*'):
            agent_id = key.rsplit(':', 1)[-1]
            agent_key = 'OML:AGENT:{0}'.format(agent_id)
            streams_raw = self.conn.hget(agent_key, 'VOICEBOT_STREAMS')
            if not streams_raw:
                continue
            streams = [s for s in streams_raw.split(',') if s]
            if not streams:
                continue
            active_calls = self.conn.hgetall(key) or {}
            for call_id, payload in active_calls.items():
                event = build_upsert_event(agent_id, call_id, payload)
                payload_str = stream_payload_str(event)
                for stream in streams:
                    try:
                        self.conn.xadd(
                            stream,
                            {'value': payload_str},
                            maxlen=stream_buffer,
                            approximate=True,
                        )
                    except Exception:
                        continue

    def registra_gears_supervision_global(self):
        """Registra gears globales de supervisión (idempotente)."""
        self.__registra_evento_agente_change()
        self.__registra_evento_voicebot_active_change()

    def sincroniza_voicebot_streams_todos_supervisores(self):
        """
        Ejecuta prepara_voicebots para cada OML:SUPERVISOR:{id},
        manteniendo VOICEBOT_STREAMS alineado sin depender de page load.
        """
        self.__registra_evento_voicebot_active_change()
        for key in self.conn.scan_iter(match='OML:SUPERVISOR:*'):
            supervisor_id = key.rsplit(':', 1)[-1]
            if not str(supervisor_id).isdigit():
                continue
            try:
                self.__prepara_voicebots_redis_gears(supervisor_id, self.VOICEBOTS_TASK_ID)
            except Exception:
                continue
        self.publicar_voicebots_activos_en_streams()

    def registra_stream_supervisor_entrantes(self, supervisor_id, campanas_ids, campanas_nombres):
        self.__registra_evento_agente_change()
        self.__prepara_agentes_redis_gears(supervisor_id, self.ENTRANTES_TASK_ID)

    def registra_stream_supervisor_dialers(self, supervisor_id):
        self.__registra_evento_agente_change()
        self.__prepara_agentes_redis_gears(supervisor_id, self.DIALERS_TASK_ID)

    def __prepara_agentes_redis_gears(self, supervisor_id, task_id):
        SCRIPT_NAME = 'prepara_agentes_para_stream_redis.py'
        script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r') \
            .read() % (task_id, supervisor_id)

        self.conn.execute_command("RG.PYEXECUTE", script)

    def __prepara_voicebots_redis_gears(self, supervisor_id, task_id):
        SCRIPT_NAME = 'prepara_voicebots_para_stream_redis.py'
        script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r') \
            .read() % (task_id, supervisor_id)

        self.conn.execute_command("RG.PYEXECUTE", script)

    def __registra_evento_agente_change(self):
        AGENTE_KEY = 'OML:AGENT:*'
        EVENT_DESC = 'sup_agent'
        SCRIPT_NAME = 'registrar_evento_agente_change.py'

        total_agentes = self._total_registros_x_clave(AGENTE_KEY)
        total_stream_buffer = total_agentes * 5

        if total_stream_buffer < 100:
            total_stream_buffer = 100

        if not self.__existe_evento_key_change(AGENTE_KEY, EVENT_DESC):
            script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r') \
                .read() % total_stream_buffer
            self.conn.execute_command("RG.PYEXECUTE", script)

    def __registra_evento_voicebot_active_change(self):
        SCRIPT_NAME = 'registrar_evento_voicebot_active_change.py'

        total_voicebots = self._total_registros_x_clave(self.VOICEBOT_ACTIVE_KEY)
        total_stream_buffer = total_voicebots * 5
        if total_stream_buffer < 100:
            total_stream_buffer = 100

        if not self.__existe_evento_key_change(self.VOICEBOT_ACTIVE_KEY, self.VOICEBOT_EVENT_DESC):
            script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r') \
                .read() % total_stream_buffer
            self.conn.execute_command("RG.PYEXECUTE", script)

    def __reregistrar_evento_voicebot_active_change(self):
        """Desregistra y vuelve a cargar sup_voicebot (necesario tras deploy del script)."""
        reg_id = self._id_registration(self.VOICEBOT_ACTIVE_KEY, self.VOICEBOT_EVENT_DESC)
        if reg_id is not None:
            try:
                self.conn.execute_command('RG.UNREGISTER', reg_id)
            except Exception:
                pass

        SCRIPT_NAME = 'registrar_evento_voicebot_active_change.py'
        total_voicebots = self._total_registros_x_clave(self.VOICEBOT_ACTIVE_KEY)
        total_stream_buffer = max(total_voicebots * 5, 100)
        script = open(f'{settings.BASE_DIR}/{self.SCRIPT_PATH}/{SCRIPT_NAME}', 'r') \
            .read() % total_stream_buffer
        self.conn.execute_command("RG.PYEXECUTE", script)

    def _id_registration(self, redis_key, desc):
        REGISTRATION_DATA = 7
        ARGS = 13
        REGEX = 1
        DESCRIPTION = 5
        ID = 1
        lista_eventos_registrados = self.conn.execute_command("RG.DUMPREGISTRATIONS")
        for evento in lista_eventos_registrados:
            if evento[REGISTRATION_DATA][ARGS][REGEX] == redis_key and evento[DESCRIPTION] == desc:
                return evento[ID]
        return None

    def __existe_evento_key_change(self, redis_key, desc):
        REGISTRATION_DATA = 7
        ARGS = 13
        REGEX = 1
        DESCRIPTION = 5
        lista_eventos_registrados = self.conn.execute_command("RG.DUMPREGISTRATIONS")
        for evento in lista_eventos_registrados:
            if evento[REGISTRATION_DATA][ARGS][REGEX] == redis_key and evento[DESCRIPTION] == desc:
                return True
        return False

    def _total_registros_x_clave(self, clave):
        command = f'GearsBuilder().count().run("{clave}")'
        res = self.conn.execute_command("RG.PYEXECUTE", command)
        try:
            total = int(res[0][0])
        except Exception:
            total = 0
        return total
