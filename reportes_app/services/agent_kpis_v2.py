import json
import logging
from datetime import datetime, timedelta

import pytz
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

def get_agent_activity_kpis_v2(date_start, date_end, agent_id=None, group_by='agent'):
    """
    Calcula KPIs de agentes usando Window Functions de PostgreSQL.
    Evita iterar en Python para máxima performance.
    """
    
    # 1. Definir parámetros y Query Raw
    # Convertimos las fechas a strings seguros para la query si es necesario, 
    # aunque pasarlos como params a cursor.execute es lo ideal.
    
    # Tabla reportes_app_agentactivityeventv2: ts, agente_id, event_type, pause_id, aux_code, metadata
    sql_query = """
    WITH raw_events AS (
        SELECT 
            id,
            agente_id AS agent_id,
            ts AS timestamp,
            event_type,
            metadata,
            pause_id,
            aux_code
        FROM reportes_app_agentactivityeventv2
        WHERE ts >= %(since)s - INTERVAL '24 hours'
          AND ts <= %(until)s
          AND (%(agent_id)s IS NULL OR agente_id = %(agent_id)s)
    ),
    
    events_with_lead AS (
        SELECT 
            *,
            LEAD(timestamp) OVER (PARTITION BY agent_id ORDER BY timestamp ASC) as next_ts,
            LEAD(event_type) OVER (PARTITION BY agent_id ORDER BY timestamp ASC) as next_event
        FROM raw_events
    ),
    
    intervals AS (
        SELECT
            agent_id,
            timestamp as start_ts,
            COALESCE(next_ts, LEAST(NOW(), %(until)s)) as end_ts,
            event_type,
            metadata,
            pause_id,
            aux_code,
            EXTRACT(EPOCH FROM (COALESCE(next_ts, LEAST(NOW(), %(until)s)) - timestamp)) as duration_seconds,
            date_trunc('day', timestamp AT TIME ZONE %(timezone)s) as report_date
        FROM events_with_lead
        WHERE timestamp >= %(since)s
          AND timestamp < %(until)s
          AND event_type != 'SESSION_LOGOUT'
    ),
    
    -- Desglose de pausas: todas las filas STATE_PAUSED de intervals, agrupadas por motivo.
    -- Si pause_id y aux_code son NULL se agrupa como 'UNKNOWN' para no descartar.
    pause_breakdown AS (
        SELECT
            agent_id,
            report_date,
            COALESCE(pause_id::text, COALESCE(aux_code, 'UNKNOWN')) AS reason_key,
            SUM(duration_seconds) AS seconds,
            MAX(pause_id) AS pause_id,
            MAX(aux_code) AS aux_code
        FROM intervals
        WHERE event_type = 'STATE_PAUSED'
        GROUP BY agent_id, report_date, COALESCE(pause_id::text, COALESCE(aux_code, 'UNKNOWN'))
    )

    SELECT 
        i.agent_id,
        %(group_field)s as group_key,
        SUM(CASE WHEN i.event_type IN ('SESSION_LOGIN', 'STATE_READY', 'STATE_PAUSED', 'STATE_ACW') THEN i.duration_seconds ELSE 0 END) as session_seconds,
        SUM(CASE WHEN i.event_type = 'STATE_READY' OR i.event_type = 'SESSION_LOGIN' THEN i.duration_seconds ELSE 0 END) as ready_seconds,
        SUM(CASE WHEN i.event_type = 'STATE_PAUSED' THEN i.duration_seconds ELSE 0 END) as pause_seconds,
        SUM(CASE WHEN i.event_type = 'STATE_ACW' THEN i.duration_seconds ELSE 0 END) as acw_seconds,
        COUNT(CASE WHEN i.event_type = 'SESSION_LOGIN' THEN 1 END) as sessions_count,
        COUNT(*) FILTER (WHERE i.event_type = 'STATE_PAUSED') as pauses_count,
        __BREAKDOWN_SUBQUERY__ AS pause_breakdown_json
    FROM intervals i
    GROUP BY 1, 2
    ORDER BY 1, 2;
    """
    
    # Configurar Timezone
    tz_name = getattr(settings, 'TIME_ZONE', 'UTC')
    local_tz = pytz.timezone(tz_name)
    
    # Preparar fechas (Since 00:00:00, Until 23:59:59)
    dt_start = datetime.strptime(date_start, '%Y-%m-%d')
    dt_end = datetime.strptime(date_end, '%Y-%m-%d')
    
    since = local_tz.localize(dt_start.replace(hour=0, minute=0, second=0))
    until = local_tz.localize(dt_end.replace(hour=23, minute=59, second=59, microsecond=999999))
    
    # Ajuste dinámico: group_key y subquery de pause_breakdown (no parametrizables vía psycopg2)
    group_field = "i.report_date" if group_by == 'day' else "'ALL'"
    breakdown_date_filter = "AND pb.report_date = i.report_date" if group_by == 'day' else ""
    # aux_code: 'UNKNOWN' solo si pause_id IS NULL AND aux_code IS NULL; si pause_id existe => aux_code NULL o valor real.
    # seconds: int (bigint) para que SUM(pause_breakdown.seconds) sea consistente con pause_seconds (enteros).
    breakdown_subquery = (
        "(SELECT jsonb_agg(jsonb_build_object("
        "'pause_id', pb.pause_id, "
        "'aux_code', CASE WHEN pb.pause_id IS NOT NULL THEN pb.aux_code ELSE COALESCE(pb.aux_code, 'UNKNOWN') END, "
        "'seconds', (ROUND(pb.seconds::numeric)::bigint)"
        ")) FROM pause_breakdown pb WHERE pb.agent_id = i.agent_id " + breakdown_date_filter + ")"
    )

    params = {
        'since': since,
        'until': until,
        'agent_id': agent_id,
        'timezone': tz_name,
    }

    with connection.cursor() as cursor:
        final_sql = sql_query.replace('%(group_field)s', group_field).replace('__BREAKDOWN_SUBQUERY__', breakdown_subquery)
        cursor.execute(final_sql, params)
        rows = cursor.fetchall()

    # Formateo de respuesta: row = agent_id, group_key, session_seconds, ready, pause, acw, sessions_count, pauses_count, pause_breakdown_json
    results = []
    for row in rows:
        total_session = row[2] or 0
        pause_seconds = int(round(row[4], 0))
        pause_breakdown_raw = row[8]  # jsonb o None
        if pause_breakdown_raw is not None and pause_breakdown_raw != '':
            try:
                breakdown_list = json.loads(pause_breakdown_raw) if isinstance(pause_breakdown_raw, str) else list(pause_breakdown_raw) if pause_breakdown_raw else []
            except (TypeError, ValueError):
                breakdown_list = []
        else:
            breakdown_list = []
        if pause_seconds > 0 and not breakdown_list:
            logger.warning(
                "agents_kpis_v2: pause_seconds=%s but pause_breakdown empty for agent_id=%s, date=%s; using UNKNOWN entry",
                pause_seconds, row[0], row[1],
            )
            breakdown_list = [{"pause_id": None, "aux_code": "UNKNOWN", "seconds": pause_seconds}]

        agent_data = {
            "agente_id": row[0],
            "date": row[1] if group_by == 'day' else date_start,
            "session_seconds": int(round(total_session, 0)),
            "ready_seconds": int(round(row[3], 0)),
            "pause_seconds": pause_seconds,
            "acw_seconds": int(round(row[5], 0)),
            "sessions_count": row[6],
            "pauses_count": row[7] or 0,
            "ready_ratio": round(row[3] / total_session, 4) if total_session > 0 else 0,
            "pause_ratio": round(row[4] / total_session, 4) if total_session > 0 else 0,
            "acw_ratio": round(row[5] / total_session, 4) if total_session > 0 else 0,
            "pause_breakdown": breakdown_list,
        }
        results.append(agent_data)
        
    return {
        "group_by": group_by,
        "agents": results
    }