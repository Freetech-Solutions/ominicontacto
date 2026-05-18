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

import time as time_module
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils.timezone import now

from reportes_app.models import ActividadAgenteLog, AgentActivityEventV2
from reportes_app.agent_activity_dual_write import (
    write_agent_activity_event_v2,
    write_agent_activity_event_v2_synthetic,
    SOURCE_SESSION_EXPIRED,
)
from ominicontacto_app.services.redis.connection import create_redis_connection

# Cooldown in ms; LOGOUT -> LOGIN within this window is treated as reconnection.
COOLDOWN_MS = getattr(settings, 'PRESENCE_LOG_RECONNECT_COOLDOWN_MS', 1500)

# Redis key for debounce: hash with last_event_type, last_event_ts (ms).
DEBOUNCE_KEY_TEMPLATE = 'OML:PRESENCE_LOG_DEBOUNCE:{0}'
# Redis key for agent status (must match AgenteFamily / OML:AGENT:{id}).
AGENT_STATUS_KEY_TEMPLATE = 'OML:AGENT:{0}'
HEARTBEAT_KEY_TEMPLATE = 'OML:PRESENCE:HB:{0}:{1}'
HEARTBEAT_LEADER_KEY_TEMPLATE = 'OML:PRESENCE:HB:LEADER:{0}:{1}'
HEARTBEAT_TIMEOUT_GUARD_KEY_TEMPLATE = 'OML:PRESENCE:HB:TIMEOUT_GUARD:{0}'


