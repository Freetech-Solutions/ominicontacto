# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions
#
# This file is part of OMniLeads
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#

import logging
import signal
import sys
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.timezone import now

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ominicontacto_app.models import AgenteProfile
from ominicontacto_app.services.agent.presence import AgentPresenceManager
from ominicontacto_app.services.asterisk.agent_activity import AgentActivityAmiManager
from ominicontacto_app.services.redis.connection import create_redis_connection
from reportes_app.agent_activity_dual_write import SOURCE_HEARTBEAT_TIMEOUT

logger = logging.getLogger(__name__)

AGENT_KEY_PATTERN = 'OML:AGENT:*'
HEARTBEAT_SCAN_PATTERN = 'OML:PRESENCE:HB:*'
NON_ACTIVE_STATUSES = frozenset(['', 'OFFLINE', 'UNAVAILABLE', 'DISABLED'])


def _iter_scan(redis_conn, pattern, count=200):
    cursor = 0
    while True:
        cursor, keys = redis_conn.scan(cursor=cursor, match=pattern, count=count)
        for key in keys:
            yield key
        if cursor == 0:
            break


def _extract_agent_id_from_agent_key(key):
    try:
        return int(str(key).split(':')[-1])
    except (TypeError, ValueError):
        return None


def _collect_agents_with_heartbeat(redis_conn):
    """
    Devuelve los agent_id que tienen al menos un heartbeat vivo.
    Formato esperado: OML:PRESENCE:HB:{agent_id}:{browser_id}
    """
    agent_ids = set()
    for key in _iter_scan(redis_conn, HEARTBEAT_SCAN_PATTERN):
        parts = str(key).split(':')
        if len(parts) == 5 and parts[0:3] == ['OML', 'PRESENCE', 'HB']:
            try:
                agent_ids.add(int(parts[3]))
            except (TypeError, ValueError):
                continue
    return agent_ids


def _set_agent_unavailable(agent_activity, agent_id):
    try:
        agente_profile = AgenteProfile.objects.get(id=agent_id)
    except AgenteProfile.DoesNotExist:
        logger.warning(
            "presence_heartbeat: agente %s no existe; no se puede setear UNAVAILABLE",
            agent_id,
        )
        return
    agent_activity.set_agent_as_unavailable(agente_profile)


def sweep_presence_heartbeat_timeouts():
    """
    Detecta agentes sin heartbeat vigente y cierra su presencia en V2.
    Orden de escritura:
    1) Insertar SESSION_LOGOUT sintético en V2.
    2) Setear UNAVAILABLE en Redis.
    """
    try:
        redis_conn = create_redis_connection()
        redis_conn.ping()
    except Exception as e:
        logger.warning("presence_heartbeat: redis no disponible para sweep: %s", e)
        return

    presence_manager = AgentPresenceManager()
    agent_activity = AgentActivityAmiManager()

    timeout_sec = int(getattr(settings, 'PRESENCE_HEARTBEAT_TIMEOUT_SEC', 60))
    recent_window_sec = int(getattr(settings, 'PRESENCE_HEARTBEAT_LOGOUT_RECENT_SEC', 90))
    guard_ttl_sec = int(getattr(settings, 'PRESENCE_HEARTBEAT_GUARD_TTL_SEC', 90))
    heartbeat_agents = _collect_agents_with_heartbeat(redis_conn)
    current_ts = now()

    checked_agents = 0
    timeout_events = 0
    reconciled_agents = 0

    for key in _iter_scan(redis_conn, AGENT_KEY_PATTERN):
        agent_id = None
        try:
            agent_id = _extract_agent_id_from_agent_key(key)
            if agent_id is None:
                continue

            checked_agents += 1
            status = redis_conn.hget(key, 'STATUS') or ''
            if status in NON_ACTIVE_STATUSES:
                continue
            if agent_id in heartbeat_agents:
                continue

            guard_key = presence_manager.get_heartbeat_timeout_guard_key(agent_id)
            if redis_conn.exists(guard_key):
                continue

            recent_timeout_logout = presence_manager.has_recent_synthetic_logout(
                agente_id=agent_id,
                source=SOURCE_HEARTBEAT_TIMEOUT,
                within_seconds=recent_window_sec,
            )
            if recent_timeout_logout:
                if status != 'UNAVAILABLE':
                    _set_agent_unavailable(agent_activity, agent_id)
                    reconciled_agents += 1
                redis_conn.setex(guard_key, guard_ttl_sec, '1')
                continue

            if not presence_manager.is_presence_open_v2(agent_id):
                continue

            metadata = {
                'reason': 'timeout',
                'status_before': status,
                'heartbeat_timeout_sec': timeout_sec,
            }
            try:
                presence_manager.close_presence_session_v2(
                    agente_id=agent_id,
                    ts=current_ts,
                    source=SOURCE_HEARTBEAT_TIMEOUT,
                    metadata=metadata,
                )
            except Exception as write_error:
                logger.warning(
                    "presence_heartbeat: no se pudo insertar logout sintético para agente=%s: %s",
                    agent_id, write_error
                )
                # Si V2 falla, no tocar Redis; se reintentará en el próximo sweep.
                continue

            timeout_events += 1
            redis_conn.setex(guard_key, guard_ttl_sec, '1')

            try:
                _set_agent_unavailable(agent_activity, agent_id)
            except Exception as unavailable_error:
                logger.warning(
                    "presence_heartbeat: logout sintético ok pero fallo UNAVAILABLE para agente=%s: %s",
                    agent_id, unavailable_error
                )
        except Exception as e:
            logger.warning(
                "presence_heartbeat: error procesando agente=%s: %s",
                agent_id, e
            )

    logger.info(
        "presence_heartbeat sweep: checked=%s heartbeat_agents=%s timeouts=%s reconciled=%s",
        checked_agents, len(heartbeat_agents), timeout_events, reconciled_agents
    )


class Command(BaseCommand):
    help = 'Scheduler APScheduler para detectar timeout de heartbeat de agentes'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.scheduler = None
        self.shutdown_requested = False

    def setup_scheduler(self):
        executors = {
            'default': ThreadPoolExecutor(1)
        }
        job_defaults = {
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 60,
        }
        interval_sec = int(getattr(settings, 'PRESENCE_HEARTBEAT_SWEEP_SEC', 15))
        self.scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults=job_defaults,
            timezone=None,
        )
        self.scheduler.add_job(
            sweep_presence_heartbeat_timeouts,
            trigger=IntervalTrigger(seconds=interval_sec),
            id='presence_heartbeat_scheduler',
            name='Presence heartbeat timeout sweep',
            replace_existing=True,
        )
        logger.info(
            "presence_heartbeat scheduler configurado: intervalo=%ss",
            interval_sec
        )

    def signal_handler(self, signum, frame):
        logger.info("presence_heartbeat scheduler señal %s recibida; cerrando...", signum)
        self.shutdown_requested = True
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        sys.exit(0)

    def handle(self, *args, **options):
        try:
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)
            self.setup_scheduler()
            self.scheduler.start()
            logger.info("presence_heartbeat scheduler iniciado")
            while not self.shutdown_requested:
                time.sleep(1)
        except Exception as e:
            logger.error("Error en presence_heartbeat scheduler: %s", e, exc_info=True)
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            sys.exit(1)
        finally:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=True)
