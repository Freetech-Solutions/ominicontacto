# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

# This file is part of OMniLeads

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#
from django.template import Library
from reportes_app.models import LlamadaLog

register = Library()


@register.simple_tag
def es_calificacion_llamada(grabacion, calificacion):
    """Determina si la calificación es la exacta de la llamada que generó
    la grabación
    """
    if grabacion.callid == calificacion.callid:
        return calificacion
    return False


@register.filter(name='select_contacto_id')
def select_contacto_id(grabacion):
    """Devuelve el id del contacto de la grabación"""
    # Manejar el caso donde contacto_id puede ser None
    if grabacion.contacto_id is None:
        # Si contacto_id es None, intentar obtenerlo de LlamadaLog
        llamada_log = LlamadaLog.objects.filter(callid=grabacion.callid).first()
        if llamada_log and llamada_log.contacto_id is not None:
            return llamada_log.contacto_id
        return None
    
    # Convertir a int de forma segura
    try:
        contacto_id_int = int(grabacion.contacto_id)
        if contacto_id_int == -1:
            # Si es -1, intentar obtener el contacto_id real de LlamadaLog
            llamada_log = LlamadaLog.objects.filter(callid=grabacion.callid).first()
            if llamada_log and llamada_log.contacto_id is not None:
                return llamada_log.contacto_id
            return contacto_id_int
        return contacto_id_int
    except (ValueError, TypeError):
        # Si no se puede convertir, retornar el valor original o None
        return grabacion.contacto_id if grabacion.contacto_id is not None else None
