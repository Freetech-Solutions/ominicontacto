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
Servicio para exportar la tabla Listado de agents_activity_v2 a CSV.
Usa Redis para notificar progreso vía WebSocket.
"""

from __future__ import unicode_literals

import csv
import logging
import os

import redis

from django.conf import settings
from django.utils.encoding import force_str
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

DIRECTORIO_REPORTE = 'reporte_agents_activity_v2'
PREFIJO_ARCHIVO = 'agents_activity_listado'
KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:AGENTS_ACTIVITY_LISTADO:cc:{task_id}'


def _to_str(value):
    if value is None:
        return ''
    return force_str(value)


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value):
    return int(round(_safe_float(value)))


def _format_seconds_hhmmss(value):
    total_seconds = max(0, _safe_int(value))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return '{:02d}:{:02d}:{:02d}'.format(hours, minutes, seconds)


def _format_pct_1d(value):
    return '{:.1f}'.format(_safe_float(value))


def _build_totals_row(rows):
    session_seconds = sum(_safe_float(r.get('session_seconds')) for r in rows)
    ready_seconds = sum(_safe_float(r.get('ready_seconds')) for r in rows)
    pause_seconds = sum(_safe_float(r.get('pause_seconds')) for r in rows)
    acw_seconds = sum(_safe_float(r.get('acw_seconds')) for r in rows)

    ready_pct = (ready_seconds * 100.0 / session_seconds) if session_seconds > 0 else 0.0
    pause_pct = (pause_seconds * 100.0 / session_seconds) if session_seconds > 0 else 0.0
    acw_pct = (acw_seconds * 100.0 / session_seconds) if session_seconds > 0 else 0.0

    return {
        'agent_name': _('Total'),
        'agent_id': '',
        'session_seconds': session_seconds,
        'ready_seconds': ready_seconds,
        'ready_pct': ready_pct,
        'pause_seconds': pause_seconds,
        'pause_pct': pause_pct,
        'acw_seconds': acw_seconds,
        'acw_pct': acw_pct,
        'total_interactions': sum(_safe_int(r.get('total_interactions')) for r in rows),
        'gestiones_count': sum(_safe_int(r.get('gestiones_count')) for r in rows),
        'inbound_voice_count': sum(_safe_int(r.get('inbound_voice_count', 0)) for r in rows),
        'outbound_voice_count': sum(_safe_int(r.get('outbound_voice_count', 0)) for r in rows),
        'inbound_chat_count': sum(_safe_int(r.get('inbound_chat_count', 0)) for r in rows),
        'outbound_chat_count': sum(_safe_int(r.get('outbound_chat_count', 0)) for r in rows),
        'conversation_seconds': sum(_safe_float(r.get('conversation_seconds')) for r in rows),
        'tmo_avg': '',
        'act_avg': '',
        'transfer_in_count': sum(_safe_int(r.get('transfer_in_count')) for r in rows),
        'transfer_out_count': sum(_safe_int(r.get('transfer_out_count')) for r in rows),
        'hold_count': sum(_safe_int(r.get('hold_count')) for r in rows),
    }


def _csv_row_from_report_row(row, is_total=False):
    tmo = '' if is_total else _format_seconds_hhmmss(row.get('tmo_avg'))
    act = '' if is_total else _format_seconds_hhmmss(row.get('act_avg'))
    return [
        _to_str(row.get('agent_name')),
        _to_str(row.get('agent_id')),
        _format_seconds_hhmmss(row.get('session_seconds')),
        _format_seconds_hhmmss(row.get('ready_seconds')),
        _format_pct_1d(row.get('ready_pct')),
        _format_seconds_hhmmss(row.get('pause_seconds')),
        _format_pct_1d(row.get('pause_pct')),
        _format_seconds_hhmmss(row.get('acw_seconds')),
        _format_pct_1d(row.get('acw_pct')),
        _to_str(_safe_int(row.get('total_interactions'))),
        _to_str(_safe_int(row.get('gestiones_count'))),
        _to_str(_safe_int(row.get('inbound_voice_count', 0))),
        _to_str(_safe_int(row.get('outbound_voice_count', 0))),
        _to_str(_safe_int(row.get('inbound_chat_count', 0))),
        _to_str(_safe_int(row.get('outbound_chat_count', 0))),
        _format_seconds_hhmmss(row.get('conversation_seconds')),
        tmo,
        act,
        _to_str(_safe_int(row.get('transfer_in_count'))),
        _to_str(_safe_int(row.get('transfer_out_count'))),
        _to_str(_safe_int(row.get('hold_count'))),
    ]


def generar_csv_agents_activity_v2_listado(
    key_task,
    task_id,
    date_start,
    date_end,
    allowed_agent_ids=None,
):
    """
    Genera el archivo CSV de Listado (agents_activity_v2) y publica progreso
    en Redis (0 y 100).
    """
    redis_conn = redis.Redis(
        host=settings.REDIS_HOSTNAME,
        port=settings.CONSTANCE_REDIS_CONNECTION['port'],
        decode_responses=True,
    )

    try:
        redis_conn.publish(key_task, 0)
    except Exception as e:
        logger.warning('Redis publish(0) agents activity listado: %s', e)

    try:
        from api_app.views.reports_agent_activity_v2 import get_agents_activity_v2_flat_rows

        rows = get_agents_activity_v2_flat_rows(
            date_start=date_start,
            date_end=date_end,
            allowed_agent_ids=allowed_agent_ids,
        )

        totals_row = _build_totals_row(rows)

        dir_abs = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE)
        if not os.path.exists(dir_abs):
            os.makedirs(dir_abs, mode=0o755)
        filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
        filepath = os.path.join(dir_abs, filename)

        header = [
            _('Agente'),
            _('ID Agente'),
            _('Sesión'),
            _('Ready'),
            _('% Ready'),
            _('Pause'),
            _('% Pause'),
            _('ACW'),
            _('% ACW'),
            _('Total'),
            _('Gestiones'),
            _('Llamadas In'),
            _('Llamadas Out'),
            _('Chat In'),
            _('Chat Out'),
            _('Talk Time'),
            _('ATT'),
            _('ACT'),
            _('Transfer In'),
            _('Transfer Out'),
            _('Hold'),
        ]

        with open(filepath, 'w', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(header)
            for row in rows:
                writer.writerow(_csv_row_from_report_row(row, is_total=False))
            writer.writerow(_csv_row_from_report_row(totals_row, is_total=True))
    except Exception as e:
        logger.exception('Error generando CSV agents activity listado: %s', e)
    finally:
        try:
            redis_conn.publish(key_task, 100)
        except Exception as e:
            logger.warning('Redis publish(100) agents activity listado: %s', e)


def obtener_url_descarga_agents_activity_v2_listado(task_id):
    """
    Retorna la URL relativa a MEDIA_URL del CSV generado para task_id,
    o None si no existe.
    """
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    filepath = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE, filename)
    if os.path.exists(filepath):
        return os.path.join(settings.MEDIA_URL, DIRECTORIO_REPORTE, filename)
    return None
