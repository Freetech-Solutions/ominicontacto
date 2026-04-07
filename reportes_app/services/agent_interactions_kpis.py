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
Servicio de KPIs de interacciones por agente desde interactions_summary.
Solo VOICE por defecto; agregación por agent_id y opcionalmente por día local.
"""

import pytz
from django.db import connection
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, FloatField, Q
from django.db.models.functions import Extract, TruncDate

from ominicontacto_app.models import CalificacionCliente, OpcionCalificacion
from reportes_app.models import AgentActivityEventV2
from whatsapp_app.models import ConversacionWhatsapp


def _get_agent_whatsapp_act_avg(since, until, agent_id=None):
    """
    Retorna el ACT (Average Conversation Time) de WhatsApp por agente en segundos.

    Reglas:
    - agent_id no nulo
    - atendida=True
    - date_last_interaction no nulo
    - timestamp en [since, until]
    - excluye duraciones negativas
    """
    qs = ConversacionWhatsapp.objects.filter(
        timestamp__gte=since,
        timestamp__lte=until,
        agent_id__isnull=False,
        atendida=True,
        date_last_interaction__isnull=False,
    )
    if agent_id is not None:
        qs = qs.filter(agent_id=agent_id)

    rows = (
        qs
        .annotate(
            _duration_delta=ExpressionWrapper(
                F('date_last_interaction') - F('timestamp'),
                output_field=DurationField(),
            ),
        )
        .annotate(
            _duration_seconds=ExpressionWrapper(
                Extract(F('_duration_delta'), lookup_name='epoch'),
                output_field=FloatField(),
            ),
        )
        .filter(_duration_seconds__gte=0)
        .values('agent_id')
        .annotate(act_avg=Avg('_duration_seconds'))
        .order_by('agent_id')
    )

    result = []
    for row in rows:
        result.append({
            'agent_id': row['agent_id'],
            'act_avg': float(row.get('act_avg') or 0),
        })
    return result


def _get_agent_whatsapp_in_out_counts(
    since,
    until,
    agent_id=None,
    group_by='day',
    timezone_name=None,
):
    """
    Retorna conteos de conversaciones WhatsApp por agente para sumar a In/Out.
    Inbound: saliente=False. Outbound: saliente=True.
    """
    if timezone_name is None:
        from django.conf import settings
        timezone_name = settings.TIME_ZONE or 'UTC'
    try:
        tz = pytz.timezone(timezone_name)
    except Exception:
        tz = pytz.UTC

    qs = ConversacionWhatsapp.objects.filter(
        timestamp__gte=since,
        timestamp__lte=until,
        agent_id__isnull=False,
    )
    if agent_id is not None:
        qs = qs.filter(agent_id=agent_id)

    if group_by == 'day':
        rows = (
            qs
            .annotate(local_date=TruncDate('timestamp', tzinfo=tz))
            .values('agent_id', 'local_date')
            .annotate(
                interactions_inbound_wa=Count('id', filter=Q(saliente=False)),
                interactions_outbound_wa=Count('id', filter=Q(saliente=True)),
            )
            .order_by('agent_id', 'local_date')
        )
    else:
        rows = (
            qs
            .values('agent_id')
            .annotate(
                interactions_inbound_wa=Count('id', filter=Q(saliente=False)),
                interactions_outbound_wa=Count('id', filter=Q(saliente=True)),
            )
            .order_by('agent_id')
        )

    result = []
    for row in rows:
        out = {
            'agent_id': row['agent_id'],
            'interactions_inbound_wa': row.get('interactions_inbound_wa') or 0,
            'interactions_outbound_wa': row.get('interactions_outbound_wa') or 0,
        }
        if group_by == 'day' and row.get('local_date') is not None:
            local_date = row['local_date']
            out['date'] = local_date.isoformat() if hasattr(local_date, 'isoformat') else str(local_date)
        result.append(out)

    return result


def _get_agent_voice_interactions_kpis(
    since,
    until,
    agent_id=None,
    group_by='day',
    channel_type='VOICE',
    timezone_name=None,
):
    """
    Retorna KPIs de VOICE desde interactions_summary.
    """
    params = {
        'since': since,
        'until': until,
        'channel_type': channel_type,
        'tz': timezone_name,
        'agent_id': agent_id,
    }

    # Interacciones que se solapan con [since, until]: start_time < until AND (end_time IS NULL OR end_time > since)
    # Solo filas con agent_id no nulo para poder agrupar por agente
    where_clause = """
        start_time < %(until)s
        AND (end_time IS NULL OR end_time > %(since)s)
        AND channel_type = %(channel_type)s
        AND agent_id IS NOT NULL
        AND (%(agent_id)s IS NULL OR agent_id = %(agent_id)s)
    """

    if group_by == 'day':
        select_group = """
            agent_id,
            ((start_time AT TIME ZONE %(tz)s)::date) AS local_date,
            COUNT(*)::int AS interactions_total,
            COUNT(*) FILTER (WHERE UPPER(TRIM(direction)) = 'INBOUND')::int AS interactions_inbound,
            COUNT(*) FILTER (WHERE UPPER(TRIM(direction)) = 'OUTBOUND')::int AS interactions_outbound,
            COUNT(*) FILTER (WHERE UPPER(TRIM(status)) = 'EXIT_ANSWERED')::int AS answered_count,
            COUNT(*) FILTER (WHERE UPPER(TRIM(status)) = 'CANCEL')::int AS cancel_count,
            COUNT(*) FILTER (WHERE outcome = true)::int AS sales_count,
            COALESCE(SUM(agent_duration), 0)::numeric(12,3) AS talk_seconds,
            COALESCE(AVG(agent_duration) FILTER (WHERE UPPER(TRIM(status)) = 'EXIT_ANSWERED'), 0)::numeric(12,3) AS avg_talk_seconds_answered,
            COALESCE(SUM(wait_conn_duration), 0)::numeric(12,3) AS wait_conn_duration,
            COALESCE(AVG(wait_conn_duration), 0)::numeric(12,3) AS avg_wait_conn_duration
        """
        group_by_clause = "GROUP BY agent_id, ((start_time AT TIME ZONE %(tz)s)::date)"
    else:
        select_group = """
            agent_id,
            COUNT(*)::int AS interactions_total,
            COUNT(*) FILTER (WHERE UPPER(TRIM(direction)) = 'INBOUND')::int AS interactions_inbound,
            COUNT(*) FILTER (WHERE UPPER(TRIM(direction)) = 'OUTBOUND')::int AS interactions_outbound,
            COUNT(*) FILTER (WHERE UPPER(TRIM(status)) = 'EXIT_ANSWERED')::int AS answered_count,
            COUNT(*) FILTER (WHERE UPPER(TRIM(status)) = 'CANCEL')::int AS cancel_count,
            COUNT(*) FILTER (WHERE outcome = true)::int AS sales_count,
            COALESCE(SUM(agent_duration), 0)::numeric(12,3) AS talk_seconds,
            COALESCE(AVG(agent_duration) FILTER (WHERE UPPER(TRIM(status)) = 'EXIT_ANSWERED'), 0)::numeric(12,3) AS avg_talk_seconds_answered,
            COALESCE(SUM(wait_conn_duration), 0)::numeric(12,3) AS wait_conn_duration,
            COALESCE(AVG(wait_conn_duration), 0)::numeric(12,3) AS avg_wait_conn_duration
        """
        group_by_clause = "GROUP BY agent_id"

    sql = """
        SELECT
            """ + select_group + """
        FROM public.interactions_summary
        WHERE """ + where_clause + """
        """ + group_by_clause

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    result = []
    for row in rows:
        out = {
            'agent_id': row['agent_id'],
            'interactions_total': row.get('interactions_total') or 0,
            'interactions_inbound': row.get('interactions_inbound') or 0,
            'interactions_outbound': row.get('interactions_outbound') or 0,
            'answered_count': row.get('answered_count') or 0,
            'cancel_count': row.get('cancel_count') or 0,
            'sales_count': row.get('sales_count') or 0,
            'talk_seconds': float(row.get('talk_seconds') or 0),
            'avg_talk_seconds_answered': float(row.get('avg_talk_seconds_answered') or 0),
            'wait_conn_duration': float(row.get('wait_conn_duration') or 0),
            'avg_wait_conn_duration': float(row.get('avg_wait_conn_duration') or 0),
        }
        if group_by == 'day' and 'local_date' in row and row['local_date'] is not None:
            out['date'] = row['local_date'].isoformat() if hasattr(row['local_date'], 'isoformat') else str(row['local_date'])
        result.append(out)

    return result


def get_agent_interactions_kpis(
    since,
    until,
    agent_id=None,
    group_by='day',
    channel_type='VOICE',
    timezone_name=None,
    include_whatsapp_in_out=False,
):
    """
    Calcula KPIs de interacciones (VOICE) por agente en el rango [since, until].

    Args:
        since: datetime aware, inicio del rango.
        until: datetime aware, fin del rango.
        agent_id: opcional, filtrar por agente.
        group_by: 'agent' (una fila por agente) o 'day' (una fila por agente y día local).
        channel_type: tipo de canal, por defecto 'VOICE'.
        timezone_name: timezone para día local en group_by=day (ej. settings.TIME_ZONE).
        include_whatsapp_in_out: si True, suma conversaciones WhatsApp por agente a In/Out.

    Returns:
        Lista de dicts con agent_id, date (si group_by=day), y métricas:
        interactions_total, interactions_inbound, interactions_outbound,
        answered_count, cancel_count, sales_count, talk_seconds,
        avg_talk_seconds_answered, wait_conn_duration, avg_wait_conn_duration.
    """
    if timezone_name is None:
        from django.conf import settings
        timezone_name = settings.TIME_ZONE or 'UTC'
    result = _get_agent_voice_interactions_kpis(
        since=since,
        until=until,
        agent_id=agent_id,
        group_by=group_by,
        channel_type=channel_type,
        timezone_name=timezone_name,
    )

    if not include_whatsapp_in_out:
        return result

    wa_rows = _get_agent_whatsapp_in_out_counts(
        since=since,
        until=until,
        agent_id=agent_id,
        group_by=group_by,
        timezone_name=timezone_name,
    )

    merged = {}
    for row in result:
        key = (row['agent_id'], row.get('date') if group_by == 'day' else None)
        merged[key] = dict(row)
        merged[key]['interactions_inbound_voice'] = row.get('interactions_inbound') or 0
        merged[key]['interactions_outbound_voice'] = row.get('interactions_outbound') or 0
        merged[key]['interactions_inbound_chat'] = 0
        merged[key]['interactions_outbound_chat'] = 0

    for wa_row in wa_rows:
        key = (wa_row['agent_id'], wa_row.get('date') if group_by == 'day' else None)
        wa_in = wa_row.get('interactions_inbound_wa') or 0
        wa_out = wa_row.get('interactions_outbound_wa') or 0
        if key not in merged:
            merged[key] = {
                'agent_id': wa_row['agent_id'],
                'interactions_total': 0,
                'interactions_inbound': 0,
                'interactions_outbound': 0,
                'interactions_inbound_voice': 0,
                'interactions_outbound_voice': 0,
                'interactions_inbound_chat': wa_in,
                'interactions_outbound_chat': wa_out,
                'answered_count': 0,
                'cancel_count': 0,
                'sales_count': 0,
                'talk_seconds': 0.0,
                'avg_talk_seconds_answered': 0.0,
                'wait_conn_duration': 0.0,
                'avg_wait_conn_duration': 0.0,
            }
            if group_by == 'day' and wa_row.get('date') is not None:
                merged[key]['date'] = wa_row.get('date')
        else:
            merged[key]['interactions_inbound_chat'] = wa_in
            merged[key]['interactions_outbound_chat'] = wa_out
        merged[key]['interactions_inbound'] += wa_in
        merged[key]['interactions_outbound'] += wa_out

    if group_by == 'day':
        return sorted(merged.values(), key=lambda row: (row.get('date') or '', row['agent_id']))
    return sorted(merged.values(), key=lambda row: row['agent_id'])


def get_agent_transfer_counts(
    since,
    until,
    agent_id=None,
    status_filter='OK',
):
    """
    Calcula cantidad de transferencias por agente desde interaction_transfers.

    Args:
        since: datetime aware, inicio del rango.
        until: datetime aware, fin del rango.
        agent_id: opcional, filtrar por agente.
        status_filter: estado de transferencia a considerar (default: 'OK').

    Returns:
        Lista de dicts con:
        - agent_id (int)
        - transfer_count (int)
    """
    params = {
        'since': since,
        'until': until,
        'agent_id': agent_id,
        'status_filter': status_filter,
    }

    where_parts = [
        "created_at >= %(since)s",
        "created_at <= %(until)s",
        "source_agent_id IS NOT NULL",
        "(%(agent_id)s IS NULL OR source_agent_id = %(agent_id)s)",
    ]
    if status_filter is not None:
        where_parts.append("UPPER(TRIM(status)) = UPPER(TRIM(%(status_filter)s))")

    sql = """
        SELECT
            source_agent_id AS agent_id,
            COUNT(*)::int AS transfer_count
        FROM public.interaction_transfers
        WHERE """ + " AND ".join(where_parts) + """
        GROUP BY source_agent_id
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    result = []
    for row in rows:
        result.append({
            'agent_id': row[0],
            'transfer_count': row[1] or 0,
        })

    return result


