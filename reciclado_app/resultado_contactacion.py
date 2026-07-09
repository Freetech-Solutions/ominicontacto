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

"""
En este modulo se van obtener las estadisticas, de los registros que no fueron
contactados(RS_BUSY, RS_NOANSWER, etc)

contactados(hoy en dia por las calificaciones(calificacioncliente))
"""

from collections import Counter

from django.db import connections
from django.utils.translation import gettext as _
from django.db.models import Count
from ominicontacto_app.models import Campana, CalificacionCliente
from reportes_app.models import InteractionsSummary


def _status_hangup_to_reciclado_id(status, hangup_cause):
    """
    Mapea (status, hangup_cause) de InteractionsSummary al id de estado
    de reciclado (0-11). Equivalencias: EXIT_TIMEOUT -> 8,
    EXIT_ABANDON/ABANDONWEL/EXIT_ABANDON_WEL -> 9.
    """
    status = (status or '').strip().upper() or None
    hc = (hangup_cause or '').strip().upper() or None
    idx_otro = 4  # OTHER
    # IDs alineados con EstadisticasContactacion.MAP_ESTADO_ID / TXT_ESTADO
    cause_to_id = {
        'NOANSWER': 0,
        'CANCEL': 1,
        'BUSY': 2,
        'CHANUNAVAIL': 3,
        'OTHER': 4,
        'FAIL': 5,
        'EXIT_AMD': 6,
        'BLACKLIST': 7,
        'EXIT_TIMEOUT': 8,
        'EXITWITHTIMEOUT': 8,
        'EXIT_HANDOFF_TIMEOUT': 8,
        'EXIT_ABANDON': 9,
        'EXIT_HANDOFF_ABANDON': 9,
        'EXIT_ABANDON_WEL': 9,
        'ABANDON': 9,
        'CONGESTION': 10,
        'NONDIALPLAN': 11,
    }
    for key, rec_id in cause_to_id.items():
        if hc == key or status == key:
            return rec_id
    return idx_otro


def _normalize_contact_ids(ids_contactos_base_actual):
    if hasattr(ids_contactos_base_actual, '__iter__') and not isinstance(
            ids_contactos_base_actual, (str, bytes)):
        return list(ids_contactos_base_actual)
    return list(ids_contactos_base_actual)


def _fetch_ultimas_interacciones_por_contacto(campana, ids_contactos_base_actual):
    """
    Devuelve la última interacción VOICE OUTBOUND por customer_id usando DISTINCT ON.
    Una fila por contacto con customer_id, status, hangup_cause y start_time.
    """
    ids_list = _normalize_contact_ids(ids_contactos_base_actual)
    if not ids_list:
        return []

    sql = """
        SELECT DISTINCT ON (customer_id)
               customer_id, status, hangup_cause, start_time
        FROM public.interactions_summary
        WHERE campaign_id = %(campaign_id)s
          AND UPPER(TRIM(channel_type)) = 'VOICE'
          AND UPPER(TRIM(direction)) = 'OUTBOUND'
          AND customer_id IS NOT NULL
          AND customer_id = ANY(%(customer_ids)s)
          AND start_time >= %(fecha_alta)s
        ORDER BY customer_id, start_time DESC
    """
    params = {
        'campaign_id': campana.id,
        'customer_ids': ids_list,
        'fecha_alta': campana.bd_contacto.fecha_alta,
    }
    with connections['replica'].cursor() as cursor:
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _get_interactions_base_queryset(campana, ids_contactos_base_actual):
    """Queryset base de InteractionsSummary para campaña y contactos de la base actual."""
    ids_list = _normalize_contact_ids(ids_contactos_base_actual)
    if not ids_list:
        return InteractionsSummary.objects.none()
    qs = InteractionsSummary.objects.using('replica').filter(
        campaign_id=campana.id,
        channel_type__iexact='VOICE',
        direction__iexact='OUTBOUND',
        customer_id__in=ids_list,
        start_time__gte=campana.bd_contacto.fecha_alta,
        customer_id__isnull=False,
    )
    return qs


