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
Servicio para exportar la tabla "Llamadas por hora de día" (Ingresos/Voz/Horas) del reporte
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
PREFIJO_ARCHIVO = 'llamadas_por_hora'
KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_POR_HORA_CC:cc:{task_id}'


def _to_str(value):
    if value is None:
        return ''
    return force_str(value)


def _format_seconds(value):
    """Formato de segundos para CSV (equivalente a format_seconds_int en template)."""
    if value is None:
        return ''
    try:
        sec = int(round(float(value)))
        return str(sec)
    except (TypeError, ValueError):
        return ''


def generar_csv_llamadas_por_hora_centro_contacto(
    key_task,
    task_id,
    start_date=None,
    end_date=None,
    allowed_campaigns=None,
    allowed_agent_ids=None,
    customer_id=None,
    address_query=None,
    hora_desde=None,
    hora_hasta=None,
    duracion_agente_min=None,
    duracion_bot_min=None,
):
    """
    Genera el archivo CSV de Llamadas por hora de día (Ingresos/Voz/Horas) y publica
    progreso en Redis (0 y 100). key_task debe ser OML:STATUS_CSV_REPORT:LLAMADAS_POR_HORA_CC:cc:{task_id}.
    """
    from api_app.views.reports_centro_contacto import obtener_llamadas_por_hora

    redis_conn = redis.Redis(
        host=settings.REDIS_HOSTNAME,
        port=settings.CONSTANCE_REDIS_CONNECTION['port'],
        decode_responses=True,
    )

    try:
        redis_conn.publish(key_task, 0)
    except Exception as e:
        logger.warning("Redis publish(0) llamadas por hora CC: %s", e)

    try:
        rows = obtener_llamadas_por_hora(
            start_date=start_date,
            end_date=end_date,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=customer_id,
            address_query=address_query,
            direction_filter='INBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
    except Exception as e:
        logger.exception("Error obteniendo llamadas por hora: %s", e)
        try:
            redis_conn.publish(key_task, 100)
        except Exception:
            pass
        return

    # Aplicar mismo filtro de rango horario que la vista (Ingresos/Voz/Horas)
    if rows and hora_desde is not None and hora_hasta is not None:
        hour_begin = hora_desde.hour
        hour_end = hora_hasta.hour
        if hour_begin <= hour_end:
            rows = [r for r in rows if hour_begin <= r['hour'] <= hour_end]
        else:
            rows = [
                r for r in rows
                if r['hour'] >= hour_begin or r['hour'] <= hour_end
            ]
            rows.sort(key=lambda r: (r['hour'] + 24) if r['hour'] < hour_begin else r['hour'])

    totals = None
    if rows:
        total_received = sum(r['received'] for r in rows)
        total_answered = sum(r['answered'] for r in rows)
        total_unanswered = sum(r['unanswered'] for r in rows)
        total_abandoned = sum(r['abandoned'] for r in rows)
        total_transferred = sum(r['transferred'] for r in rows)
        totals = {
            'received': total_received,
            'answered': total_answered,
            'unanswered': total_unanswered,
            'abandoned': total_abandoned,
            'transferred': total_transferred,
            'pct_answered': round(100.0 * total_answered / total_received, 2) if total_received else 0.0,
            'pct_unanswered': round(100.0 * total_unanswered / total_received, 2) if total_received else 0.0,
            'pct_abandoned': round(100.0 * total_abandoned / total_received, 2) if total_received else 0.0,
            'pct_transferred': round(100.0 * total_transferred / total_received, 2) if total_received else 0.0,
        }

    dir_abs = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE)
    if not os.path.exists(dir_abs):
        os.makedirs(dir_abs, mode=0o755)
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(dir_abs, filename)

    header = [
        _('Hora'),
        _('Recibidas'),
        _('Respondidas'),
        _('Expiradas'),
        _('Abandonadas'),
        _('Transferidas'),
        _('Espera prom.'),
        _('Habla prom.'),
        _('% Respondidas'),
        _('% Expiradas'),
        _('% Abandonadas'),
        _('% Transferidas'),
    ]

    with open(ruta, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow([
                _to_str(row.get('hour_label')),
                _to_str(row.get('received')),
                _to_str(row.get('answered')),
                _to_str(row.get('unanswered')),
                _to_str(row.get('abandoned')),
                _to_str(row.get('transferred')),
                _format_seconds(row.get('avg_wait_seconds')),
                _format_seconds(row.get('avg_talk_seconds')),
                _to_str(row.get('pct_answered')),
                _to_str(row.get('pct_unanswered')),
                _to_str(row.get('pct_abandoned')),
                _to_str(row.get('pct_transferred')),
            ])
        if totals:
            writer.writerow([
                _('Total'),
                _to_str(totals.get('received')),
                _to_str(totals.get('answered')),
                _to_str(totals.get('unanswered')),
                _to_str(totals.get('abandoned')),
                _to_str(totals.get('transferred')),
                '',
                '',
                _to_str(totals.get('pct_answered')),
                _to_str(totals.get('pct_unanswered')),
                _to_str(totals.get('pct_abandoned')),
                _to_str(totals.get('pct_transferred')),
            ])

    try:
        redis_conn.publish(key_task, 100)
    except Exception as e:
        logger.warning("Redis publish(100) llamadas por hora CC: %s", e)


def obtener_url_descarga_llamadas_por_hora(task_id):
    """
    Retorna la URL relativa a MEDIA_URL del CSV generado para task_id,
    o None si no existe.
    """
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE, filename)
    if os.path.exists(ruta):
        return os.path.join(settings.MEDIA_URL, DIRECTORIO_REPORTE, filename)
    return None
