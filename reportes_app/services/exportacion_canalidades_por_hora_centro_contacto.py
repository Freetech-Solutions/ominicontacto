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
Servicio para exportar la tabla "Canalidades por hora" del reporte
centro de contacto (Ingresos) a CSV. Usa Redis para notificar progreso vía WebSocket.
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
PREFIJO_ARCHIVO = 'canalidades_por_hora'
KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CANALIDADES_POR_HORA_CC:cc:{task_id}'


def _to_str(value):
    if value is None:
        return ''
    return force_str(value)


def generar_csv_canalidades_por_hora_centro_contacto(
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
    Genera el archivo CSV de Canalidades por hora (Ingresos) y publica
    progreso en Redis (0 y 100). key_task debe ser OML:STATUS_CSV_REPORT:CANALIDADES_POR_HORA_CC:cc:{task_id}.
    """
    from api_app.views.reports_centro_contacto import obtener_canalidades_por_hora

    redis_conn = redis.Redis(
        host=settings.REDIS_HOSTNAME,
        port=settings.CONSTANCE_REDIS_CONNECTION['port'],
        decode_responses=True,
    )

    try:
        redis_conn.publish(key_task, 0)
    except Exception as e:
        logger.warning("Redis publish(0) canalidades por hora CC: %s", e)

    try:
        rows, totals = obtener_canalidades_por_hora(
            start_date=start_date,
            end_date=end_date,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=customer_id,
            address_query=address_query,
            callid=callid,
            direction_filter='INBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
    except Exception as e:
        logger.exception("Error obteniendo canalidades por hora: %s", e)
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
        _('Hora'),
        _('Llamadas recibidas'),
        _('% llamadas atendidas'),
        _('% llamadas no atendidas'),
        _('WhatsApp recibidos'),
        _('% WhatsApp atendidos'),
        _('% WhatsApp no atendidos'),
        _('Facebook msn recibidos'),
        _('% Facebook msn atendidos'),
        _('% Facebook msn no atendidos'),
    ]

    with open(ruta, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow([
                _to_str(row.get('hour_label')),
                _to_str(row.get('llamadas_received')),
                _to_str(row.get('llamadas_pct_atendidas')),
                _to_str(row.get('llamadas_pct_no_atendidas')),
                _to_str(row.get('whatsapp_received')),
                _to_str(row.get('whatsapp_pct_atendidas')),
                _to_str(row.get('whatsapp_pct_no_atendidas')),
                _to_str(row.get('facebook_received')),
                _to_str(row.get('facebook_pct_atendidas')),
                _to_str(row.get('facebook_pct_no_atendidas')),
            ])
        if totals:
            writer.writerow([
                _('Total'),
                _to_str(totals.get('llamadas_received')),
                _to_str(totals.get('llamadas_pct_atendidas')),
                _to_str(totals.get('llamadas_pct_no_atendidas')),
                _to_str(totals.get('whatsapp_received')),
                _to_str(totals.get('whatsapp_pct_atendidas')),
                _to_str(totals.get('whatsapp_pct_no_atendidas')),
                _to_str(totals.get('facebook_received')),
                _to_str(totals.get('facebook_pct_atendidas')),
                _to_str(totals.get('facebook_pct_no_atendidas')),
            ])

    try:
        redis_conn.publish(key_task, 100)
    except Exception as e:
        logger.warning("Redis publish(100) canalidades por hora CC: %s", e)


def obtener_url_descarga_canalidades_por_hora(task_id):
    """
    Retorna la URL relativa a MEDIA_URL del CSV generado para task_id,
    o None si no existe.
    """
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE, filename)
    if os.path.exists(ruta):
        return os.path.join(settings.MEDIA_URL, DIRECTORIO_REPORTE, filename)
    return None
