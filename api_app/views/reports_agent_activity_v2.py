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
Endpoints de actividad de agentes (v2) para el Reporte de Performance.
GET  /api/v1/reportes/agents_activity_v2/?date_start=YYYY-MM-DD&date_end=YYYY-MM-DD
POST /api/v1/exportar_csv_agents_activity_v2_listado/
"""

import threading
import traceback as tb_module
from datetime import datetime

from django.conf import settings
from django.core.paginator import Paginator
from django.utils.translation import gettext_lazy as _
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from api_app.views.reports_agent_kpis_v2 import (
    _normalize_date,
    _build_availability_block,
    _build_interactions_block,
    _empty_availability,
    _empty_interactions,
)
from ominicontacto_app.models import AgenteProfile, Campana, Grupo
from ominicontacto_app.utiles import (
    convert_fecha_datetime,
    datetime_hora_minima_dia,
    datetime_hora_maxima_dia,
)
from reportes_app.services.agent_kpis_v2 import get_agent_activity_kpis_v2
from reportes_app.services.agent_interactions_kpis import (
    get_agent_gestiones_count,
    get_agent_hold_counts,
    get_agent_interactions_kpis,
    get_agent_transfer_counts,
    get_agent_transfer_in_counts,
    _get_agent_whatsapp_act_avg,
)
from reportes_app.services.exportacion_agents_activity_v2_listado import (
    KEY_TASK_TEMPLATE,
    generar_csv_agents_activity_v2_listado,
)


DATE_FMT = '%Y-%m-%d'
MAX_DAYS_RANGE = 31
TODOS_LOS_AGENTES_VALUE = '__all_agents__'
TODOS_LOS_GRUPOS_VALUE = '__all_groups__'
ALLOWED_PAGE_SIZES = (10, 20, 30, 40, 50)


def _item_to_flat_row(item):
    """
    Convierte un ítem con availability + interactions anidados al formato plano
    que espera el frontend (agents_activity_v2.js).
    """
    av = item.get('availability') or {}
    inter = item.get('interactions') or {}
    ready_ratio = av.get('ready_ratio') or 0
    pause_ratio = av.get('pause_ratio') or 0
    acw_ratio = av.get('acw_ratio') or 0
    total_interactions = inter.get('interactions_total') or 0
    transfer_count = item.get('transfer_count') or 0
    transfer_in_count = item.get('transfer_in_count') or 0
    transfer_pct = (
        round((float(transfer_count) / float(total_interactions)) * 100, 1)
        if total_interactions > 0 else 0.0
    )
    return {
        'agent_id': item.get('agent_id'),
        'agent_name': item.get('agent_name', ''),
        'session_seconds': av.get('session_seconds') or 0,
        'ready_seconds': av.get('ready_seconds') or 0,
        'ready_pct': round(ready_ratio * 100, 1) if ready_ratio is not None else 0,
        'pause_seconds': av.get('pause_seconds') or 0,
        'pause_pct': round(pause_ratio * 100, 1) if pause_ratio is not None else 0,
        'acw_seconds': av.get('acw_seconds') or 0,
        'acw_pct': round(acw_ratio * 100, 1) if acw_ratio is not None else 0,
        'total_interactions': total_interactions,
        'inbound_count': inter.get('interactions_inbound') or 0,
        'outbound_count': inter.get('interactions_outbound') or 0,
        'inbound_voice_count': inter.get('interactions_inbound_voice', 0),
        'outbound_voice_count': inter.get('interactions_outbound_voice', 0),
        'inbound_chat_count': inter.get('interactions_inbound_chat', 0),
        'outbound_chat_count': inter.get('interactions_outbound_chat', 0),
        'conversation_seconds': inter.get('talk_seconds') or 0,
        'tmo_avg': inter.get('avg_talk_seconds_answered') or 0,
        'act_avg': item.get('act_avg') or 0,
        'transfer_count': transfer_count,
        'transfer_in_count': transfer_in_count,
        'transfer_out_count': transfer_count,
        'transfer_pct': transfer_pct,
        'hold_count': item.get('hold_count') or 0,
        'gestiones_count': item.get('gestiones_count') or 0,
        'wait_conn_avg': inter.get('avg_wait_conn_duration') or 0,
    }


def _parse_yyyy_mm_dd_or_error(date_value, field_name):
    try:
        return datetime.strptime(date_value, DATE_FMT).date(), None
    except ValueError:
        return None, Response(
            {'error': '{} debe tener formato YYYY-MM-DD'.format(field_name)},
            status=status.HTTP_400_BAD_REQUEST,
        )


def _validate_range_or_error(date_start, date_end):
    if date_end < date_start:
        return Response(
            {'error': 'date_end debe ser mayor o igual a date_start'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    days_count = (date_end - date_start).days + 1
    if days_count > MAX_DAYS_RANGE:
        return Response(
            {'error': 'El rango no puede superar {} días'.format(MAX_DAYS_RANGE)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _iter_filtered_rows(rows, agent_ids_set):
    for row in rows:
        aid = row.get('agent_id')
        if aid is None:
            continue
        if agent_ids_set is not None and aid not in agent_ids_set:
            continue
        yield row


def get_agents_activity_v2_flat_rows(date_start, date_end, allowed_agent_ids=None):
    """
    Construye filas planas del reporte agents_activity_v2 para rango [date_start, date_end].
    Si allowed_agent_ids se informa, limita el merge a ese subconjunto.
    """
    since = datetime_hora_minima_dia(date_start)
    until = datetime_hora_maxima_dia(date_end)
    tz_name = getattr(settings, 'TIME_ZONE', None) or 'UTC'
    include_pause_breakdown = False
    agent_ids_set = set(allowed_agent_ids) if allowed_agent_ids is not None else None

    availability_response = get_agent_activity_kpis_v2(
        date_start=date_start.isoformat(),
        date_end=date_end.isoformat(),
        agent_id=None,
        group_by='agent',
    )
    availability_raw = availability_response.get('agents') or []
    availability_rows = []
    for row in availability_raw:
        aid = row.get('agente_id', row.get('agent_id'))
        if aid is None:
            continue
        if agent_ids_set is not None and aid not in agent_ids_set:
            continue
        availability_rows.append({
            'agent_id': aid,
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
        })

    interactions_rows = list(_iter_filtered_rows(
        get_agent_interactions_kpis(
            since=since,
            until=until,
            agent_id=None,
            group_by='agent',
            channel_type='VOICE',
            timezone_name=tz_name,
            include_whatsapp_in_out=True,
        ),
        agent_ids_set,
    ))
    transfer_rows = list(_iter_filtered_rows(
        get_agent_transfer_counts(
            since=since,
            until=until,
            agent_id=None,
            status_filter='OK',
        ),
        agent_ids_set,
    ))
    transfer_in_rows = list(_iter_filtered_rows(
        get_agent_transfer_in_counts(
            since=since,
            until=until,
            agent_id=None,
            status_filter='OK',
        ),
        agent_ids_set,
    ))
    hold_rows = list(_iter_filtered_rows(
        get_agent_hold_counts(since=since, until=until, agent_id=None),
        agent_ids_set,
    ))
    gestiones_rows = list(_iter_filtered_rows(
        get_agent_gestiones_count(since=since, until=until, agent_id=None),
        agent_ids_set,
    ))
    act_rows = list(_iter_filtered_rows(
        _get_agent_whatsapp_act_avg(since=since, until=until, agent_id=None),
        agent_ids_set,
    ))

    merged = {}
    for row in availability_rows:
        aid = row['agent_id']
        merged[aid] = {
            'agent_id': aid,
            'date': row.get('date'),
            'availability': _build_availability_block(row, include_pause_breakdown),
            'interactions': _empty_interactions(),
            'transfer_count': 0,
            'transfer_in_count': 0,
            'hold_count': 0,
            'gestiones_count': 0,
            'act_avg': 0,
        }
    for row in interactions_rows:
        aid = row['agent_id']
        if aid not in merged:
            merged[aid] = {
                'agent_id': aid,
                'date': _normalize_date(row.get('date')),
                'availability': _empty_availability(include_pause_breakdown),
                'interactions': _build_interactions_block(row),
                'transfer_count': 0,
                'transfer_in_count': 0,
                'hold_count': 0,
                'gestiones_count': 0,
                'act_avg': 0,
            }
        else:
            merged[aid]['interactions'] = _build_interactions_block(row)
    for row in transfer_rows:
        aid = row['agent_id']
        if aid not in merged:
            merged[aid] = {
                'agent_id': aid,
                'date': None,
                'availability': _empty_availability(include_pause_breakdown),
                'interactions': _empty_interactions(),
                'transfer_count': row.get('transfer_count') or 0,
                'transfer_in_count': 0,
                'hold_count': 0,
                'gestiones_count': 0,
                'act_avg': 0,
            }
        else:
            merged[aid]['transfer_count'] = row.get('transfer_count') or 0
    for row in transfer_in_rows:
        aid = row['agent_id']
        if aid not in merged:
            merged[aid] = {
                'agent_id': aid,
                'date': None,
                'availability': _empty_availability(include_pause_breakdown),
                'interactions': _empty_interactions(),
                'transfer_count': 0,
                'transfer_in_count': row.get('transfer_in_count') or 0,
                'hold_count': 0,
                'gestiones_count': 0,
                'act_avg': 0,
            }
        else:
            merged[aid]['transfer_in_count'] = row.get('transfer_in_count') or 0
    for row in hold_rows:
        aid = row['agent_id']
        if aid not in merged:
            merged[aid] = {
                'agent_id': aid,
                'date': None,
                'availability': _empty_availability(include_pause_breakdown),
                'interactions': _empty_interactions(),
                'transfer_count': 0,
                'transfer_in_count': 0,
                'hold_count': row.get('hold_count') or 0,
                'gestiones_count': 0,
                'act_avg': 0,
            }
        else:
            merged[aid]['hold_count'] = row.get('hold_count') or 0
    for row in gestiones_rows:
        aid = row['agent_id']
        if aid not in merged:
            merged[aid] = {
                'agent_id': aid,
                'date': None,
                'availability': _empty_availability(include_pause_breakdown),
                'interactions': _empty_interactions(),
                'transfer_count': 0,
                'transfer_in_count': 0,
                'hold_count': 0,
                'gestiones_count': row.get('gestiones_count') or 0,
                'act_avg': 0,
            }
        else:
            merged[aid]['gestiones_count'] = row.get('gestiones_count') or 0
    for row in act_rows:
        aid = row['agent_id']
        if aid not in merged:
            merged[aid] = {
                'agent_id': aid,
                'date': None,
                'availability': _empty_availability(include_pause_breakdown),
                'interactions': _empty_interactions(),
                'transfer_count': 0,
                'transfer_in_count': 0,
                'hold_count': 0,
                'gestiones_count': 0,
                'act_avg': row.get('act_avg') or 0,
            }
        else:
            merged[aid]['act_avg'] = row.get('act_avg') or 0

    ordered_agent_ids = sorted(merged.keys())
    agent_names = {}
    if ordered_agent_ids:
        for ap in AgenteProfile.objects.filter(id__in=ordered_agent_ids).select_related('user'):
            full_name = (ap.user.get_full_name() or ap.user.get_username() or '').strip()
            agent_names[ap.id] = full_name or 'Agente %s' % ap.id

    data = []
    for aid in ordered_agent_ids:
        item = merged[aid]
        item['agent_name'] = agent_names.get(item['agent_id'], 'Agente %s' % item['agent_id'])
        data.append(_item_to_flat_row(item))
    return data


def _get_post_list(data, key):
    val = data.get(key)
    if val is None and hasattr(data, 'getlist'):
        return data.getlist(key) or []
    if isinstance(val, (list, tuple)):
        return list(val)
    if val is not None and val != '':
        return [val]
    return []


def _get_campanas_visibles(user):
    if user.get_is_administrador():
        return Campana.objects.obtener_actuales()
    supervisor = user.get_supervisor_profile()
    return supervisor.campanas_asignadas_actuales()


def _compute_allowed_agent_ids(user, agentes_list, grupos_list):
    """
    Dado el usuario y las listas crudas de agente y grupo_agente (desde request),
    devuelve (allowed_agent_ids, None) o (None, error_response).
    """
    campanas_visibles = _get_campanas_visibles(user)
    visible_agent_ids = set(
        AgenteProfile.objects.filter(
            campana_member__queue_name__campana__in=campanas_visibles,
        ).distinct().values_list('id', flat=True)
    )
    visible_group_ids = set(
        Grupo.objects.filter(
            agentes__campana_member__queue_name__campana__in=campanas_visibles,
        ).distinct().values_list('id', flat=True)
    )

    grupos_seleccionados = list(grupos_list) if grupos_list else []
    if not grupos_seleccionados or TODOS_LOS_GRUPOS_VALUE in grupos_seleccionados:
        agent_ids_by_group = None
    else:
        try:
            selected_group_ids = [int(g) for g in grupos_seleccionados]
        except (TypeError, ValueError):
            return None, Response(
                {'error': _('Grupo de agentes inválido.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not set(selected_group_ids).issubset(visible_group_ids):
            return None, Response(
                {'error': _('Grupo de agentes inválido.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        agent_ids_by_group = set(
            AgenteProfile.objects.filter(
                grupo_id__in=selected_group_ids,
                campana_member__queue_name__campana__in=campanas_visibles,
            ).distinct().values_list('id', flat=True)
        )

    agentes_seleccionados = list(agentes_list) if agentes_list else []
    if not agentes_seleccionados or TODOS_LOS_AGENTES_VALUE in agentes_seleccionados:
        selected_agent_ids = None
    else:
        try:
            selected_agent_ids = set(int(a) for a in agentes_seleccionados)
        except (TypeError, ValueError):
            return None, Response(
                {'error': _('Agente inválido.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not selected_agent_ids.issubset(visible_agent_ids):
            return None, Response(
                {'error': _('Agente inválido.')},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if selected_agent_ids is None and agent_ids_by_group is None:
        allowed_agent_ids = sorted(visible_agent_ids)
    elif selected_agent_ids is None:
        allowed_agent_ids = sorted(agent_ids_by_group)
    elif agent_ids_by_group is None:
        allowed_agent_ids = sorted(selected_agent_ids)
    else:
        allowed_agent_ids = sorted(selected_agent_ids.intersection(agent_ids_by_group))

    return allowed_agent_ids, None


def _parse_export_filters(request):
    data = getattr(request, 'data', None) or {}

    task_id = data.get('task_id')
    if not task_id or not str(task_id).strip():
        return None, Response(
            {'error': _('Falta task_id')},
            status=status.HTTP_400_BAD_REQUEST,
        )
    task_id = str(task_id).strip()

    desde_str = (data.get('desde') or '').strip()
    hasta_str = (data.get('hasta') or '').strip()
    if not desde_str or not hasta_str:
        return None, Response(
            {'error': _('Indique rango de fechas (desde y hasta).')},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        desde_dt = convert_fecha_datetime(desde_str)
        hasta_dt = convert_fecha_datetime(hasta_str, final_dia=True)
    except (TypeError, ValueError, IndexError):
        return None, Response(
            {'error': _('Formato de fecha inválido. Use dd/mm/aaaa.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    date_start = desde_dt.date()
    date_end = hasta_dt.date()
    err = _validate_range_or_error(date_start, date_end)
    if err is not None:
        return None, err

    allowed_agent_ids, err = _compute_allowed_agent_ids(
        request.user,
        _get_post_list(data, 'agente'),
        _get_post_list(data, 'grupo_agente'),
    )
    if err is not None:
        return None, err

    return (task_id, date_start, date_end, allowed_agent_ids), None


class AgentsActivityV2ReportView(APIView):
    """
    GET /api/v1/reportes/agents_activity_v2/
    Params: date_start, date_end (YYYY-MM-DD); page, page_size (paginación);
    opc. agente, grupo_agente (listas). Devuelve data agregada por agente
    en formato plano para el Reporte de Performance, paginada.
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['get']

    def get(self, request):
        q = request.query_params or request.GET
        date_start_s = q.get('date_start')
        date_end_s = q.get('date_end')
        if not date_start_s or not date_end_s:
            return Response(
                {'error': 'date_start y date_end son obligatorios (formato YYYY-MM-DD)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_start, err = _parse_yyyy_mm_dd_or_error(date_start_s, 'date_start')
        if err is not None:
            return err
        date_end, err = _parse_yyyy_mm_dd_or_error(date_end_s, 'date_end')
        if err is not None:
            return err

        err = _validate_range_or_error(date_start, date_end)
        if err is not None:
            return err

        try:
            page_num = int(q.get('page') or 1)
        except (TypeError, ValueError):
            page_num = 1
        if page_num < 1:
            page_num = 1

        raw_page_size = q.get('page_size')
        try:
            page_size = int(raw_page_size) if raw_page_size else 10
        except (TypeError, ValueError):
            page_size = 10
        if page_size not in ALLOWED_PAGE_SIZES:
            page_size = 10

        agentes_list = q.getlist('agente') if hasattr(q, 'getlist') else []
        grupos_list = q.getlist('grupo_agente') if hasattr(q, 'getlist') else []
        allowed_agent_ids, err = _compute_allowed_agent_ids(
            request.user, agentes_list, grupos_list,
        )
        if err is not None:
            return err

        try:
            all_rows = get_agents_activity_v2_flat_rows(
                date_start=date_start,
                date_end=date_end,
                allowed_agent_ids=allowed_agent_ids,
            )
        except Exception as e:
            err_body = {'error': str(e)}
            if getattr(settings, 'DEBUG', False):
                err_body['traceback'] = tb_module.format_exc()
            return Response(err_body, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        paginator = Paginator(all_rows, page_size)
        total_count = len(all_rows)
        try:
            page_obj = paginator.page(page_num)
        except Exception:
            page_obj = paginator.page(1)
            page_num = 1
        data_page = list(page_obj.object_list)

        return Response({
            'group_by': 'agent',
            'data': data_page,
            'date_start': date_start.isoformat(),
            'date_end': date_end.isoformat(),
            'total_count': total_count,
            'page': page_num,
            'page_size': page_size,
            'num_pages': paginator.num_pages,
        }, status=status.HTTP_200_OK)


class ExportarCSVAgentsActivityV2Listado(APIView):
    """
    POST /api/v1/exportar_csv_agents_activity_v2_listado/
    Inicia exportación CSV asíncrona del tab Listado (agents-activity-v2).
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response

        task_id, date_start, date_end, allowed_agent_ids = parsed
        key_task = KEY_TASK_TEMPLATE.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_agents_activity_v2_listado,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'date_start': date_start,
                'date_end': date_end,
                'allowed_agent_ids': allowed_agent_ids,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Listado de Agentes (Performance) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )
