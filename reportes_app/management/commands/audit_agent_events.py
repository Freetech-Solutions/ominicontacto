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

"""
Auditoría de health checks para eventos de actividad de agente (Legacy y V2).
Ejecuta checks A, B, D, F, H, I. Ver docs/agent_events_health_checks.md.
"""

import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.db import connection

logger = logging.getLogger(__name__)

MAX_EXAMPLES = 20
FLAPPING_SECONDS = 2
PARITY_WARN_PCT = 1.0
PARITY_WARN_ABS = 10
PARITY_CRIT_PCT = 5.0
PARITY_CRIT_ABS = 100


class Command(BaseCommand):
    help = (
        'Audita eventos de actividad de agente (legacy y V2): '
        'UNPAUSEALL con pausa_id, logouts/logins consecutivos, estado fuera de sesión, '
        'consistencia V2, paridad dual-write, flapping.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--since',
            type=str,
            default=None,
            help='Inicio del rango (ISO datetime, ej. 2025-02-01T00:00:00). Por defecto: hace 24h.',
        )
        parser.add_argument(
            '--until',
            type=str,
            default=None,
            help='Fin del rango (ISO datetime). Por defecto: ahora.',
        )
        parser.add_argument(
            '--agent-id',
            type=int,
            default=None,
            help='Filtrar por agente_id (opcional).',
        )

    def handle(self, *args, **options):
        until = self._parse_dt(options['until']) or datetime.now()
        since = self._parse_dt(options['since']) or (until - timedelta(hours=24))
        agent_id = options.get('agent_id')

        if since >= until:
            self.stderr.write('Error: --since debe ser anterior a --until.')
            return

        params = {'since': since, 'until': until}
        if agent_id is not None:
            params['agent_id'] = agent_id
        agent_filter = ' AND agente_id = %(agent_id)s' if agent_id is not None else ''

        self.stdout.write('Audit agent events: since={} until={} agent_id={}'.format(
            since, until, agent_id))

        results = []
        # A) UNPAUSEALL con pausa_id no nulo
        rows_a = self._run_check_a(params, agent_filter)
        status_a = 'CRIT' if rows_a else 'OK'
        results.append(('A', 'UNPAUSEALL con pausa_id no nulo', status_a, len(rows_a), rows_a[:MAX_EXAMPLES]))

        # B) Logout duplicado consecutivo
        rows_b = self._run_check_b(params, agent_filter)
        status_b = 'WARN' if rows_b else 'OK'
        results.append(('B', 'Logout duplicado consecutivo', status_b, len(rows_b), rows_b[:MAX_EXAMPLES]))

        # D) PAUSEALL/UNPAUSEALL fuera de sesión
        rows_d = self._run_check_d(params, agent_filter)
        status_d = 'WARN' if rows_d else 'OK'
        results.append(('D', 'PAUSE/UNPAUSE fuera de sesión', status_d, len(rows_d), rows_d[:MAX_EXAMPLES]))

        # F) V2 consistencia schema
        rows_f = self._run_check_f(params, agent_filter)
        status_f = 'CRIT' if rows_f else 'OK'
        results.append(('F', 'V2 consistencia schema', status_f, len(rows_f), rows_f[:MAX_EXAMPLES]))

        # H) Paridad legacy vs V2
        status_h, detail_h, rows_h = self._run_check_h(params, agent_filter)
        results.append(('H', 'Paridad legacy vs V2', status_h, 0, []))
        detail_lines_h = [detail_h] if isinstance(detail_h, str) else (detail_h or [])

        # I) Flapping logout -> login < 2s
        rows_i = self._run_check_i(params, agent_filter)
        status_i = 'WARN' if rows_i else 'OK'
        results.append(('I', 'Flapping logout->login <{}s'.format(FLAPPING_SECONDS), status_i, len(rows_i), rows_i[:MAX_EXAMPLES]))

        # Output
        for code, name, status, count, examples in results:
            self.stdout.write('{} [{}] {} (count={})'.format(code, status, name, count))
            if code == 'H':
                for line in detail_lines_h:
                    self.stdout.write('  {}'.format(line))
            else:
                for ex in examples:
                    self.stdout.write('  example: {}'.format(ex))

        crit_count = sum(1 for r in results if r[2] == 'CRIT')
        warn_count = sum(1 for r in results if r[2] == 'WARN')
        if crit_count:
            self.stderr.write('Audit finished with {} CRIT, {} WARN'.format(crit_count, warn_count))
        elif warn_count:
            self.stdout.write('Audit finished: {} WARN'.format(warn_count))
        else:
            self.stdout.write('Audit finished: all OK')

    def _parse_dt(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None

    def _run_sql(self, sql, params, agent_filter_placeholder=''):
        """Ejecuta SQL reemplazando {agent_filter} por el filtro opcional de agente."""
        sql = sql.replace('{agent_filter}', agent_filter_placeholder)
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return rows

    def _run_check_a(self, params, agent_filter):
        sql = """
        SELECT id, agente_id, time, event, pausa_id
        FROM reportes_app_actividadagentelog
        WHERE time >= %(since)s AND time < %(until)s
          AND event = 'UNPAUSEALL'
          AND (pausa_id IS NOT NULL AND pausa_id != '')
        {agent_filter}
        """
        return self._run_sql(sql, params, agent_filter)

    def _run_check_b(self, params, agent_filter):
        sql = """
        WITH ordered AS (
          SELECT id, agente_id, time, event,
            LAG(event) OVER (PARTITION BY agente_id ORDER BY time, id) AS prev_event
          FROM reportes_app_actividadagentelog
          WHERE time >= %(since)s AND time < %(until)s
          {agent_filter}
        )
        SELECT id, agente_id, time, event, prev_event
        FROM ordered
        WHERE event IN ('SESSION_LOGOUT', 'REMOVEMEMBER')
          AND prev_event IN ('SESSION_LOGOUT', 'REMOVEMEMBER')
        """
        # agent_filter debe ir en el WHERE del CTE
        inner = ' AND agente_id = %(agent_id)s' if params.get('agent_id') is not None else ''
        sql = sql.replace('{agent_filter}', inner)
        return self._run_sql(sql, params)

    def _run_check_d(self, params, agent_filter):
        sql = """
        WITH session_balance AS (
          SELECT id, agente_id, time, event,
            SUM(CASE WHEN event IN ('SESSION_LOGIN', 'ADDMEMBER') THEN 1
                     WHEN event IN ('SESSION_LOGOUT', 'REMOVEMEMBER') THEN -1
                     ELSE 0 END)
              OVER (PARTITION BY agente_id ORDER BY time, id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS balance_before
          FROM reportes_app_actividadagentelog
          WHERE time >= %(since)s AND time < %(until)s
          {agent_filter}
        ),
        pause_unpause AS (
          SELECT id, agente_id, time, event, balance_before
          FROM session_balance
          WHERE event IN ('PAUSEALL', 'UNPAUSEALL')
        )
        SELECT id, agente_id, time, event, balance_before
        FROM pause_unpause
        WHERE balance_before IS NULL OR balance_before <= 0
        """
        inner = ' AND agente_id = %(agent_id)s' if params.get('agent_id') is not None else ''
        sql = sql.replace('{agent_filter}', inner)
        return self._run_sql(sql, params)

    def _run_check_f(self, params, agent_filter):
        sql = """
        SELECT id, agente_id, ts, event_type, pause_id, aux_code
        FROM reportes_app_agentactivityeventv2
        WHERE ts >= %(since)s AND ts < %(until)s
        {agent_filter}
          AND (
            (event_type = 'STATE_READY' AND (pause_id IS NOT NULL OR (aux_code IS NOT NULL AND aux_code != '')))
            OR (event_type = 'STATE_ACW'  AND (pause_id IS NOT NULL OR (aux_code IS NOT NULL AND aux_code != '')))
            OR (event_type = 'STATE_PAUSED' AND (pause_id IS NULL AND (aux_code IS NULL OR aux_code = '')))
            OR (event_type IN ('SESSION_LOGIN', 'SESSION_LOGOUT') AND (pause_id IS NOT NULL OR (aux_code IS NOT NULL AND aux_code != '')))
          )
        """
        return self._run_sql(sql, params, agent_filter)

    def _run_check_h(self, params, agent_filter):
        # Legacy counts
        sql_legacy = """
        SELECT event, COUNT(*) AS cnt
        FROM reportes_app_actividadagentelog
        WHERE time >= %(since)s AND time < %(until)s
          AND event IN ('SESSION_LOGIN', 'SESSION_LOGOUT', 'PAUSEALL', 'UNPAUSEALL')
        {agent_filter}
        GROUP BY event
        """
        inner = ' AND agente_id = %(agent_id)s' if params.get('agent_id') is not None else ''
        legacy_rows = self._run_sql(sql_legacy.replace('{agent_filter}', inner), params)

        sql_v2 = """
        SELECT
          CASE event_type
            WHEN 'SESSION_LOGIN' THEN 'SESSION_LOGIN'
            WHEN 'SESSION_LOGOUT' THEN 'SESSION_LOGOUT'
            WHEN 'STATE_PAUSED' THEN 'PAUSEALL'
            WHEN 'STATE_ACW' THEN 'PAUSEALL'
            WHEN 'STATE_READY' THEN 'UNPAUSEALL'
          END AS event_legacy,
          COUNT(*) AS cnt
        FROM reportes_app_agentactivityeventv2
        WHERE ts >= %(since)s AND ts < %(until)s
          AND event_type IN ('SESSION_LOGIN', 'SESSION_LOGOUT', 'STATE_PAUSED', 'STATE_ACW', 'STATE_READY')
        {agent_filter}
        GROUP BY 1
        """
        v2_rows = self._run_sql(sql_v2.replace('{agent_filter}', inner), params)

        legacy_by_event = {r['event']: r['cnt'] for r in legacy_rows}
        v2_pauseall = sum(r['cnt'] for r in v2_rows if r['event_legacy'] == 'PAUSEALL')
        v2_by_event = {}
        for r in v2_rows:
            if r['event_legacy'] == 'PAUSEALL':
                v2_by_event['PAUSEALL'] = v2_pauseall
            else:
                v2_by_event[r['event_legacy']] = r['cnt']
        v2_by_event.setdefault('PAUSEALL', 0)

        total_legacy = sum(legacy_by_event.values())
        details = []
        status = 'OK'
        for event in ('SESSION_LOGIN', 'SESSION_LOGOUT', 'PAUSEALL', 'UNPAUSEALL'):
            leg = legacy_by_event.get(event, 0)
            v2 = v2_by_event.get(event, 0)
            diff = abs(leg - v2)
            details.append('  {} legacy={} v2={} diff={}'.format(event, leg, v2, diff))
            if total_legacy > 0:
                pct = 100.0 * diff / total_legacy
                if diff > PARITY_CRIT_ABS or pct > PARITY_CRIT_PCT:
                    status = 'CRIT'
                elif (status != 'CRIT') and (diff > PARITY_WARN_ABS or pct > PARITY_WARN_PCT):
                    status = 'WARN'
        return status, details, None

    def _run_check_i(self, params, agent_filter):
        sql = """
        WITH ordered AS (
          SELECT id, agente_id, time, event,
            LAG(event) OVER (PARTITION BY agente_id ORDER BY time, id) AS prev_event,
            LAG(time) OVER (PARTITION BY agente_id ORDER BY time, id) AS prev_time
          FROM reportes_app_actividadagentelog
          WHERE time >= %(since)s AND time < %(until)s
          {agent_filter}
        )
        SELECT id, agente_id, time, event, prev_event, prev_time
        FROM ordered
        WHERE event IN ('SESSION_LOGIN', 'ADDMEMBER')
          AND prev_event IN ('SESSION_LOGOUT', 'REMOVEMEMBER')
          AND (time - prev_time) BETWEEN INTERVAL '0' AND INTERVAL '%d seconds'
        """ % FLAPPING_SECONDS
        inner = ' AND agente_id = %(agent_id)s' if params.get('agent_id') is not None else ''
        sql = sql.replace('{agent_filter}', inner)
        return self._run_sql(sql, params)
