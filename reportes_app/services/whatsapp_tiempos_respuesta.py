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
Servicio para calcular KPIs de Tiempos de Respuesta (FRT) y SLA de conversaciones WhatsApp.
Toda la lógica se ejecuta en base de datos vía Subquery/RawSQL/ExpressionWrapper.
"""
from datetime import date, datetime

from django.db.models import (
    BooleanField, Case, DateTimeField, DurationField, ExpressionWrapper, F,
    IntegerField, OuterRef, Q, Subquery, Value, When,
)
from django.db.models.expressions import RawSQL
from django.db.models.functions import Extract

from ominicontacto_app.utiles import datetime_hora_maxima_dia, datetime_hora_minima_dia
from whatsapp_app.models import ConversacionWhatsapp, MensajeWhatsapp


def _normalizar_fechas(fecha_inicio, fecha_fin):
    """Convierte fecha_inicio/fecha_fin a datetime (inicio/fin de día) si son date."""
    if isinstance(fecha_inicio, date) and not isinstance(fecha_inicio, datetime):
        fecha_inicio = datetime_hora_minima_dia(fecha_inicio)
    if isinstance(fecha_fin, date) and not isinstance(fecha_fin, datetime):
        fecha_fin = datetime_hora_maxima_dia(fecha_fin)
    return fecha_inicio, fecha_fin


def reporte_tiempos_respuesta_whatsapp(fecha_inicio, fecha_fin, sla_segundos=120):
    """
    Retorna un QuerySet de ConversacionWhatsapp en el rango de fechas dado, anotado con:
    - timestamp_primer_mensaje_cliente: timestamp del primer mensaje recibido (cliente).
    - timestamp_primera_respuesta_agente: timestamp del primer mensaje enviado por el agente
      después del primer mensaje del cliente.
    - frt_segundos: diferencia en segundos entre (2) y (1). NULL si no hay respuesta.
    - cumple_sla: True si frt_segundos <= sla_segundos (y no es NULL); False en caso contrario.

    No usa bucles en Python; todo se calcula en base de datos (Subquery, RawSQL, ExpressionWrapper).
    """
    fecha_inicio, fecha_fin = _normalizar_fechas(fecha_inicio, fecha_fin)

    # 1) Subquery: primer mensaje cliente (origen == conversation.destination)
    primer_mensaje_cliente = MensajeWhatsapp.objects.filter(
        conversation_id=OuterRef('pk'),
        origen=OuterRef('destination'),
    ).order_by('timestamp').values('timestamp')[:1]

    # 2) RawSQL: primera respuesta agente (origen == line.numero, timestamp > primer cliente)
    # Referenciamos la tabla externa por nombre; Django la usa en el FROM.
    tabla_conv = ConversacionWhatsapp._meta.db_table
    tabla_msg = MensajeWhatsapp._meta.db_table
    tabla_linea = ConversacionWhatsapp._meta.get_field('line').related_model._meta.db_table

    sql_primera_respuesta_agente = f"""
    (SELECT m2.timestamp
     FROM {tabla_msg} m2
     INNER JOIN {tabla_linea} l ON l.id = {tabla_conv}.line_id AND m2.origen = l.numero
     WHERE m2.conversation_id = {tabla_conv}.id
       AND m2.timestamp > (
           SELECT m.timestamp
           FROM {tabla_msg} m
           WHERE m.conversation_id = {tabla_conv}.id
             AND m.origen = {tabla_conv}.destination
           ORDER BY m.timestamp ASC
           LIMIT 1
       )
     ORDER BY m2.timestamp ASC
     LIMIT 1)
    """

    qs = (
        ConversacionWhatsapp.objects
        .filter(timestamp__gte=fecha_inicio, timestamp__lte=fecha_fin)
        .annotate(
            timestamp_primer_mensaje_cliente=Subquery(primer_mensaje_cliente, output_field=DateTimeField()),
            timestamp_primera_respuesta_agente=RawSQL(
                sql_primera_respuesta_agente, [], output_field=DateTimeField()
            ),
        )
    )

    # 3) frt_segundos: EXTRACT(EPOCH FROM (primera_respuesta - primer_cliente))
    # Anotamos la diferencia como DurationField y luego extraemos epoch (segundos).
    qs = qs.annotate(
        _frt_duration=ExpressionWrapper(
            F('timestamp_primera_respuesta_agente') - F('timestamp_primer_mensaje_cliente'),
            output_field=DurationField(),
        ),
    ).annotate(
        frt_segundos=ExpressionWrapper(
            Extract(F('_frt_duration'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )

    # 4) cumple_sla: True si frt_segundos no es NULL y frt_segundos <= sla_segundos
    qs = qs.annotate(
        cumple_sla=Case(
            When(
                Q(frt_segundos__isnull=False) & Q(frt_segundos__lte=sla_segundos),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        ),
    )

    return qs


def anotar_frt_y_duracion(qs):
    """
    Anota un QuerySet de ConversacionWhatsapp con:
    - frt_segundos: tiempo hasta primera respuesta del agente (segundos). NULL si no hay.
    - duracion_segundos: segundos entre timestamp y date_last_interaction. NULL si date_last_interaction es null.
    """
    # 1) Subquery: primer mensaje cliente
    primer_mensaje_cliente = MensajeWhatsapp.objects.filter(
        conversation_id=OuterRef('pk'),
        origen=OuterRef('destination'),
    ).order_by('timestamp').values('timestamp')[:1]

    tabla_conv = ConversacionWhatsapp._meta.db_table
    tabla_msg = MensajeWhatsapp._meta.db_table
    tabla_linea = ConversacionWhatsapp._meta.get_field('line').related_model._meta.db_table

    sql_primera_respuesta_agente = f"""
    (SELECT m2.timestamp
     FROM {tabla_msg} m2
     INNER JOIN {tabla_linea} l ON l.id = {tabla_conv}.line_id AND m2.origen = l.numero
     WHERE m2.conversation_id = {tabla_conv}.id
       AND m2.timestamp > (
           SELECT m.timestamp
           FROM {tabla_msg} m
           WHERE m.conversation_id = {tabla_conv}.id
             AND m.origen = {tabla_conv}.destination
           ORDER BY m.timestamp ASC
           LIMIT 1
       )
     ORDER BY m2.timestamp ASC
     LIMIT 1)
    """

    qs = qs.annotate(
        timestamp_primer_mensaje_cliente=Subquery(primer_mensaje_cliente, output_field=DateTimeField()),
        timestamp_primera_respuesta_agente=RawSQL(
            sql_primera_respuesta_agente, [], output_field=DateTimeField()
        ),
    ).annotate(
        _frt_duration=ExpressionWrapper(
            F('timestamp_primera_respuesta_agente') - F('timestamp_primer_mensaje_cliente'),
            output_field=DurationField(),
        ),
    ).annotate(
        frt_segundos=ExpressionWrapper(
            Extract(F('_frt_duration'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )

    # duracion_segundos: date_last_interaction - timestamp (epoch)
    qs = qs.annotate(
        _duracion_delta=ExpressionWrapper(
            F('date_last_interaction') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        duracion_segundos=ExpressionWrapper(
            Extract(F('_duracion_delta'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )

    return qs
