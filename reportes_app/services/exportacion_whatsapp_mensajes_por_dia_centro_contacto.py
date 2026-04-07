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
Servicio para exportar la tabla "Mensajes por día" (Ingresos > WhatsApp > Días)
del reporte centro de contacto a CSV. Usa Redis para notificar progreso vía WebSocket.
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
PREFIJO_ARCHIVO = 'whatsapp_mensajes_por_dia'
KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:WA_MSG_DIA:cc:{task_id}'


def _to_str(value):
    if value is None:
        return ''
    return force_str(value)


def _format_seconds_csv(seconds):
    """Formato para CSV: segundos enteros o vacío (como en template format_seconds_int)."""
    if seconds is None:
        return ''
    try:
        return str(int(round(float(seconds))))
    except (TypeError, ValueError):
        return ''


def generar_csv_whatsapp_mensajes_por_dia(
    key_task,
    task_id,
    start_date=None,
    end_date=None,
    allowed_campaigns=None,
    allowed_agent_ids=None,
    address_query=None,
    hora_desde=None,
    hora_hasta=None,
    duracion_agente_min=None,
    duracion_bot_min=None,
):
    """
    Genera el archivo CSV de Mensajes por día (WhatsApp Ingresos) y publica
    progreso en Redis (0 y 100). key_task debe ser OML:STATUS_CSV_REPORT:WA_MSG_DIA:cc:{task_id}.
    """
    from api_app.views.reports_centro_contacto import obtener_whatsapp_mensajes_por_dia

    redis_conn = redis.Redis(
        host=settings.REDIS_HOSTNAME,
        port=settings.CONSTANCE_REDIS_CONNECTION['port'],
        decode_responses=True,
    )

    try:
        redis_conn.publish(key_task, 0)
    except Exception as e:
        logger.warning("Redis publish(0) whatsapp mensajes por dia: %s", e)

    try:
        rows, totals = obtener_whatsapp_mensajes_por_dia(
            start_date=start_date,
            end_date=end_date,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
        )
    except Exception as e:
        logger.exception("Error obteniendo whatsapp mensajes por dia: %s", e)
        try:
            redis_conn.publish(key_task, 100)
        except Exception:
            pass
        return

    dir_abs = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE)
    if not os.path.exists(dir_abs):
        os.makedirs(dir_abs, mode=0o755)
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(dir_abs, filename)

    header = [
        _('Fecha'),
        _('Recibidos'),
        _('Respondidos'),
        _('No respondidos'),
        _('T. Espera prom.'),
        _('T. Habla prom.'),
        _('% Respondidas'),
        _('% No respondidos'),
    ]

    with open(ruta, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow([
                _to_str(row.get('fecha_label')),
                _to_str(row.get('recibidos')),
                _to_str(row.get('respondidos')),
                _to_str(row.get('no_respondidos')),
                _format_seconds_csv(row.get('avg_frt_segundos')),
                _format_seconds_csv(row.get('avg_duracion_segundos')),
                _to_str(row.get('pct_respondidas')) if row.get('pct_respondidas') is not None else '',
                _to_str(row.get('pct_no_respondidos')) if row.get('pct_no_respondidos') is not None else '',
            ])
        if totals:
            writer.writerow([
                _('Total'),
                _to_str(totals.get('recibidos')),
                _to_str(totals.get('respondidos')),
                _to_str(totals.get('no_respondidos')),
                _format_seconds_csv(totals.get('avg_frt_segundos')),
                _format_seconds_csv(totals.get('avg_duracion_segundos')),
                _to_str(totals.get('pct_respondidas')) if totals.get('pct_respondidas') is not None else '',
                _to_str(totals.get('pct_no_respondidos')) if totals.get('pct_no_respondidos') is not None else '',
            ])

    try:
        redis_conn.publish(key_task, 100)
    except Exception as e:
        logger.warning("Redis publish(100) whatsapp mensajes por dia: %s", e)


def obtener_url_descarga_whatsapp_mensajes_por_dia(task_id):
    """
    Retorna la URL relativa a MEDIA_URL del CSV generado para task_id,
    o None si no existe.
    """
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE, filename)
    if os.path.exists(ruta):
        return os.path.join(settings.MEDIA_URL, DIRECTORIO_REPORTE, filename)
    return None
