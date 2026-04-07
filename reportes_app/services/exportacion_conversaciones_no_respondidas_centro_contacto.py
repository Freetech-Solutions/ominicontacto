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
Servicio para exportar la tabla "Conversaciones no respondidas" (Ingresos > WhatsApp)
del reporte centro de contacto a CSV. Usa Redis para notificar progreso vía WebSocket.
"""

from __future__ import unicode_literals

import csv
import logging
import os

import redis

from django.conf import settings
from django.db.models import Q
from django.utils.encoding import force_str
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

DIRECTORIO_REPORTE = 'reporte_centro_contacto'
PREFIJO_ARCHIVO = 'conversaciones_no_respondidas'
KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CONV_NO_RESP_CC:cc:{task_id}'


def _to_str(value):
    if value is None:
        return ''
    return force_str(value)


def generar_csv_conversaciones_no_respondidas_centro_contacto(
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
    Genera el archivo CSV de Conversaciones no respondidas (Ingresos WhatsApp) y publica
    progreso en Redis (0 y 100). key_task debe ser OML:STATUS_CSV_REPORT:CONV_NO_RESP_CC:cc:{task_id}.
    """
    from whatsapp_app.models import ConversacionWhatsapp
    from reportes_app.services.whatsapp_tiempos_respuesta import anotar_frt_y_duracion

    redis_conn = redis.Redis(
        host=settings.REDIS_HOSTNAME,
        port=settings.CONSTANCE_REDIS_CONNECTION['port'],
        decode_responses=True,
    )

    try:
        redis_conn.publish(key_task, 0)
    except Exception as e:
        logger.warning("Redis publish(0) conversaciones no respondidas CC: %s", e)

    try:
        qs = ConversacionWhatsapp.objects.conversaciones_entrantes_no_atendidas(
            start_date, end_date
        )
        if allowed_campaigns is not None:
            qs = qs.filter(
                Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
            )
        if allowed_agent_ids is not None:
            qs = qs.filter(agent_id__in=allowed_agent_ids)
        if customer_id is not None:
            qs = qs.filter(client_id=customer_id)
        if address_query:
            qs = qs.filter(destination__icontains=address_query)
        if hora_desde is not None:
            qs = qs.filter(timestamp__time__gte=hora_desde)
        if hora_hasta is not None:
            qs = qs.filter(timestamp__time__lte=hora_hasta)
        qs = qs.select_related(
            'campana',
            'agent',
            'agent__user',
            'agent__grupo',
            'client',
            'conversation_disposition',
            'conversation_disposition__opcion_calificacion',
        )
        qs = anotar_frt_y_duracion(qs).order_by('-timestamp')
    except Exception as e:
        logger.exception("Error obteniendo conversaciones no respondidas: %s", e)
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
        _('Id conversación'),
        _('Fecha/Hora'),
        _('Id contacto'),
        _('Whatsapp_id'),
        _('Client_id'),
        _('Id campaña'),
        _('Nombre campaña'),
        _('Id agente'),
        _('Nombre agente'),
        _('Username agente'),
        _('Grupo de agente'),
        _('Tiempo espera'),
        _('Duración'),
        _('Id calificación'),
        _('Nombre calificación'),
        _('Nombre subcalificación'),
    ]

    def _row_from_conv(conv):
        timestamp_str = ''
        if conv.timestamp:
            timestamp_str = conv.timestamp.strftime('%d/%m/%Y %H:%M')
        client_id = conv.client_id if conv.client_id is not None else ''
        whatsapp_id = _to_str(conv.whatsapp_id) if conv.whatsapp_id else ''
        campana_id = conv.campana_id if conv.campana_id is not None else ''
        campana_nombre = ''
        if conv.campana:
            campana_nombre = _to_str(conv.campana.nombre)
        agent_id = conv.agent_id if conv.agent_id is not None else ''
        agent_nombre = ''
        agent_username = ''
        grupo_nombre = ''
        if conv.agent:
            agent_nombre = _to_str(
                conv.agent.user.get_full_name() or conv.agent.user.username
            )
            agent_username = _to_str(conv.agent.user.username)
            if conv.agent.grupo:
                grupo_nombre = _to_str(conv.agent.grupo.nombre)
        frt = conv.frt_segundos if getattr(conv, 'frt_segundos', None) is not None else ''
        duracion = (
            conv.duracion_segundos
            if getattr(conv, 'duracion_segundos', None) is not None
            else ''
        )
        disp_id = (
            conv.conversation_disposition_id
            if conv.conversation_disposition_id is not None
            else ''
        )
        calif_nombre = ''
        subcalif = ''
        if conv.conversation_disposition:
            if conv.conversation_disposition.opcion_calificacion:
                calif_nombre = _to_str(
                    conv.conversation_disposition.opcion_calificacion.nombre
                )
            subcalif = _to_str(
                conv.conversation_disposition.subcalificacion or ''
            )
        return [
            _to_str(conv.id),
            timestamp_str,
            _to_str(client_id),
            whatsapp_id,
            _to_str(client_id),
            _to_str(campana_id),
            campana_nombre,
            _to_str(agent_id),
            agent_nombre,
            agent_username,
            grupo_nombre,
            _to_str(frt),
            _to_str(duracion),
            _to_str(disp_id),
            calif_nombre,
            subcalif,
        ]

    with open(ruta, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for conv in qs:
            writer.writerow(_row_from_conv(conv))

    try:
        redis_conn.publish(key_task, 100)
    except Exception as e:
        logger.warning("Redis publish(100) conversaciones no respondidas CC: %s", e)


def obtener_url_descarga_conversaciones_no_respondidas(task_id):
    """
    Retorna la URL relativa a MEDIA_URL del CSV generado para task_id,
    o None si no existe.
    """
    filename = '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id)
    ruta = os.path.join(settings.MEDIA_ROOT, DIRECTORIO_REPORTE, filename)
    if os.path.exists(ruta):
        return os.path.join(settings.MEDIA_URL, DIRECTORIO_REPORTE, filename)
    return None
