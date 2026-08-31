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
Servicio para exportar la tabla "Llamadas por día" (Egresos/Voz/Días) del reporte
centro de contacto a CSV. Usa Redis para notificar progreso vía WebSocket.
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

DIRECTORIO_REPORTE = 'reporte_centro_contacto'
PREFIJO_ARCHIVO = 'llamadas_por_dia_egresos'
KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_POR_DIA_EGRESOS_CC:cc:{task_id}'


def _to_str(value):
    if value is None:
        return ''
    return force_str(value)


def _dist_row_csv(row):
    return [
        _to_str(row.get('date_label')),
        _to_str(row.get('sent')),
        _to_str(row.get('pct_dist_conectadas_ag')),
        _to_str(row.get('pct_dist_abandonadas_espera')),
        _to_str(row.get('pct_dist_timeout_espera')),
        _to_str(row.get('pct_dist_shortcall')),
        _to_str(row.get('pct_dist_contestador')),
        _to_str(row.get('pct_dist_ocupado')),
        _to_str(row.get('pct_dist_cancel')),
        _to_str(row.get('pct_dist_error_contactacion')),
    ]


def generar_csv_llamadas_por_dia_egresos_centro_contacto(
    key_task,
    task_id,
    start_date=None,
    end_date=None,
    allowed_campaigns=None,
    allowed_agent_ids=None,
    customer_id=None,
    address_query=None,
    callid=None,
    hora_desde=None,
    hora_hasta=None,
    duracion_agente_min=None,
    duracion_bot_min=None,
):
    """
    Genera el archivo CSV de Llamadas por día (Egresos/Voz/Días) y publica
    progreso en Redis (0 y 100). key_task debe ser OML:STATUS_CSV_REPORT:LLAMADAS_POR_DIA_EGRESOS_CC:cc:{task_id}.
    """
    from api_app.views.reports_centro_contacto import obtener_llamadas_salientes_por_dia

    redis_conn = redis.Redis(
        host=settings.REDIS_HOSTNAME,
        port=settings.CONSTANCE_REDIS_CONNECTION['port'],
        decode_responses=True,
    )

    try:
        redis_conn.publish(key_task, 0)
    except Exception as e:
        logger.warning("Redis publish(0) llamadas por día egresos CC: %s", e)

    try:
        rows = obtener_llamadas_salientes_por_dia(
            start_date=start_date,
            end_date=end_date,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=customer_id,
            address_query=address_query,
            callid=callid,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
    except Exception as e:
        logger.exception("Error obteniendo llamadas salientes por día: %s", e)
        try:
            redis_conn.publish(key_task, 100)
        except Exception:
            pass
        return

    totals = None
    if rows:
        total_sent = sum(r['sent'] for r in rows)
        total_conectadas = sum(r['conectadas'] for r in rows)
        total_abandonadas_espera = sum(r['abandonadas_espera'] for r in rows)
        total_timeout_espera = sum(r['timeout_espera'] for r in rows)
        total_shortcall = sum(r['shortcall'] for r in rows)
        total_contestador = sum(r['contestador'] for r in rows)
        total_ocupado = sum(r['ocupado'] for r in rows)
        total_canceladas = sum(r['canceladas'] for r in rows)
        total_error_contactacion = sum(r['error_contactacion'] for r in rows)
        totals = {
            'date_label': _('Total'),
            'sent': total_sent,
            'pct_dist_conectadas_ag': round(100.0 * total_conectadas / total_sent, 2) if total_sent else 0.0,
            'pct_dist_abandonadas_espera': (
                round(100.0 * total_abandonadas_espera / total_sent, 2) if total_sent else 0.0
            ),
            'pct_dist_timeout_espera': (
                round(100.0 * total_timeout_espera / total_sent, 2) if total_sent else 0.0
            ),
            'pct_dist_shortcall': round(100.0 * total_shortcall / total_sent, 2) if total_sent else 0.0,
            'pct_dist_contestador': round(100.0 * total_contestador / total_sent, 2) if total_sent else 0.0,
            'pct_dist_ocupado': round(100.0 * total_ocupado / total_sent, 2) if total_sent else 0.0,
            'pct_dist_cancel': round(100.0 * total_canceladas / total_sent, 2) if total_sent else 0.0,
            'pct_dist_error_contactacion': (
                round(100.0 * total_error_contactacion / total_sent, 2) if total_sent else 0.0
            ),
        }

    dir_abs = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE)
    if not os.path.exists(dir_abs):
        os.makedirs(dir_abs, mode=0o755)
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(dir_abs, filename)

    header = [
        _('Fecha'),
        _('Llamadas enviadas (total)'),
        _('Conectadas Ag'),
        _('Abandonadas en espera'),
        _('Timeout de espera'),
        _('Short call'),
        _('Contestador Automático'),
        _('Ocupado'),
        _('Cancel'),
        _('Error de contactación'),
    ]

    with open(ruta, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(_dist_row_csv(row))
        if totals:
            writer.writerow(_dist_row_csv(totals))

    try:
        redis_conn.publish(key_task, 100)
    except Exception as e:
        logger.warning("Redis publish(100) llamadas por día egresos CC: %s", e)


def obtener_url_descarga_llamadas_por_dia_egresos(task_id):
    """
    Retorna la URL relativa a MEDIA_URL del CSV generado para task_id,
    o None si no existe.
    """
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE, filename)
    if os.path.exists(ruta):
        return os.path.join(settings.MEDIA_URL, DIRECTORIO_REPORTE, filename)
    return None
