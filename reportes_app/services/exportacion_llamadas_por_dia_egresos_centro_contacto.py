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


def _format_seconds(value):
    """Formato de segundos para CSV (equivalente a format_seconds_int en template)."""
    if value is None:
        return ''
    try:
        sec = int(round(float(value)))
        return str(sec)
    except (TypeError, ValueError):
        return ''


def generar_csv_llamadas_por_dia_egresos_centro_contacto(
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
        total_canceladas = sum(r['canceladas'] for r in rows)
        total_no_atiende = sum(r['no_atiende'] for r in rows)
        total_ocupado = sum(r['ocupado'] for r in rows)
        total_contestador = sum(r['contestador'] for r in rows)
        total_shortcall = sum(r['shortcall'] for r in rows)
        total_congestion = sum(r['congestion'] for r in rows)
        total_otro_error = sum(r['otro_error'] for r in rows)
        total_transferred = sum(r['transferred'] for r in rows)
        totals = {
            'sent': total_sent,
            'conectadas': total_conectadas,
            'canceladas': total_canceladas,
            'no_atiende': total_no_atiende,
            'ocupado': total_ocupado,
            'contestador': total_contestador,
            'shortcall': total_shortcall,
            'congestion': total_congestion,
            'otro_error': total_otro_error,
            'transferred': total_transferred,
            'pct_conectadas': round(100.0 * total_conectadas / total_sent, 2) if total_sent else 0.0,
            'pct_no_conectadas': round(100.0 * (total_sent - total_conectadas) / total_sent, 2) if total_sent else 0.0,
        }

    dir_abs = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE)
    if not os.path.exists(dir_abs):
        os.makedirs(dir_abs, mode=0o755)
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(dir_abs, filename)

    header = [
        _('Fecha'),
        _('Enviadas'),
        _('Conectadas'),
        _('Canceladas'),
        _('Sin respuesta'),
        _('Ocupado'),
        _('Contestador'),
        _('Shortcall'),
        _('Congestion'),
        _('Otro'),
        _('Transferidas'),
        _('Espera prom.'),
        _('Habla prom.'),
        _('% Conectadas'),
        _('% No conectadas'),
    ]

    with open(ruta, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow([
                _to_str(row.get('date_label')),
                _to_str(row.get('sent')),
                _to_str(row.get('conectadas')),
                _to_str(row.get('canceladas')),
                _to_str(row.get('no_atiende')),
                _to_str(row.get('ocupado')),
                _to_str(row.get('contestador')),
                _to_str(row.get('shortcall')),
                _to_str(row.get('congestion')),
                _to_str(row.get('otro_error')),
                _to_str(row.get('transferred')),
                _format_seconds(row.get('avg_wait_seconds')),
                _format_seconds(row.get('avg_talk_seconds')),
                _to_str(row.get('pct_conectadas')),
                _to_str(row.get('pct_no_conectadas')),
            ])
        if totals:
            writer.writerow([
                _('Total'),
                _to_str(totals.get('sent')),
                _to_str(totals.get('conectadas')),
                _to_str(totals.get('canceladas')),
                _to_str(totals.get('no_atiende')),
                _to_str(totals.get('ocupado')),
                _to_str(totals.get('contestador')),
                _to_str(totals.get('shortcall')),
                _to_str(totals.get('congestion')),
                _to_str(totals.get('otro_error')),
                _to_str(totals.get('transferred')),
                '',
                '',
                _to_str(totals.get('pct_conectadas')),
                _to_str(totals.get('pct_no_conectadas')),
            ])

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