class AgentPresenceManager(object):
    """
    Clase que se encarga de manejar los eventos relativos a la presencia y el
    estado del agente.
    Idempotencia:
    - SESSION_LOGIN: si V2 tiene presencia cerrada (último SESSION_LOGOUT), siempre
      insertar aunque Redis indique online (evita desincronización tras SESS_EXPIRED).
      Si V2 está abierta: Redis (agente ya online/logged-in => no insertar) + cooldown
      configurable (PRESENCE_LOG_RECONNECT_COOLDOWN_MS) para evitar login/logout/login
      en milisegundos. Redis puede actualizarse después del login en algunos flujos.
    - SESSION_LOGOUT: solo Postgres (no Redis). El flujo llama primero a logout_agent()
      (Redis OFFLINE) y luego presence_manager.logout(). Antes de insertar se consulta
      el último evento del agente; si es SESSION_LOGOUT o REMOVEMEMBER => no insertar.
    - UNPAUSEALL: siempre se persiste con pausa_id=NULL en legacy.
    Si Redis no está disponible al evaluar reglas de LOGIN, se inserta el evento (fallback).
    TODO:
    - Hacerse cargo de la funcionalidad de
      ominicontacto_app/services/asterisk/agent_activity.AgentActivityAmiManager
    - Desacoplar el manejo de la presencia en Redis de AgentActivityAmiManager
      en un nuevo servicio AgentRedisPresenceManager
    - Solo este componente deberá usar dicho servicio
    """

    def login(self, agente, time=None):
        self._append_event(agente, ActividadAgenteLog.SESSION_LOGIN, pausa_id=None, time=time)

    def logout(self, agente, time=None):
        self._append_event(agente, ActividadAgenteLog.SESSION_LOGOUT, pausa_id=None, time=time)

    def pause(self, agente, pausa_id, time=None):
        self._append_event(agente, ActividadAgenteLog.PAUSE, pausa_id=pausa_id, time=time)

    def unpause(self, agente, pausa_id, time=None):
        # UNPAUSEALL must never persist pausa_id (semantic normalization).
        self._append_event(agente, ActividadAgenteLog.UNPAUSE, pausa_id=None, time=time)

    def _append_event(self, agente, event, pausa_id=None, time=None):
        # Normalize UNPAUSE: never persist pausa_id.
        if event == ActividadAgenteLog.UNPAUSE:
            pausa_id = None

        if event in (ActividadAgenteLog.SESSION_LOGIN, ActividadAgenteLog.SESSION_LOGOUT):
            if not self._should_persist_session_event(agente, event):
                return

        ts = time if time is not None else now()
        write_agent_activity_event_v2(
            agente_id=agente.id,
            event=event,
            pausa_id=pausa_id,
            ts=ts,
        )

        if event in (ActividadAgenteLog.SESSION_LOGIN, ActividadAgenteLog.SESSION_LOGOUT):
            self._update_debounce_redis(agente.id, event)

    def _get_ultimo_evento_v2_agente(self, agente_id):
        """Último evento V2 del agente (ORDER BY ts DESC, id DESC LIMIT 1)."""
        return AgentActivityEventV2.objects.filter(
            agente_id=agente_id
        ).order_by('-ts', '-id').first()

    def is_presence_open_v2(self, agente_id):
        """
        Presencia abierta basada en V2.
        - False si el último evento es SESSION_LOGOUT
        - True en cualquier otro caso.
        - Si no hay eventos V2, retorna True para no bloquear el flujo legado.
        """
        last_event = self._get_ultimo_evento_v2_agente(agente_id)
        if last_event is None:
            return True
        return last_event.event_type != AgentActivityEventV2.EventType.SESSION_LOGOUT

    def should_redirect_by_closed_presence(self, agente_id):
        """
        True cuando la presencia está cerrada en V2 y se debe redirigir al login.
        """
        return not self.is_presence_open_v2(agente_id)

    def has_recent_synthetic_logout(self, agente_id, source, within_seconds):
        """
        True si existe un SESSION_LOGOUT sintético reciente para el agente.
        """
        if within_seconds <= 0:
            return False
        since = now() - timedelta(seconds=within_seconds)
        return AgentActivityEventV2.objects.filter(
            agente_id=agente_id,
            event_type=AgentActivityEventV2.EventType.SESSION_LOGOUT,
            source=source,
            ts__gte=since,
        ).exists()

    def close_presence_session_v2(self, agente_id, ts, source, metadata=None):
        """
        Cierra presencia solo en V2 con un SESSION_LOGOUT sintético.
        """
        write_agent_activity_event_v2_synthetic(
            agente_id=agente_id,
            event_type=AgentActivityEventV2.EventType.SESSION_LOGOUT,
            ts=ts,
            source=source,
            metadata=metadata or {},
        )

    @staticmethod
    def get_heartbeat_key(agente_id, browser_id):
        return HEARTBEAT_KEY_TEMPLATE.format(agente_id, browser_id)

    @staticmethod
    def get_heartbeat_leader_key(agente_id, browser_id):
        return HEARTBEAT_LEADER_KEY_TEMPLATE.format(agente_id, browser_id)

    @staticmethod
    def get_heartbeat_timeout_guard_key(agente_id):
        return HEARTBEAT_TIMEOUT_GUARD_KEY_TEMPLATE.format(agente_id)

    def _should_persist_session_event(self, agente, event):
        """Returns True if the session event should be persisted (idempotency + cooldown)."""
        if event == ActividadAgenteLog.SESSION_LOGOUT:
            # Idempotencia: logout_agent() pone Redis OFFLINE antes de llamar a
            # presence_manager.logout(), por tanto se consulta el último evento V2.
            ultimo = self._get_ultimo_evento_v2_agente(agente.id)
            if ultimo and ultimo.event_type == AgentActivityEventV2.EventType.SESSION_LOGOUT:
                return False
            return True

        if event == ActividadAgenteLog.SESSION_LOGIN:
            # La consola usa V2 como fuente de verdad; no omitir LOGIN si V2 está cerrada
            # aunque Redis conserve STATUS stale (p. ej. tras close_presence_session_v2).
            if not self.is_presence_open_v2(agente.id):
                return True
            try:
                redis_conn = create_redis_connection()
                status = redis_conn.hget(AGENT_STATUS_KEY_TEMPLATE.format(agente.id), 'STATUS')
            except Exception:
                return True
            logged_in = status and status in ('READY', 'RINGING') or (
                status and status.startswith('PAUSE-'))
            if logged_in:
                return False
            if self._is_reconnect_within_cooldown(agente.id):
                return False
        return True

    def _is_reconnect_within_cooldown(self, agente_id):
        """True if last persisted session event was LOGOUT and within COOLDOWN_MS."""
        try:
            redis_conn = create_redis_connection()
            key = DEBOUNCE_KEY_TEMPLATE.format(agente_id)
            last_type = redis_conn.hget(key, 'last_event_type')
            last_ts = redis_conn.hget(key, 'last_event_ts')
        except Exception:
            return False
        if last_type != ActividadAgenteLog.SESSION_LOGOUT or not last_ts:
            return False
        try:
            last_ms = int(last_ts)
        except (TypeError, ValueError):
            return False
        now_ms = int(time_module.time() * 1000)
        return (now_ms - last_ms) < COOLDOWN_MS

    def _update_debounce_redis(self, agente_id, event):
        """Store last session event type and timestamp (ms) for cooldown."""
        try:
            redis_conn = create_redis_connection()
            key = DEBOUNCE_KEY_TEMPLATE.format(agente_id)
            redis_conn.hset(key, mapping={
                'last_event_type': event,
                'last_event_ts': str(int(time_module.time() * 1000)),
            })
        except Exception:
            pass

    def enforce_login(self, agente):
        # Legacy no-op: se conserva por compatibilidad de llamada en vistas.
        # La decisión de redirección se evalúa con should_redirect_by_closed_presence().
        return self.should_redirect_by_closed_presence(agente.id)

    def fix_previous_open_session_logs(self, user, agente):
        """ Fix de Logs al momento de hacer Login (antes de self.login) """
        """ Para ser usado al momento de hacer Login unicamente """
        try:
            # Si existe la Session y se está haciendo login, puede tener logs sin cierre de sesion
            # Por expiracion o por iniciar sesion en otro navegador.
            session = Session.objects.get(session_key=user.last_session_key)
            fecha_cierre = min(session.expire_date, now())
            if self.is_presence_open_v2(agente.id):
                metadata = {
                    'reason': 'session_expired',
                    'session_key': user.last_session_key,
                }
                self.close_presence_session_v2(
                    agente_id=agente.id,
                    ts=fecha_cierre,
                    source=SOURCE_SESSION_EXPIRED,
                    metadata=metadata,
                )
        except Session.DoesNotExist:
            # Si no existe la Session fue borrada al hacer logout. Nada para corregir.
            pass
