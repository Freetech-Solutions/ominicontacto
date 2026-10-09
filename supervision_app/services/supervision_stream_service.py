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
from __future__ import unicode_literals

import json
import logging
import time

from django.conf import settings
import redis

from supervision_app.services.voicebot_stream_events import (
    VOICEBOT_FANOUT_LOCK_KEY,
    VOICEBOT_FANOUT_LOCK_RETRIES,
    VOICEBOT_FANOUT_LOCK_SLEEP,
    VOICEBOT_FANOUT_LOCK_TTL,
    VOICEBOT_SNAPSHOT_KEY,
    diff_voicebot_hash_events,
    stream_payload_str,
)

logger = logging.getLogger(__name__)


class SupervisionStreamService(object):
    """Prepara streams de supervisión y hace fan-out sin RedisGears."""

    AGENTES_TASK_ID = 'agentes'
    ENTRANTES_TASK_ID = 'entrantes'
    DIALERS_TASK_ID = 'dialers'
    VOICEBOTS_TASK_ID = 'voicebots'
    DEFAULT_STREAM_BUFFER = 100
    # Evita SCAN en cada XADD del hot path (H4).
    STREAM_BUFFER_CACHE_TTL = 30

    def __init__(self, conn=None):
        if conn is not None:
            self.conn = conn
        else:
            self.conn = redis.Redis(
                host=settings.REDIS_HOSTNAME,
                port=settings.CONSTANCE_REDIS_CONNECTION['port'],
                decode_responses=True,
            )
        self._stream_buffer_cache_until = 0
        self._stream_buffer_cache_value = self.DEFAULT_STREAM_BUFFER

    def registra_stream_supervisor(self, supervisor_id):
        self.prepara_agentes_para_stream(supervisor_id, self.AGENTES_TASK_ID)

    def registra_stream_supervisor_voicebots(self, supervisor_id):
        self.prepara_voicebots_para_stream(supervisor_id, self.VOICEBOTS_TASK_ID)
        self.publicar_voicebots_activos_en_streams()

    def registra_stream_supervisor_entrantes(
            self, supervisor_id, campanas_ids=None, campanas_nombres=None):
        self.prepara_agentes_para_stream(supervisor_id, self.ENTRANTES_TASK_ID)

    def registra_stream_supervisor_dialers(self, supervisor_id):
        self.prepara_agentes_para_stream(supervisor_id, self.DIALERS_TASK_ID)

    def sincroniza_voicebot_streams_todos_supervisores(self):
        """
        Ejecuta prepara_voicebots para cada OML:SUPERVISOR:{id},
        manteniendo VOICEBOT_STREAMS alineado sin depender de page load.
        """
        for key in self.conn.scan_iter(match='OML:SUPERVISOR:*'):
            supervisor_id = key.rsplit(':', 1)[-1]
            if not str(supervisor_id).isdigit():
                continue
            try:
                self.prepara_voicebots_para_stream(
                    supervisor_id, self.VOICEBOTS_TASK_ID)
            except Exception:
                logger.exception(
                    'Error preparando voicebot streams para supervisor %s',
                    supervisor_id,
                )
        self.publicar_voicebots_activos_en_streams()

    def sincroniza_campanas_agentes_todos_supervisores(self):
        """
        Copia grupo y campañas desde OML:SUPERVISOR:* hacia OML:AGENT:*.

        RedisGears reescribía CAMPANAS en cada escritura de la family del
        supervisor. Sin ese trigger, el panel sigue la lista congelada en el
        último page-load y un agente asignado a una campaña nueva solo aparece
        en las campañas que ya estaban en ese snapshot.
        """
        for key in self.conn.scan_iter(match='OML:SUPERVISOR:*'):
            supervisor_id = str(key).rsplit(':', 1)[-1]
            if not supervisor_id.isdigit():
                continue
            supervisor_hash = self.conn.hgetall(key) or {}
            for agent_id, metadata_json in supervisor_hash.items():
                self._sync_agent_campanas(agent_id, metadata_json)

    def refrescar_asignaciones_desde_db(self):
        """
        Regenera OML:SUPERVISOR desde DB y propaga CAMPANAS/VOICEBOT_STREAMS.

        Usado por el scheduler (~2 min) y por cambios inmediatos de asignación
        (H3) para no dejar el panel stale hasta el próximo tick/reload.
        """
        from reportes_app.reportes.reporte_supervisores import (
            ReporteSupervisoresFamily,
        )
        ReporteSupervisoresFamily().regenerar_families()
        self.sincroniza_campanas_agentes_todos_supervisores()
        self.sincroniza_voicebot_streams_todos_supervisores()
        # Tras recalcular membresía, sacar STREAMS huérfanos (M1).
        self.reconciliar_streams_membership()

    def _sync_agent_campanas(self, agent_id, metadata_json):
        agent_key = 'OML:AGENT:{0}'.format(agent_id)
        if not self.conn.exists(agent_key):
            return
        try:
            sup_value = json.loads(metadata_json)
        except (TypeError, ValueError):
            return
        campanas = str(sup_value.get('campana', []))
        grupo = sup_value.get('grupo', '') or ''
        current_campanas = self.conn.hget(agent_key, 'CAMPANAS') or ''
        current_grupo = self.conn.hget(agent_key, 'GROUP') or ''
        if current_campanas == campanas and current_grupo == grupo:
            return
        self.conn.hset(agent_key, mapping={
            'GROUP': grupo,
            'CAMPANAS': campanas,
            'id': str(agent_id),
        })
        self.publish_agent_to_streams(agent_id)

    def _prune_stream_from_agents(self, stream, field_name, keep_agent_ids):
        """
        Quita `stream` de field_name (STREAMS/VOICEBOT_STREAMS) en agentes
        que ya no deben publicarlo (M1).
        """
        keep_agent_ids = {str(agent_id) for agent_id in (keep_agent_ids or [])}
        try:
            for agent_key in self.conn.scan_iter(match='OML:AGENT:*'):
                agent_id = str(agent_key).rsplit(':', 1)[-1]
                if agent_id in keep_agent_ids:
                    continue
                raw = self.conn.hget(agent_key, field_name) or ''
                if not raw:
                    continue
                streams_list = [s for s in raw.split(',') if s]
                if stream not in streams_list:
                    continue
                streams_list = [s for s in streams_list if s != stream]
                self.conn.hset(agent_key, field_name, ','.join(streams_list))
        except Exception:
            logger.exception(
                'Error podando %s=%s de agentes fuera del set', field_name, stream)

    def reconciliar_streams_membership(self):
        """
        Alinea STREAMS/VOICEBOT_STREAMS con OML:SUPERVISOR actual (M1).

        Sin Gears, STREAMS solo se agregaba en page-load; un agente que deja
        de pertenecer al supervisor seguía publicando a paneles viejos.
        """
        expected_agent_streams = {}
        expected_vb_streams = {}
        try:
            for key in self.conn.scan_iter(match='OML:SUPERVISOR:*'):
                supervisor_id = str(key).rsplit(':', 1)[-1]
                if not supervisor_id.isdigit():
                    continue
                supervisor_hash = self.conn.hgetall(key) or {}
                human_ids = set()
                voicebot_ids = set()
                for agent_id in supervisor_hash.keys():
                    agent_id = str(agent_id)
                    agent_key = 'OML:AGENT:{0}'.format(agent_id)
                    if not self.conn.exists(agent_key):
                        continue
                    voicebot_flag = self.conn.hget(agent_key, 'VOICEBOT')
                    active_calls_key = 'OML:VOICEBOT-ACTIVE-CALLS:{0}'.format(
                        agent_id)
                    has_active_calls = self.conn.exists(active_calls_key) == 1
                    if voicebot_flag == '1' or has_active_calls:
                        voicebot_ids.add(agent_id)
                    if voicebot_flag != '1':
                        human_ids.add(agent_id)
                for task_id in (
                        self.AGENTES_TASK_ID,
                        self.ENTRANTES_TASK_ID,
                        self.DIALERS_TASK_ID):
                    stream = 'supervisor_{0}_{1}'.format(supervisor_id, task_id)
                    expected_agent_streams[stream] = set(human_ids)
                vb_stream = 'supervisor_{0}_{1}'.format(
                    supervisor_id, self.VOICEBOTS_TASK_ID)
                expected_vb_streams[vb_stream] = set(voicebot_ids)
        except Exception:
            logger.exception('Error construyendo membresía esperada de streams')
            return

        for stream, keep_ids in expected_agent_streams.items():
            self._prune_stream_from_agents(stream, 'STREAMS', keep_ids)
        for stream, keep_ids in expected_vb_streams.items():
            self._prune_stream_from_agents(stream, 'VOICEBOT_STREAMS', keep_ids)

        # Streams huérfanos (supervisor borrado): quitar de todos los agentes.
        known_agent_streams = set(expected_agent_streams.keys())
        known_vb_streams = set(expected_vb_streams.keys())
        try:
            for agent_key in self.conn.scan_iter(match='OML:AGENT:*'):
                for field_name, known in (
                        ('STREAMS', known_agent_streams),
                        ('VOICEBOT_STREAMS', known_vb_streams)):
                    raw = self.conn.hget(agent_key, field_name) or ''
                    if not raw:
                        continue
                    streams_list = [s for s in raw.split(',') if s]
                    filtered = [
                        s for s in streams_list
                        if not s.startswith('supervisor_') or s in known
                    ]
                    if filtered != streams_list:
                        self.conn.hset(
                            agent_key, field_name, ','.join(filtered))
        except Exception:
            logger.exception('Error podando streams de supervisores inexistentes')

    def _reset_supervision_stream(self, stream):
        """
        Vacía el stream sin borrar la key.

        Un DELETE deja un hueco donde publish_agent_to_streams (Django/ACD)
        ve exists=False y descarta el evento (race H1 en reload del panel).
        Con XTRIM la key permanece y los XADD concurrentes no se pierden;
        el seed posterior alinea el snapshot.
        """
        try:
            if self.conn.exists(stream):
                self.conn.xtrim(stream, maxlen=0, approximate=False)
            else:
                self.conn.xadd(stream, {'start': '{"value": "false"}'})
        except Exception:
            logger.exception(
                'Error reseteando stream %s; fallback delete+create', stream)
            try:
                self.conn.delete(stream)
                self.conn.xadd(stream, {'start': '{"value": "false"}'})
            except Exception:
                logger.exception(
                    'Fallback reset falló para stream %s', stream)

    def prepara_agentes_para_stream(self, supervisor_id, task_id):
        """
        Registra STREAMS y siembra el stream con el estado actual de cada agente.

        Sin RedisGears el HSET de CAMPANAS ya no dispara XADD: hay que publicar
        explícitamente o el panel queda vacío hasta el próximo cambio de estado.
        """
        supervisor_key = 'OML:SUPERVISOR:{0}'.format(supervisor_id)
        if not self.conn.exists(supervisor_key):
            return

        stream = 'supervisor_{0}_{1}'.format(supervisor_id, task_id)
        # Mantener la key viva durante todo el prepare (H1).
        self._reset_supervision_stream(stream)

        agents_to_seed = []
        supervisor_hash = self.conn.hgetall(supervisor_key) or {}
        for agent_id, metadata_json in supervisor_hash.items():
            agent_key = 'OML:AGENT:{0}'.format(agent_id)
            if not self.conn.exists(agent_key):
                continue

            voicebot_flag = self.conn.hget(agent_key, 'VOICEBOT')
            agent_streams = self.conn.hget(agent_key, 'STREAMS')
            agent_streams_list = agent_streams.split(',') if agent_streams else []

            if voicebot_flag == '1':
                if stream in agent_streams_list:
                    agent_streams_list.remove(stream)
                    self.conn.hset(
                        agent_key, 'STREAMS', ','.join(agent_streams_list))
                continue

            if stream not in agent_streams_list:
                agent_streams_list.append(stream)
                self.conn.hset(
                    agent_key, 'STREAMS', ','.join(agent_streams_list))

            agents_to_seed.append(agent_id)

            try:
                sup_value = json.loads(metadata_json)
            except (TypeError, ValueError):
                continue
            agent_group = sup_value.get('grupo', '')
            campanas = str(sup_value.get('campana', []))
            self.conn.hset(agent_key, mapping={
                'GROUP': agent_group,
                'CAMPANAS': campanas,
                'id': str(agent_id),
            })

        # M1: agentes que ya no están en este supervisor dejan de listar el stream.
        self._prune_stream_from_agents(stream, 'STREAMS', agents_to_seed)

        stream_buffer = max(
            len(agents_to_seed) * 5,
            self.stream_buffer_for_agents(),
        )
        for agent_id in agents_to_seed:
            self.publish_agent_to_streams(
                agent_id, stream_buffer=stream_buffer)

    def prepara_voicebots_para_stream(self, supervisor_id, task_id=None):
        if task_id is None:
            task_id = self.VOICEBOTS_TASK_ID
        supervisor_key = 'OML:SUPERVISOR:{0}'.format(supervisor_id)
        if not self.conn.exists(supervisor_key):
            return

        stream = 'supervisor_{0}_{1}'.format(supervisor_id, task_id)
        supervisor_hash = self.conn.hgetall(supervisor_key) or {}
        agents_keeping_stream = []

        for agent_id, metadata_json in supervisor_hash.items():
            agent_key = 'OML:AGENT:{0}'.format(agent_id)
            if not self.conn.exists(agent_key):
                continue

            voicebot_flag = self.conn.hget(agent_key, 'VOICEBOT')
            active_calls_key = 'OML:VOICEBOT-ACTIVE-CALLS:{0}'.format(agent_id)
            has_active_calls = self.conn.exists(active_calls_key) == 1
            if voicebot_flag != '1' and not has_active_calls:
                continue

            vb_streams = self.conn.hget(agent_key, 'VOICEBOT_STREAMS')
            vb_streams_list = vb_streams.split(',') if vb_streams else []
            if stream not in vb_streams_list:
                vb_streams_list.append(stream)
                self.conn.hset(
                    agent_key, 'VOICEBOT_STREAMS', ','.join(vb_streams_list))

            agents_keeping_stream.append(agent_id)

            try:
                sup_value = json.loads(metadata_json)
            except (TypeError, ValueError):
                continue
            agent_group = sup_value.get('grupo', '')
            campanas = str(sup_value.get('campana', []))
            mapping = {
                'GROUP': agent_group,
                'CAMPANAS': campanas,
                'id': str(agent_id),
            }
            if voicebot_flag != '1':
                mapping['VOICEBOT'] = '1'
            self.conn.hset(agent_key, mapping=mapping)

        self._prune_stream_from_agents(
            stream, 'VOICEBOT_STREAMS', agents_keeping_stream)

        if not self.conn.exists(stream):
            self.conn.xadd(stream, {'start': '{"value": "false"}'})

    def publicar_voicebots_activos_en_streams(self):
        """
        Republica llamadas activas vía el mismo path de diff+snapshot (H2).

        Evita upserts ciegos concurrentes con register/unregister que pueden
        pisar deletes o dejar el snapshot inconsistente.
        """
        stream_buffer = self.stream_buffer_for_agents()
        for key in self.conn.scan_iter(match='OML:VOICEBOT-ACTIVE-CALLS:*'):
            agent_id = str(key).rsplit(':', 1)[-1]
            try:
                self.publish_voicebot_active_calls_change(
                    agent_id, stream_buffer=stream_buffer)
            except Exception:
                logger.exception(
                    'Error republicando voicebot activo agente %s', agent_id)

    def stream_buffer_for_agents(self):
        """
        maxlen dinámico ≈ 5x agentes (mínimo DEFAULT).

        En CC grandes un maxlen fijo de 100 recorta el seed y deja el panel
        incompleto tras xrevrange (H4). Cache corto para no SCAN en cada XADD.
        """
        now = time.time()
        if now < self._stream_buffer_cache_until:
            return self._stream_buffer_cache_value
        total = 0
        try:
            for _ in self.conn.scan_iter(match='OML:AGENT:*'):
                total += 1
        except Exception:
            logger.exception('Error calculando stream_buffer_for_agents')
            return self._stream_buffer_cache_value
        value = max(total * 5, self.DEFAULT_STREAM_BUFFER)
        self._stream_buffer_cache_until = now + self.STREAM_BUFFER_CACHE_TTL
        self._stream_buffer_cache_value = value
        return value

    def publish_agent_to_streams(self, agent_id, agent_hash=None, stream_buffer=None):
        """Publica el hash del agente a cada stream listado en STREAMS."""
        agent_key = 'OML:AGENT:{0}'.format(agent_id)
        if agent_hash is None:
            agent_hash = self.conn.hgetall(agent_key) or {}
        if not agent_hash:
            return
        if agent_hash.get('VOICEBOT') == '1':
            return

        streams_raw = agent_hash.get('STREAMS') or ''
        streams = [s for s in streams_raw.split(',') if s]
        if not streams:
            return

        if stream_buffer is None:
            stream_buffer = self.stream_buffer_for_agents()

        payload = str(agent_hash)
        for stream in streams:
            if not self.conn.exists(stream):
                continue
            try:
                logger.info(
                    'publica estado agente=%s stream=%s status=%s timestamp=%s callid=%s',
                    agent_id,
                    stream,
                    agent_hash.get('STATUS'),
                    agent_hash.get('TIMESTAMP'),
                    agent_hash.get('CALLID'),
                )
                self.conn.xadd(
                    stream,
                    {'value': payload},
                    maxlen=stream_buffer,
                    approximate=True,
                )
            except Exception:
                logger.exception(
                    'Error publicando agente %s al stream %s', agent_id, stream)

    def _acquire_voicebot_fanout_lock(self, agent_id):
        lock_key = VOICEBOT_FANOUT_LOCK_KEY.format(agent_id=agent_id)
        for _ in range(VOICEBOT_FANOUT_LOCK_RETRIES):
            try:
                if self.conn.set(
                        lock_key, '1', nx=True, ex=VOICEBOT_FANOUT_LOCK_TTL):
                    return lock_key
            except Exception:
                logger.exception(
                    'Error adquiriendo lock fan-out voicebot %s', agent_id)
                return None
            time.sleep(VOICEBOT_FANOUT_LOCK_SLEEP)
        logger.warning(
            'Timeout adquiriendo lock fan-out voicebot %s; se omite publish',
            agent_id)
        return None

    def _release_voicebot_fanout_lock(self, lock_key):
        if not lock_key:
            return
        try:
            self.conn.delete(lock_key)
        except Exception:
            logger.exception('Error liberando lock fan-out %s', lock_key)

    def _write_voicebot_snapshot(self, snap_key, current):
        """Reemplaza el snapshot de forma atómica (delete + hset en pipeline)."""
        mapping = {}
        for call_id, payload in (current or {}).items():
            if isinstance(payload, dict):
                mapping[call_id] = json.dumps(payload)
            else:
                mapping[call_id] = payload
        pipe = self.conn.pipeline()
        pipe.delete(snap_key)
        if mapping:
            pipe.hset(snap_key, mapping=mapping)
        pipe.execute()

    def publish_voicebot_active_calls_change(self, agent_id, stream_buffer=None):
        """
        Diff snapshot vs hash actual de llamadas activas y publica upsert/delete.

        Serializa por agente con lock Redis para evitar races register/unregister
        vs scheduler (H2): delete perdido o upsert duplicado sobre snapshot.
        """
        agent_id = str(agent_id)
        agent_key = 'OML:AGENT:{0}'.format(agent_id)
        streams = self._voicebot_streams_for_agent(agent_key, agent_id)
        if not streams:
            return

        if stream_buffer is None:
            stream_buffer = self.stream_buffer_for_agents()

        lock_key = self._acquire_voicebot_fanout_lock(agent_id)
        if not lock_key:
            return

        try:
            snap_key = VOICEBOT_SNAPSHOT_KEY.format(agent_id=agent_id)
            previous = self.conn.hgetall(snap_key) or {}
            current_key = 'OML:VOICEBOT-ACTIVE-CALLS:{0}'.format(agent_id)
            current = self.conn.hgetall(current_key) or {}

            events = diff_voicebot_hash_events(agent_id, previous, current)
            for event in events:
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

            self._write_voicebot_snapshot(snap_key, current)
        finally:
            self._release_voicebot_fanout_lock(lock_key)

    def _voicebot_streams_for_agent(self, agent_key, agent_id):
        raw = self.conn.hget(agent_key, 'VOICEBOT_STREAMS')
        if raw:
            streams = [s for s in raw.split(',') if s]
            if streams:
                return streams

        streams = []
        agent_id_str = str(agent_id)
        for sup_key in self.conn.scan_iter(match='OML:SUPERVISOR:*'):
            if not self.conn.hexists(sup_key, agent_id_str):
                continue
            sup_id = sup_key.rsplit(':', 1)[-1]
            stream = 'supervisor_{0}_voicebots'.format(sup_id)
            if stream not in streams:
                streams.append(stream)
            existing = self.conn.hget(agent_key, 'VOICEBOT_STREAMS')
            vb_list = existing.split(',') if existing else []
            if stream not in vb_list:
                vb_list.append(stream)
                self.conn.hset(agent_key, 'VOICEBOT_STREAMS', ','.join(vb_list))
        return streams
