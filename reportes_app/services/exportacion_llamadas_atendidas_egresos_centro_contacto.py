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
Servicio para exportar la tabla "Listado de llamadas atendidas" (Egresos/Voz)
del reporte centro de contacto a CSV. Usa Redis para notificar progreso vía WebSocket.
"""

from __future__ import unicode_literals

import csv
import logging
import os

import redis

from django.conf import settings
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

DIRECTORIO_REPORTE = 'reporte_centro_contacto'
PREFIJO_ARCHIVO = 'llamadas_atendidas_egresos'
KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_ATENDIDAS_EGRESOS_CC:cc:{task_id}'


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


def _format_fecha_hora_csv(dt):
    """Alinea con el filtro date en plantilla (hora local del sitio)."""
    if dt is None:
        return ''
    return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M:%S')


def generar_csv_llamadas_atendidas_egresos_centro_contacto(
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
    Genera el archivo CSV del Listado de llamadas atendidas (Egresos/Voz) y publica
    progreso en Redis (0 y 100). key_task debe ser OML:STATUS_CSV_REPORT:LLAMADAS_ATENDIDAS_EGRESOS_CC:cc:{task_id}.
    """
    from api_app.views.reports_centro_contacto import obtener_listado_llamadas_atendidas

    redis_conn = redis.Redis(
        host=settings.REDIS_HOSTNAME,
        port=settings.CONSTANCE_REDIS_CONNECTION['port'],
        decode_responses=True,
    )

    try:
        redis_conn.publish(key_task, 0)
    except Exception as e:
        logger.warning("Redis publish(0) llamadas atendidas egresos CC: %s", e)

    all_rows = []
    page_size = 2000
    page = 1
    try:
        while True:
            page_obj = obtener_listado_llamadas_atendidas(
                start_date=start_date,
                end_date=end_date,
                allowed_campaigns=allowed_campaigns,
                allowed_agent_ids=allowed_agent_ids,
                customer_id=customer_id,
                address_query=address_query,
                callid=callid,
                direction_filter='OUTBOUND',
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
                duracion_agente_min=duracion_agente_min,
                duracion_bot_min=duracion_bot_min,
                page=page,
                page_size=page_size,
            )
            all_rows.extend(page_obj.object_list)
            if not page_obj.has_next():
                break
            page += 1
    except Exception as e:
        logger.exception("Error obteniendo listado llamadas atendidas egresos: %s", e)
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
        _('Fecha/Hora'),
        _('Id contacto'),
        _('Teléfono'),
        _('Id campaña'),
        _('Nombre campaña'),
        _('Id agente'),
        _('Nombre agente'),
        _('Username agente'),
        _('Grupo de agente'),
        _('Tiempo espera'),
        _('Duración agente'),
        _('Duración bot'),
        _('Quien cortó'),
        _('Id calificación'),
        _('Nombre calificación'),
        _('Nombre subcalificación'),
        _('Grabación'),
    ]

    with open(ruta, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in all_rows:
            fecha_str = _format_fecha_hora_csv(row.get('fecha_hora'))
            writer.writerow([
                fecha_str,
                _to_str(row.get('id_contacto')),
                _to_str(row.get('telefono')),
                _to_str(row.get('id_campana')),
                _to_str(row.get('nombre_campana')),
                _to_str(row.get('id_agente')),
                _to_str(row.get('nombre_agente')),
                _to_str(row.get('username_agente')),
                _to_str(row.get('grupo_agente')),
                _format_seconds(row.get('tiempo_espera')),
                _format_seconds(row.get('duracion_agente')),
                _format_seconds(row.get('duracion_bot')),
                _to_str(row.get('quien_corto')),
                _to_str(row.get('id_calificacion')),
                _to_str(row.get('nombre_calificacion')),
                _to_str(row.get('nombre_subcalificacion')),
                _to_str(row.get('url_grabacion')),
            ])

    try:
        redis_conn.publish(key_task, 100)
    except Exception as e:
        logger.warning("Redis publish(100) llamadas atendidas egresos CC: %s", e)


def obtener_url_descarga_llamadas_atendidas_egresos(task_id):
    """
    Retorna la URL relativa a MEDIA_URL del CSV generado para task_id,
    o None si no existe.
    """
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE, filename)
    if os.path.exists(ruta):
        return os.path.join(settings.MEDIA_URL, DIRECTORIO_REPORTE, filename)
    return None
