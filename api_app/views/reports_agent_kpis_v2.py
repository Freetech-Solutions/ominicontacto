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
Endpoint unificado de KPIs de agentes: availability (AgentActivityEventV2),
interactions (interactions_summary VOICE) y derived.
GET /api/v1/reportes/agents_kpis_v2/
"""

import traceback as tb_module
from datetime import datetime

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.models import AgenteProfile
from ominicontacto_app.utiles import datetime_hora_minima_dia, datetime_hora_maxima_dia
from reportes_app.services.agent_kpis_v2 import get_agent_activity_kpis_v2
from reportes_app.services.agent_kpis_v2_helpers import (
    round_ratio,
    round_seconds,
    validate_agent_kpis_v2_invariants,
)
from reportes_app.services.agent_interactions_kpis import get_agent_interactions_kpis


DATE_FMT = '%Y-%m-%d'
MAX_DAYS_RANGE = 31


def _normalize_date(val):
    """Convierte date/datetime a string YYYY-MM-DD para claves de merge y payload JSON."""
    if val is None:
        return None
    if hasattr(val, 'isoformat'):
        if hasattr(val, 'date'):
            return val.date().isoformat()
        return val.isoformat()[:10]
    s = str(val)
    return s[:10] if len(s) >= 10 else s


def _parse_bool_param(value, default=True):
    """Acepta 1, 0, true, false, yes; default si no viene o inválido."""
    if value is None or value == '':
        return default
    v = str(value).strip().lower()
    if v in ('1', 'true', 'yes'):
        return True
    if v in ('0', 'false', 'no'):
        return False
    return default


def _empty_availability(include_pause_breakdown):
    out = {
        'session_seconds': 0,
        'ready_seconds': 0,
        'pause_seconds': 0,
        'acw_seconds': 0,
        'ready_ratio': 0,
        'pause_ratio': 0,
        'acw_ratio': 0,
        'sessions_count': 0,
        'pauses_count': 0,
        'acw_count': 0,
    }
    if include_pause_breakdown:
        out['pause_breakdown'] = []
    return out


def _empty_interactions():
    return {
        'interactions_total': 0,
        'interactions_inbound': 0,
        'interactions_outbound': 0,
        'interactions_inbound_voice': 0,
        'interactions_outbound_voice': 0,
        'interactions_inbound_chat': 0,
        'interactions_outbound_chat': 0,
        'answered_count': 0,
        'cancel_count': 0,
        'sales_count': 0,
        'talk_seconds': 0.0,
        'avg_talk_seconds_answered': 0.0,
        'wait_conn_duration': 0.0,
        'avg_wait_conn_duration': 0.0,
    }


def _build_availability_block(row, include_pause_breakdown):
    """Convierte una fila del service de availability al bloque availability del response.
    availability.*_seconds: int; ratios: float 4 decimales.
    """
    block = {
        'session_seconds': int(row.get('session_seconds') or 0),
        'ready_seconds': int(row.get('ready_seconds') or 0),
        'pause_seconds': int(row.get('pause_seconds') or 0),
        'acw_seconds': int(row.get('acw_seconds') or 0),
        'ready_ratio': round_ratio(row.get('ready_ratio'), 4),
        'pause_ratio': round_ratio(row.get('pause_ratio'), 4),
        'acw_ratio': round_ratio(row.get('acw_ratio'), 4),
        'sessions_count': row.get('sessions_count') or 0,
        'pauses_count': row.get('pauses_count') or 0,
        'acw_count': row.get('acw_count') or 0,
    }
    if include_pause_breakdown:
        block['pause_breakdown'] = row.get('pause_breakdown') or []
    return block


def _build_interactions_block(row):
    """Convierte una fila del service de interactions al bloque interactions del response.
    interactions.*_seconds: float, 3 decimales.
    """
    return {
        'interactions_total': row.get('interactions_total') or 0,
        'interactions_inbound': row.get('interactions_inbound') or 0,
        'interactions_outbound': row.get('interactions_outbound') or 0,
        'interactions_inbound_voice': row.get('interactions_inbound_voice', 0),
        'interactions_outbound_voice': row.get('interactions_outbound_voice', 0),
        'interactions_inbound_chat': row.get('interactions_inbound_chat', 0),
        'interactions_outbound_chat': row.get('interactions_outbound_chat', 0),
        'answered_count': row.get('answered_count') or 0,
        'cancel_count': row.get('cancel_count') or 0,
        'sales_count': row.get('sales_count') or 0,
        'talk_seconds': round_seconds(row.get('talk_seconds'), 3),
        'avg_talk_seconds_answered': round_seconds(row.get('avg_talk_seconds_answered'), 3),
        'wait_conn_duration': round_seconds(row.get('wait_conn_duration'), 3),
        'avg_wait_conn_duration': round_seconds(row.get('avg_wait_conn_duration'), 3),
    }


def _build_derived(availability_block, interactions_block):
    session_seconds = availability_block.get('session_seconds') or 0
    ready_seconds = availability_block.get('ready_seconds') or 0
    oncall_seconds = float(interactions_block.get('talk_seconds') or 0)
    sales_count = interactions_block.get('sales_count') or 0

    oncall_ratio = (oncall_seconds / session_seconds) if session_seconds else 0
    idle_real_seconds = max(ready_seconds - oncall_seconds, 0)
    session_hours = session_seconds / 3600.0 if session_seconds else 0
    sales_per_hour = (sales_count / session_hours) if session_hours else 0.0

    return {
        'oncall_seconds': round_seconds(oncall_seconds, 3),
        'oncall_ratio': round_ratio(oncall_ratio, 4),
        'idle_real_seconds': round_seconds(idle_real_seconds, 3),
        'sales_per_hour': round_ratio(sales_per_hour, 4),
    }


class AgentKpisV2ReportView(APIView):
    """
    GET /api/v1/reportes/agents_kpis_v2/
    Params obligatorios: date_start, date_end (YYYY-MM-DD).
    Opcionales: agent_id, group_by (agent|day), include_pause_breakdown,
    include_interactions, include_derived (1|0, default 1).
    """

    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['get']

    def get(self, request):
        date_start_s = request.GET.get('date_start')
        date_end_s = request.GET.get('date_end')
        if not date_start_s or not date_end_s:
            return Response(
                {'error': 'date_start y date_end son obligatorios (formato YYYY-MM-DD)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            date_start = datetime.strptime(date_start_s, DATE_FMT).date()
        except ValueError:
            return Response(
                {'error': 'date_start debe tener formato YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            date_end = datetime.strptime(date_end_s, DATE_FMT).date()
        except ValueError:
            return Response(
                {'error': 'date_end debe tener formato YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if date_end < date_start:
            return Response(
                {'error': 'date_end debe ser mayor o igual a date_start'},
                status=status.HTTP_400_BAD_REQUEST
            )
        days_count = (date_end - date_start).days + 1
        if days_count > MAX_DAYS_RANGE:
            return Response(
                {'error': 'El rango no puede superar {} días'.format(MAX_DAYS_RANGE)},
                status=status.HTTP_400_BAD_REQUEST
            )

        group_by = request.GET.get('group_by', 'day').strip().lower()
        if group_by not in ('agent', 'day'):
            group_by = 'day'

        include_pause_breakdown = _parse_bool_param(request.GET.get('include_pause_breakdown'), True)
        include_interactions = _parse_bool_param(request.GET.get('include_interactions'), True)
        include_derived = _parse_bool_param(request.GET.get('include_derived'), True)

        agent_id = request.GET.get('agent_id')
        if agent_id is not None:
            try:
                agent_id = int(agent_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'agent_id debe ser un entero'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        since = datetime_hora_minima_dia(date_start)
        until = datetime_hora_maxima_dia(date_end)
        tz_name = getattr(settings, 'TIME_ZONE', None) or 'UTC'

        try:
            availability_response = get_agent_activity_kpis_v2(
                date_start=date_start.isoformat(),
                date_end=date_end.isoformat(),
                agent_id=agent_id,
                group_by=group_by,
            )
        except Exception as e:
            err_body = {'error': str(e)}
            if getattr(settings, 'DEBUG', False):
                err_body['traceback'] = tb_module.format_exc()
            return Response(err_body, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        availability_raw = availability_response.get('agents') or []
        try:
            # Normalizar filas: el servicio devuelve agente_id y puede no incluir pauses_count/acw_count
            availability_rows = []
            for row in availability_raw:
                normalized = {
                    'agent_id': row.get('agente_id', row.get('agent_id')),
                    'date': _normalize_date(row.get('date')),
                    'session_seconds': row.get('session_seconds', 0),
                    'ready_seconds': row.get('ready_seconds', 0),
                    'pause_seconds': row.get('pause_seconds', 0),
                    'acw_seconds': row.get('acw_seconds', 0),
                    'ready_ratio': row.get('ready_ratio', 0),
                    'pause_ratio': row.get('pause_ratio', 0),
                    'acw_ratio': row.get('acw_ratio', 0),
                    'sessions_count': row.get('sessions_count', 0),
                    'pauses_count': row.get('pauses_count', 0),
                    'acw_count': row.get('acw_count', 0),
                    'pause_breakdown': row.get('pause_breakdown', []) if include_pause_breakdown else [],
                }
                availability_rows.append(normalized)

            # 2) Interactions (si se piden interactions o derived)
            interactions_rows = []
            if include_interactions or include_derived:
                interactions_rows = get_agent_interactions_kpis(
                    since=since,
                    until=until,
                    agent_id=agent_id,
                    group_by=group_by,
                    channel_type='VOICE',
                    timezone_name=tz_name,
                )

            # 3) Merge por (agent_id, date) o (agent_id, None); date normalizado a string para coincidir
            merged = {}
            for row in availability_rows:
                key = (row['agent_id'], row.get('date'))
                merged[key] = {
                    'agent_id': row['agent_id'],
                    'date': row.get('date'),
                    'availability': _build_availability_block(row, include_pause_breakdown),
                    'interactions': _empty_interactions(),
                }
            for row in interactions_rows:
                key = (row['agent_id'], _normalize_date(row.get('date')))
                if key not in merged:
                    merged[key] = {
                        'agent_id': row['agent_id'],
                        'date': _normalize_date(row.get('date')),
                        'availability': _empty_availability(include_pause_breakdown),
                        'interactions': _build_interactions_block(row),
                    }
                else:
                    merged[key]['interactions'] = _build_interactions_block(row)

            # 4) Derived y ordenar data
            if group_by == 'day':
                sorted_keys = sorted(merged.keys(), key=lambda k: (k[1] or '', k[0]))
            else:
                sorted_keys = sorted(merged.keys(), key=lambda k: k[0])

            agent_ids = list({key[0] for key in sorted_keys})
            agent_names = {}
            if agent_ids:
                for ap in AgenteProfile.objects.filter(id__in=agent_ids).select_related('user'):
                    agent_names[ap.id] = (ap.user.get_full_name() or ap.user.get_username() or '').strip() or 'Agente %s' % ap.id

            strict_validation = getattr(settings, 'REPORTES_KPIS_V2_STRICT_VALIDATION', False)
            data = []
            for key in sorted_keys:
                item = merged[key]
                if include_derived:
                    item['derived'] = _build_derived(item['availability'], item['interactions'])
                item['agent_name'] = agent_names.get(item['agent_id'], 'Agente %s' % item['agent_id'])
                try:
                    validate_agent_kpis_v2_invariants(item, strict=strict_validation)
                except ValueError as e:
                    if strict_validation:
                        return Response(
                            {'error': 'Validación de invariantes fallida: {}'.format(str(e))},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                data.append(item)

            payload = {
                'date_start': date_start.isoformat(),
                'date_end': date_end.isoformat(),
                'since': since.isoformat(),
                'until': until.isoformat(),
                'group_by': group_by,
                'data': data,
            }
            return Response(payload, status=status.HTTP_200_OK)
        except Exception as e:
            err_body = {'error': str(e)}
            if getattr(settings, 'DEBUG', False):
                err_body['traceback'] = tb_module.format_exc()
            return Response(err_body, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
