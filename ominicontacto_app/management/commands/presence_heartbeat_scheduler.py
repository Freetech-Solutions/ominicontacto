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

from ominicontacto_app.services.agent.presence import (
    AgentPresenceManager,
    NON_ACTIVE_STATUSES,
)
from ominicontacto_app.services.asterisk.agent_activity import AgentActivityAmiManager
from ominicontacto_app.services.redis.connection import create_redis_connection

logger = logging.getLogger(__name__)

AGENT_KEY_PATTERN = 'OML:AGENT:*'
HEARTBEAT_SCAN_PATTERN = 'OML:PRESENCE:HB:*'


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


def _collect_agent_redis_state(redis_conn):
    """Devuelve (statuses, pause_ids) indexados por agent_id."""
    statuses = {}
    pause_ids = {}
    for key in _iter_scan(redis_conn, AGENT_KEY_PATTERN):
        agent_id = _extract_agent_id_from_agent_key(key)
        if agent_id is None:
            continue
        statuses[agent_id] = redis_conn.hget(key, 'STATUS') or ''
        pause_ids[agent_id] = redis_conn.hget(key, 'PAUSE_ID')
    return statuses, pause_ids


def _sweep_presence_heartbeats(
    redis_conn,
    presence_manager,
    agent_activity,
    heartbeat_agents,
    agent_statuses,
    pause_ids,
    timeout_sec,
    recent_window_sec,
    current_ts,
):
    checked_agents = 0
    timeout_events = 0
    reconciled_agents = 0
    recovered_agents = 0

    all_agent_ids = set(agent_statuses.keys()) | heartbeat_agents

    for agent_id in all_agent_ids:
        checked_agents += 1
        has_heartbeat = agent_id in heartbeat_agents
        status = agent_statuses.get(agent_id, '')
        pause_id = pause_ids.get(agent_id)

        try:
            if has_heartbeat and status == 'UNAVAILABLE':
                try:
                    if presence_manager.apply_heartbeat_recovery(
                        agente_id=agent_id,
                        ts=current_ts,
                        agent_activity=agent_activity,
                        redis_conn=redis_conn,
                    ):
                        recovered_agents += 1
                except Exception as recover_error:
                    logger.warning(
                        "presence_heartbeat: error recuperando agente=%s: %s",
                        agent_id, recover_error
                    )
                continue

            if has_heartbeat or status in NON_ACTIVE_STATUSES:
                continue

            if not presence_manager.is_presence_open_v2(agent_id):
                if presence_manager.reconcile_heartbeat_timeout_redis(
                    agente_id=agent_id,
                    status=status,
                    recent_window_sec=recent_window_sec,
                    agent_activity=agent_activity,
                ):
                    reconciled_agents += 1
                continue

            try:
                presence_manager.apply_heartbeat_timeout(
                    agente_id=agent_id,
                    status=status,
                    pause_id=pause_id,
                    ts=current_ts,
                    timeout_sec=timeout_sec,
                    agent_activity=agent_activity,
                )
                timeout_events += 1
            except Exception as timeout_error:
                logger.warning(
                    "presence_heartbeat: no se pudo aplicar timeout para agente=%s: %s",
                    agent_id, timeout_error
                )
        except Exception as e:
            logger.warning(
                "presence_heartbeat: error procesando agente=%s: %s",
                agent_id, e
            )

    return checked_agents, timeout_events, reconciled_agents, recovered_agents


def sweep_presence_heartbeats():
    """
    Barrido unificado de heartbeat: cierre por timeout, reconciliación Redis y recuperación.

    Orden de escritura (cierre):
    1) Insertar SESSION_LOGOUT sintético en V2.
    2) Setear UNAVAILABLE en Redis.

    Orden de escritura (recuperación):
    1) Insertar SESSION_LOGIN sintético en V2.
    2) Restaurar status_before en Redis.
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
    heartbeat_agents = _collect_agents_with_heartbeat(redis_conn)
    agent_statuses, pause_ids = _collect_agent_redis_state(redis_conn)
    current_ts = now()

    checked_agents, timeout_events, reconciled_agents, recovered_agents = (
        _sweep_presence_heartbeats(
            redis_conn=redis_conn,
            presence_manager=presence_manager,
            agent_activity=agent_activity,
            heartbeat_agents=heartbeat_agents,
            agent_statuses=agent_statuses,
            pause_ids=pause_ids,
            timeout_sec=timeout_sec,
            recent_window_sec=recent_window_sec,
            current_ts=current_ts,
        )
    )

    logger.info(
        "presence_heartbeat sweep: checked=%s heartbeat_agents=%s timeouts=%s "
        "reconciled=%s recovered=%s",
        checked_agents, len(heartbeat_agents), timeout_events,
        reconciled_agents, recovered_agents
    )


# Alias de compatibilidad con referencias existentes.
sweep_presence_heartbeat_timeouts = sweep_presence_heartbeats


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
            sweep_presence_heartbeats,
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