def _get_contactados_ultima_interaccion(campana, ids_contactos_base_actual, ultimas=None):
    """
    Devuelve el set de customer_id (contacto_id) cuya última interacción
    en la campaña tiene status EXIT_ANSWERED.
    """
    if ultimas is None:
        ultimas = _fetch_ultimas_interacciones_por_contacto(campana, ids_contactos_base_actual)
    return {
        row['customer_id']
        for row in ultimas
        if (row.get('status') or '').strip().upper() == 'EXIT_ANSWERED'
    }


class EstadisticasContactacion():

    MAP_ESTADO_ID = {
        'NOANSWER': 0,
        'CANCEL': 1,
        'BUSY': 2,
        'CHANUNAVAIL': 3,
        'OTHER': 4,
        'FAIL': 5,
        'EXIT_AMD': 6,
        'BLACKLIST': 7,
        'EXITWITHTIMEOUT': 8,
        'ABANDON': 9,
        'CONGESTION': 10,
        'NONDIALPLAN': 11,
    }
    MAP_ID_ESTADO = dict(zip(MAP_ESTADO_ID.values(), MAP_ESTADO_ID.keys()))
    TXT_ESTADO = {
        0: _('No Contesta'),
        1: _('Cancelado'),
        2: _('Ocupado'),
        3: _('Canal no disponible'),
        4: _('Otro'),
        5: _('Falla'),
        6: _('Contestador'),
        7: _('Blacklist'),
        8: _('Expiradas'),
        9: _('Abandono'),
        10: _('Congestion'),
        11: _('Problema de enrutamiento')
    }
    AGENTE_NO_CALIFICO = 20

    def _contabilizar_llamados_no_calificados(self, count_estados, campana, contactados):
        # contactados: iterable de contacto_id/customer_id (contactados con EXIT_ANSWERED)
        id_calificados = set(CalificacionCliente.objects.filter(
            opcion_calificacion__campana_id=campana.id,
            contacto__bd_contacto=campana.bd_contacto).values_list('contacto_id', flat=True))
        contactados_set = set(contactados)
        no_calificados = len(contactados_set - id_calificados)
        if no_calificados > 0:
            estado = _(u"Agente no califico")
            id_estado = EstadisticasContactacion.AGENTE_NO_CALIFICO
            cantidad_contactacion = CantidadContactacion(id_estado, estado, no_calificados)
            count_estados.update({id_estado: cantidad_contactacion})

    def _contabilizar_llamados_no_contactados(self, count_estados, campana, contactados,
                                              ids_contactos_base_actual, ultimas=None):
        # Cantidades de no contactados por última interacción (InteractionsSummary)
        contactados_set = set(contactados)
        ids_set = set(_normalize_contact_ids(ids_contactos_base_actual))
        contactos_no_contactados_ids = ids_set - contactados_set
        if not contactos_no_contactados_ids:
            return
        if ultimas is None:
            ultimas = _fetch_ultimas_interacciones_por_contacto(
                campana, list(contactos_no_contactados_ids))
        else:
            ultimas = [
                row for row in ultimas
                if row['customer_id'] in contactos_no_contactados_ids
            ]
        id_counts = Counter()
        for row in ultimas:
            status = row.get('status')
            if (status or '').strip().upper() == 'EXIT_ANSWERED':
                continue
            hangup_cause = row.get('hangup_cause')
            id_estado = _status_hangup_to_reciclado_id(status, hangup_cause)
            if id_estado in EstadisticasContactacion.TXT_ESTADO:
                id_counts[id_estado] += 1
        for id_estado, cantidad in id_counts.items():
            estado = EstadisticasContactacion.TXT_ESTADO[id_estado]
            cantidad_contactacion = CantidadContactacion(id_estado, estado, cantidad)
            count_estados.update({id_estado: cantidad_contactacion})

    def obtener_cantidad_no_contactados(self, campana):
        """
        Obtiene los llamados no contactados por campana de contactos de la base actual.
        Usa InteractionsSummary (última interacción por contacto).
        """
        count_estados = {}
        ids_contactos_base_actual = list(
            campana.bd_contacto.contactos.values_list('id', flat=True))
        ultimas = _fetch_ultimas_interacciones_por_contacto(campana, ids_contactos_base_actual)
        contactados = _get_contactados_ultima_interaccion(
            campana, ids_contactos_base_actual, ultimas=ultimas)
        self._contabilizar_llamados_no_calificados(count_estados, campana, contactados)
        self._contabilizar_llamados_no_contactados(
            count_estados, campana, contactados, ids_contactos_base_actual, ultimas=ultimas)
        return count_estados

    def obtener_cantidad_calificacion(self, campana):
        """
        Obtiene las cantidad de llamadas por calificacion de la campana de
        contactos de la base actual
        :param campana: campana la cual se van obtiene las calificaciones
        :return: cantidad por calificacion
        """

        calificaciones_query = campana.obtener_calificaciones().filter(
            contacto__bd_contacto=campana.bd_contacto).values(
            'opcion_calificacion__nombre', 'opcion_calificacion__id').annotate(
                Count('opcion_calificacion')).filter(opcion_calificacion__count__gt=0).order_by()

        calificaciones = []
        for calificacion in calificaciones_query:
            cantidad_contactacion = CantidadContactacion(
                calificacion['opcion_calificacion__id'],
                calificacion['opcion_calificacion__nombre'],
                calificacion['opcion_calificacion__count']
            )
            calificaciones.append(cantidad_contactacion)

        return calificaciones

    def obtener_cantidad_no_calificados(self, campana):
        # Cantidad de contactos no calificados, con o sin llamadas.
        return campana.bd_contacto.contactos.count() - CalificacionCliente.objects.filter(
            opcion_calificacion__campana_id=campana.id,
            contacto__bd_contacto_id=campana.bd_contacto_id).count()