def get_agent_transfer_in_counts(
    since,
    until,
    agent_id=None,
    status_filter='OK',
):
    """
    Calcula cantidad de transferencias recibidas por agente desde interaction_transfers
    (agrupando por destination_agent_id).

    Args:
        since: datetime aware, inicio del rango.
        until: datetime aware, fin del rango.
        agent_id: opcional, filtrar por agente.
        status_filter: estado de transferencia a considerar (default: 'OK').

    Returns:
        Lista de dicts con:
        - agent_id (int)
        - transfer_in_count (int)
    """
    params = {
        'since': since,
        'until': until,
        'agent_id': agent_id,
        'status_filter': status_filter,
    }

    where_parts = [
        "created_at >= %(since)s",
        "created_at <= %(until)s",
        "destination_agent_id IS NOT NULL",
        "(%(agent_id)s IS NULL OR destination_agent_id = %(agent_id)s)",
    ]
    if status_filter is not None:
        where_parts.append("UPPER(TRIM(status)) = UPPER(TRIM(%(status_filter)s))")

    sql = """
        SELECT
            destination_agent_id AS agent_id,
            COUNT(*)::int AS transfer_in_count
        FROM public.interaction_transfers
        WHERE """ + " AND ".join(where_parts) + """
        GROUP BY destination_agent_id
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    result = []
    for row in rows:
        result.append({
            'agent_id': row[0],
            'transfer_in_count': row[1] or 0,
        })

    return result


def get_agent_hold_counts(since, until, agent_id=None):
    """
    Calcula cantidad de veces que cada agente usó Hold (eventos STATE_ON_HOLD)
    en reportes_app_agentactivityeventv2 dentro del rango [since, until].

    Args:
        since: datetime aware, inicio del rango.
        until: datetime aware, fin del rango.
        agent_id: opcional, filtrar por agente.

    Returns:
        Lista de dicts con agent_id (int) y hold_count (int).
    """
    qs = AgentActivityEventV2.objects.filter(
        ts__gte=since,
        ts__lte=until,
        event_type=AgentActivityEventV2.EventType.STATE_ON_HOLD,
    )
    if agent_id is not None:
        qs = qs.filter(agente_id=agent_id)
    rows = qs.values('agente_id').annotate(hold_count=Count('id')).values_list('agente_id', 'hold_count')
    return [{'agent_id': aid, 'hold_count': count or 0} for aid, count in rows]


def get_agent_hold_seconds(since, until, agent_id=None):
    """
    Calcula tiempo total en hold (segundos) por agente usando AgentActivityEventV2
    (eventos STATE_ON_HOLD / STATE_OFF_HOLD), emparejando inicios y fines por agente.

    Args:
        since: datetime aware, inicio del rango.
        until: datetime aware, fin del rango.
        agent_id: opcional, filtrar por agente.

    Returns:
        Lista de dicts con agent_id (int) y hold_seconds (float).
    """
    from django.utils.timezone import now

    qs = AgentActivityEventV2.objects.filter(
        ts__gte=since,
        ts__lte=until,
        event_type__in=(
            AgentActivityEventV2.EventType.STATE_ON_HOLD,
            AgentActivityEventV2.EventType.STATE_OFF_HOLD,
        ),
    ).order_by('agente_id', 'ts')
    if agent_id is not None:
        qs = qs.filter(agente_id=agent_id)

    events = list(qs.values_list('agente_id', 'ts', 'event_type'))
    result = {}  # agent_id -> hold_seconds

    # Agrupar por agente y calcular duración por hold
    current_agent = None
    hold_start = None
    for agente_id, ts, event_type in events:
        if agente_id not in result:
            result[agente_id] = 0.0

        if event_type == AgentActivityEventV2.EventType.STATE_ON_HOLD:
            if hold_start is not None and current_agent == agente_id:
                # Segundo ON_HOLD sin OFF_HOLD: el hold anterior termina en este ts
                result[agente_id] += max(0, (ts - hold_start).total_seconds())
            elif hold_start is not None and current_agent != agente_id:
                # Cambio de agente con hold abierto: usar fin de rango
                hold_end = until if until <= now() else now()
                result[current_agent] += max(0, (hold_end - hold_start).total_seconds())
            hold_start = ts
            current_agent = agente_id
        elif event_type == AgentActivityEventV2.EventType.STATE_OFF_HOLD:
            if hold_start is not None and current_agent == agente_id:
                result[agente_id] += max(0, (ts - hold_start).total_seconds())
            hold_start = None
            current_agent = None

    # Si quedó un ON_HOLD sin OFF_HOLD al final del rango
    if hold_start is not None and current_agent is not None:
        hold_end = until if until <= now() else now()
        result[current_agent] += max(0, (hold_end - hold_start).total_seconds())

    return [{'agent_id': aid, 'hold_seconds': secs} for aid, secs in result.items()]


def get_agent_gestiones_count(since, until, agent_id=None):
    """
    Calcula cantidad de gestiones (ventas) por agente desde CalificacionCliente.
    Misma lógica que el dashboard del agente: calificaciones con opcion_calificacion.tipo=GESTION.

    Args:
        since: datetime aware, inicio del rango.
        until: datetime aware, fin del rango.
        agent_id: opcional, filtrar por agente.

    Returns:
        Lista de dicts con agent_id (int) y gestiones_count (int).
    """
    qs = CalificacionCliente.objects.using('replica').filter(
        fecha__gte=since,
        fecha__lte=until,
        opcion_calificacion__tipo=OpcionCalificacion.GESTION,
    )
    if agent_id is not None:
        qs = qs.filter(agente_id=agent_id)
    rows = qs.values('agente_id').annotate(gestiones_count=Count('id')).values_list(
        'agente_id', 'gestiones_count'
    )
    return [{'agent_id': aid, 'gestiones_count': count or 0} for aid, count in rows]