class CantidadContactacion(object):

    def __init__(self, id, nombre, cantidad):
        self._id = id
        self._nombre = nombre
        self._cantidad = cantidad

    @property
    def id(self):
        return self._id

    @property
    def nombre(self):
        return self._nombre

    @property
    def cantidad(self):
        return self._cantidad

    @cantidad.setter
    def cantidad(self, cantidad):
        self._cantidad += cantidad
        return self._cantidad

    @property
    def label_checkbox(self):
        return self._nombre + "  " + str(self._cantidad)


class RecicladorContactosCampanaDIALER():
    """
    Este manager se encarga de obtener los contactos según los tipo de
    reciclado de campana de dialer que se realice.
    Únicamente reciclará contactos de la base de datos de contactos actual
    (si fue reciclada sobre la misma campaña no será la original)
    """

    def obtener_contactos_reciclados(self, campana, reciclado_calificacion,
                                     reciclado_no_contactacion):
        """
        Este método se encarga de iterar sobre los tipos de reciclado que
        se indiquen aplicar en el reciclado de campana. Según el tipo de
        reciclado se invoca al método adecuado para llevar a cabo la consulta
        correspondiente, y en caso de que sea mas de uno se sumarizan las
        mismas.
        """
        contactos_reciclados = set()
        if reciclado_calificacion:
            contactos_reciclados.update(self._obtener_contactos_calificados(
                campana, reciclado_calificacion))
        if reciclado_no_contactacion:
            contactos_reciclados.update(self._obtener_contactos_no_contactados(
                campana, reciclado_no_contactacion))
        return contactos_reciclados

    def _obtener_contactos_no_llamados(self, campana):
        ids_contactos_base = list(
            campana.bd_contacto.contactos.values_list('id', flat=True))
        if not ids_contactos_base:
            return []
        qs = _get_interactions_base_queryset(campana, ids_contactos_base)
        customer_ids_llamados = set(qs.values_list('customer_id', flat=True).distinct())
        queryset_no_llamados = campana.bd_contacto.contactos.exclude(
            id__in=customer_ids_llamados)
        return list(queryset_no_llamados)

    def _obtener_contactos_calificados(self, campana, reciclado_calificacion):
        """
            Este metodo se encarga obtener los contactos calificados por las
            calificaciones seleccionada
            Sólo contactos que pertenecen a la base de datos de contacto actual.
        """
        calificaciones_query = campana.obtener_calificaciones().filter(
            opcion_calificacion__in=reciclado_calificacion,
            contacto__bd_contacto=campana.bd_contacto).distinct()

        contactos = [calificacion.contacto for calificacion in calificaciones_query]
        return contactos

    def _obtener_contactos_no_contactados(self, campana, reciclado_no_contactacion):
        """
        Obtiene los contactos no contactados según los estados seleccionados.
        Usa InteractionsSummary (última interacción por contacto).
        """
        ids_contactos_base_actual = list(
            campana.bd_contacto.contactos.values_list('id', flat=True))
        id_contactos = set()
        filtrar_no_calificados = False
        eventos_ids = set()

        for evento_id in reciclado_no_contactacion:
            evento_id = int(evento_id)
            if evento_id == EstadisticasContactacion.AGENTE_NO_CALIFICO:
                filtrar_no_calificados = True
            else:
                eventos_ids.add(evento_id)

        ultimas = _fetch_ultimas_interacciones_por_contacto(
            campana, ids_contactos_base_actual)
        contactados = _get_contactados_ultima_interaccion(
            campana, ids_contactos_base_actual, ultimas=ultimas)

        if filtrar_no_calificados:
            id_calificados = set(CalificacionCliente.objects.filter(
                opcion_calificacion__campana_id=campana.id,
                contacto__bd_contacto=campana.bd_contacto
            ).values_list('contacto_id', flat=True))
            id_contactos |= (contactados - id_calificados)

        if eventos_ids:
            contactos_no_contactados = set(ids_contactos_base_actual) - contactados
            for row in ultimas:
                customer_id = row['customer_id']
                if customer_id not in contactos_no_contactados:
                    continue
                status = row.get('status')
                if (status or '').strip().upper() == 'EXIT_ANSWERED':
                    continue
                rec_id = _status_hangup_to_reciclado_id(status, row.get('hangup_cause'))
                if rec_id in eventos_ids:
                    id_contactos.add(customer_id)

        return campana.bd_contacto.contactos.filter(id__in=id_contactos)

    def reciclar(self, campana, reciclado_calificacion, reciclado_no_contactacion):

        # Obtener los contactos reciclados
        contactos_reciclados = self.obtener_contactos_reciclados(
            campana, reciclado_calificacion, reciclado_no_contactacion)

        # Si quiero reciclar una campana activa puede existir contactos que no fueron llamados
        if campana.estado == Campana.ESTADO_PAUSADA:
            contactos_no_llamados = self._obtener_contactos_no_llamados(campana)
            contactos_reciclados.update(contactos_no_llamados)

        # Creamos la instancia de BaseDatosContacto para el reciclado.
        bd_contacto_reciclada = campana.bd_contacto.copia_para_reciclar()
        bd_contacto_reciclada.genera_contactos(contactos_reciclados)
        bd_contacto_reciclada.define()
        return bd_contacto_reciclada


class RecicladorContactosCampanaPreview(RecicladorContactosCampanaDIALER):

    def retomar_contactacion(self, campana, reciclado_calificacion, reciclado_no_contactacion):
        contactos_reciclados = self.obtener_contactos_reciclados(
            campana, reciclado_calificacion, reciclado_no_contactacion)
        campana.establecer_valores_iniciales_agente_contacto(False, False, contactos_reciclados)
        campana.estado = Campana.ESTADO_ACTIVA
        campana.save()

    def _obtener_contactos_no_contactados(self, campana, reciclado_no_contactacion):
        """Campañas preview solo filtra contactos no Calificados (con o sin llamadas)"""
        calificados = CalificacionCliente.objects.filter(
            opcion_calificacion__campana_id=campana.id,
            contacto__bd_contacto_id=campana.bd_contacto_id).values_list('contacto_id', flat=True)
        return campana.bd_contacto.contactos.exclude(id__in=calificados)
