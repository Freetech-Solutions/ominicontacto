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
Servicio para generar reporte grafico de una campana
"""

from __future__ import unicode_literals

import os

import pygal

from collections import OrderedDict
from pygal.style import LightGreenStyle, DefaultStyle

from django.conf import settings

from django.utils.translation import gettext as _

from ominicontacto_app.models import (AgenteEnContacto, CalificacionCliente, Campana,
                                      AgenteProfile, HistoricalCalificacionCliente,
                                      HistoricalRespuestaFormularioGestion,
                                      RespuestaFormularioGestion)
from ominicontacto_app.services.dialer import get_dialer_service
from reportes_app.models import LlamadaLog, LlamadaResumen

from utiles_globales import adicionar_render_unicode

import logging as _logging

logger = _logging.getLogger(__name__)

NO_CONECTADO_DESCRIPCION = {
    'NOANSWER': _('Cliente no atiende'),
    'CANCEL': _('Se corta antes que atienda el cliente'),
    'BUSY': _('Ocupado'),
    'CHANUNAVAIL': _('Canales Saturados'),
    'OTHER': _('Motivo no especificado'),
    'FAIL': _('Fallo'),
    'AMD': _('AMD Detected'),
    'BLACKLIST': _('Blacklist'),
    'ABANDON': _('Abandonada por cliente'),
    'EXITWITHTIMEOUT': _('Expirada'),
    'CONGESTION': _('Canal congestionado'),
    'NONDIALPLAN': _('Problema de enrutamiento'),
    'ABANDONWEL': _('Abandonadas durante anuncio'),
}


class EstadisticasBaseCampana:

    def _obtener_modelo_constantes(self):
        """
        Retorna la clase de constantes a usar según el tipo de modelo.
        Si estamos usando LlamadaResumen, retorna LlamadaResumen, sino LlamadaLog.
        """
        if (hasattr(self, 'campana') and self.campana.es_dialer and 
            hasattr(settings, 'OML_DIALER_ENGINE') and 
            settings.OML_DIALER_ENGINE == 'omnidialer'):
            return LlamadaResumen
        return LlamadaLog

    def _obtener_logs_de_llamadas(self):
        # Si es dialer y OML_DIALER_ENGINE=omnidialer, usar LlamadaResumen
        if (self.campana.es_dialer and 
            hasattr(settings, 'OML_DIALER_ENGINE') and 
            settings.OML_DIALER_ENGINE == 'omnidialer'):
            # Usar la tabla de resumen para omnidialer
            resumenes = LlamadaResumen.objects.using('replica').filter(
                campana_id=self.campana.pk, 
                fecha_fin__range=(self.fecha_desde, self.fecha_hasta)
            ).order_by('-fecha_fin')
            # Convertir LlamadaResumen a objetos similares a LlamadaLog
            return self._convertir_resumenes_a_logs(resumenes)
        else:
            # Usar LlamadaLog para otros casos
            logs_llamadas = LlamadaLog.objects.using('replica').filter(
                campana_id=self.campana.pk, time__range=(self.fecha_desde, self.fecha_hasta)).order_by(
                    '-time')
            return logs_llamadas

    def _convertir_resumenes_a_logs(self, resumenes):
        """
        Convierte registros de LlamadaResumen en objetos similares a LlamadaLog
        para mantener compatibilidad con el código existente.
        """
        class LlamadaLogAdapter:
            """Adaptador que convierte LlamadaResumen a formato LlamadaLog"""
            def __init__(self, resumen):
                self.resumen = resumen
                # Mapear campos de LlamadaResumen a atributos de LlamadaLog
                self.time = resumen.fecha_fin or resumen.fecha_inicio
                self.callid = resumen.callid
                self.campana_id = resumen.campana_id
                self.tipo_campana = resumen.tipo_campana
                self.tipo_llamada = resumen.tipo_llamada
                self.agente_id = resumen.agente_id or -1
                self.event = resumen.event
                self.numero_marcado = resumen.numero_marcado
                self.contacto_id = resumen.contacto_id
                self.bridge_wait_time = float(resumen.bridge_wait_time) if resumen.bridge_wait_time else 0
                self.duracion_llamada = int(resumen.duracion_segundos) if resumen.duracion_segundos else 0
                self.archivo_grabacion = resumen.archivo_grabacion
                # Marcar que este es un adaptador de LlamadaResumen
                self._es_resumen = True
                
        return [LlamadaLogAdapter(resumen) for resumen in resumenes]

    def _inicializar_valores_estadisticas(self):
        self.calificaciones_finales_dict = {}

        self.calificaciones_historicas_dict = {}

        self.agentes_dict = {}

        # con el id de la calificacion asociada como clave
        self.respuestas_formulario_gestion_dict = {}

        self.bd_contacto = self.campana.bd_contacto
        self.opciones_calificacion_campana = {opcion.pk: opcion for opcion in
                                              self.campana.opciones_calificacion.all(
                                              ).select_related('formulario').prefetch_related(
                                                  'formulario__campos')}
        self.bd_metadata = self.bd_contacto.get_metadata()
        self._inicializar_valores_calificaciones()
        self._inicializar_respuestas_formulario_gestion()
        self._inicializar_valores_agentes()

    def _inicializar_valores_calificaciones(self):
        calificacion_finales_qs = CalificacionCliente.objects.using('replica').filter(
            opcion_calificacion__campana=self.campana, modified__range=(
                self.fecha_desde, self.fecha_hasta)).select_related(
                    'agente', 'agente__user', 'contacto', 'contacto__bd_contacto',
                    'opcion_calificacion')

        for calificacion in calificacion_finales_qs:
            self.calificaciones_finales_dict[calificacion.callid] = calificacion

        calificaciones_historicas_qs = HistoricalCalificacionCliente.objects.using('replica')\
            .filter(history_date__range=(self.fecha_desde, self.fecha_hasta),
                    opcion_calificacion__campana=self.campana).select_related(
                        'agente', 'agente__user', 'contacto', 'contacto__bd_contacto',
                        'opcion_calificacion').order_by()

        self.calificaciones_historicas_dict = {calificacion.callid: calificacion for calificacion
                                               in calificaciones_historicas_qs}
        self.calificaciones_historicas_por_history_id = {
            calificacion.history_id: calificacion for calificacion in calificaciones_historicas_qs}

    def _inicializar_respuestas_formulario_gestion(self):
        respuestas_formulario_gestion_qs = RespuestaFormularioGestion.objects.filter(
            calificacion__callid__in=self.calificaciones_finales_dict.keys()).select_related(
                'calificacion')
        for respuesta in respuestas_formulario_gestion_qs:
            self.respuestas_formulario_gestion_dict[respuesta.calificacion.pk] = respuesta

    def _inicializar_respuestas_formulario_gestion_historicas(self):
        respuestas_historicas = HistoricalRespuestaFormularioGestion.objects.filter(
            history_change_reason__in=self.calificaciones_historicas_por_history_id.keys())
        self.respuestas_historicas_por_calificacion = {
            int(respuesta.history_change_reason): respuesta for respuesta in respuestas_historicas}

    def _inicializar_valores_agentes(self):
        # se crean un diccionario de los agentes de la campaña
        # para evitar accesos a la BD para recuperarlos desde los logs
        agentes_campana = AgenteProfile.objects.obtener_agentes_campana(
            self.campana).select_related('user')
        for agente in agentes_campana:
            self.agentes_dict[agente.pk] = agente


class ReporteDetalleLlamadasPreview:
    """
    Devuelve los datos para tabla con el detalle de las llamadas recibidas para una
    campaña de tipo preview
    :param logs_llamadas_campana: queryset con los logs de las llamadas preview
    recibidas
    :return: dicionario con los totales de cada estado de las llamadas recibidas
    """

    def __init__(self):
        self.reporte = OrderedDict(
            # se cuentan todos los eventos DIAL  con 'tipo_llamada' no manual
            [(_('Discadas'), 0),
             # se cuentan todos los eventos ANSWER  con 'tipo_llamada' no manual
             (_('Conectadas'), 0),
             # se cuentan todos los eventos 'no-conexión' con 'tipo_llamada' no manual
             (_('No conectadas'), 0),
             # se cuentan todos los eventos DIAL con 'tipo_llamada' manual
             (_('Manuales'), 0),
             # se cuentan todos los eventos ANSWER con 'tipo_llamada' manual
             (_('Manuales atendidas'), 0),
             # se cuentan todos los eventos de 'no-conexión con 'tipo_llamada' manual
             (_('Manuales no atendidas'), 0)])

    def _calcular_detalle(self, evento=None, tipo_llamada=None, modelo_constantes=None):
        # Usar LlamadaResumen si se proporciona, sino LlamadaLog por defecto
        constantes = modelo_constantes if modelo_constantes else LlamadaLog
        if evento == 'ANSWER' and tipo_llamada != constantes.LLAMADA_MANUAL:
            self.reporte[_('Conectadas')] += 1
        elif evento == 'ANSWER' and tipo_llamada == constantes.LLAMADA_MANUAL:
            self.reporte[_('Manuales atendidas')] += 1
        elif ((evento in constantes.EVENTOS_NO_CONEXION) and
              tipo_llamada != constantes.LLAMADA_MANUAL):
            self.reporte[_('No conectadas')] += 1
        elif ((evento in constantes.EVENTOS_NO_CONEXION) and
              tipo_llamada == constantes.LLAMADA_MANUAL):
            self.reporte[_('Manuales no atendidas')] += 1
        elif evento == 'DIAL' and tipo_llamada == constantes.LLAMADA_MANUAL:
            self.reporte[_('Manuales')] += 1
        elif evento == 'DIAL' and tipo_llamada != constantes.LLAMADA_MANUAL:
            self.reporte[_('Discadas')] += 1


class ReporteDetalleLlamadasManual:
    """
    Devuelve los datos para tabla con el detalle de las llamadas recibidas para una
    campaña de tipo manual
    :param logs_llamadas_campana: queryset con los logs de las llamadas manual
    recibidas
    :return: dicionario con los totales de cada estado de las llamadas recibidas
    """

    def __init__(self):
        self.reporte = OrderedDict(
            # se cuentan todos los eventos DIAL
            [(_('Discadas'), 0),
             # se cuentan todos los eventos ANSWER
             (_('Discadas atendidas'), 0),
             # se cuentan todos los eventos de 'no-conexión'
             (_('Discadas no atendidas'), 0)])

    def _calcular_detalle(self, evento=None, tipo_llamada=None, modelo_constantes=None):
        # Usar LlamadaResumen si se proporciona, sino LlamadaLog por defecto
        constantes = modelo_constantes if modelo_constantes else LlamadaLog
        if evento == 'DIAL':
            self.reporte[_('Discadas')] += 1
        elif evento == 'ANSWER':
            self.reporte[_('Discadas atendidas')] += 1
        elif evento in constantes.EVENTOS_NO_CONEXION:
            self.reporte[_('Discadas no atendidas')] += 1


class ReporteDetalleLlamadasDialer:
    """
    Devuelve los datos para tabla con el detalle de las llamadas recibidas para una
    campaña de tipo dialer
    :param logs_llamadas_campana: queryset con los logs de las llamadas dialer
    recibidas
    :return: dicionario con los totales de cada estado de las llamadas recibidas
    """

    def __init__(self):
        self.reporte = OrderedDict(
            # se cuentan todos los eventos DIAL con 'tipo_llamada' no manual
            [(_('Discadas'), 0),
             # se cuentan todos los eventos ANSWER con 'tipo_llamada' no manual
             (_('Atendidas'), 0),
             # se cuentan todos los eventos CONNECT con 'tipo_llamada' no manual
             (_('Conectadas al agente'), 0),
             # se cuentan todos los eventos EXITWITHTIMEOUT y ABANDON con 'tipo_llamada' no manual
             (_('Perdidas'), 0),
             # se cuentan todos los eventos AMD
             (_('Contestador detectado'), 0),
             # se cuentan todos los eventos DIAL con 'tipo_llamada' manual
             (_('Manuales'), 0),
             # se cuentan todos los eventos ANSWER con 'tipo_llamada' manual
             (_('Manuales atendidas'), 0),
             # se cuentan todos los eventos de 'no-conexión con 'tipo_llamada' manual
             (_('Manuales no atendidas'), 0)])

    def _calcular_detalle(self, evento=None, tipo_llamada=None, modelo_constantes=None):
        # Usar LlamadaResumen si se proporciona, sino LlamadaLog por defecto
        constantes = modelo_constantes if modelo_constantes else LlamadaLog
        if evento == 'DIAL' and tipo_llamada != constantes.LLAMADA_MANUAL:
            self.reporte[_('Discadas')] += 1
        elif evento == 'DIAL' and tipo_llamada == constantes.LLAMADA_MANUAL:
            self.reporte[_('Manuales')] += 1
        elif evento == 'CONNECT' and tipo_llamada != constantes.LLAMADA_MANUAL:
            self.reporte[_('Conectadas al agente')] += 1
        elif evento == 'ANSWER' and tipo_llamada != constantes.LLAMADA_MANUAL:
            self.reporte[_('Atendidas')] += 1
        elif evento == 'ANSWER' and tipo_llamada == constantes.LLAMADA_MANUAL:
            self.reporte[_('Manuales atendidas')] += 1
        elif evento == 'AMD' or evento == 'EXIT_AMD':
            self.reporte[_('Contestador detectado')] += 1
        elif (evento in ['ABANDON', 'EXITWITHTIMEOUT'] and
              tipo_llamada != constantes.LLAMADA_MANUAL):
            self.reporte[_('Perdidas')] += 1
        elif ((evento in constantes.EVENTOS_NO_CONEXION) and
              tipo_llamada == constantes.LLAMADA_MANUAL):
            self.reporte[_('Manuales no atendidas')] += 1


class ReporteDetalleLlamadasEntrantes:
    """
    Devuelve los datos para tabla con el detalle de las llamadas recibidas para una
    campaña de tipo entrante
    :param logs_llamadas_campana: queryset con los logs de las llamadas entrantes
    recibidas
    :return: dicionario con los totales de cada estado de las llamadas recibidas
    """

    def __init__(self):
        # se cuentan todos los eventos para cada caso
        self.reporte = OrderedDict(
            [(_('Recibidas'), 0),
             (_('Atendidas'), 0),
             (_('Expiradas'), 0),
             (_('Abandonadas'), 0),
             (_('Abandonadas durante anuncio'), 0),
             (_('Manuales'), 0),
             (_('Manuales atendidas'), 0),
             (_('Manuales no atendidas'), 0)])

        self.eventos_headers = {
            'ENTERQUEUE': _('Recibidas'),
            'ENTERQUEUE-TRANSFER': _('Recibidas'),
            'CONNECT': _('Atendidas'),
            'EXITWITHTIMEOUT': _('Expiradas'),
            'ABANDON': _('Abandonadas'),
            'ABANDONWEL': _('Abandonadas durante anuncio'),
            'DIAL': _('Manuales'),
            'ANSWER': _('Manuales atendidas')}

    def _calcular_detalle(self, evento=None, tipo_llamada=None, modelo_constantes=None):
        # Usar LlamadaResumen si se proporciona, sino LlamadaLog por defecto
        constantes = modelo_constantes if modelo_constantes else LlamadaLog
        evento_header = self.eventos_headers.get(evento, False)
        if evento_header:
            self.reporte[evento_header] += 1
        elif not evento_header and (evento in constantes.EVENTOS_NO_CONEXION):
            self.reporte[_('Manuales no atendidas')] += 1
        if evento == 'ABANDONWEL':
            self.reporte[_('Recibidas')] += 1


class ReporteNoAtendidos:
    def __init__(self):
        self.reporte = OrderedDict(
            # se cuentan todos los eventos NOANSWER
            [(_('Cliente no atiende'), 0),
             # se cuentan todos los eventos CANCEL
             (_('Cancelado'), 0),
             # se cuentan todos los eventos AMD
             (_('Contestador detectado'), 0),
             # se cuentan todos los eventos BUSY
             (_('Ocupado'), 0),
             # se cuentan todos los evento CHANUNAVAIL
             (_('Canales No disponibles'), 0),
             # se cuentan todos los eventos FAIL
             (_('Fallidas'), 0),
             # se cuentan todos los eventos OTHER
             (_('Otro'), 0),
             # se cuentan todos los eventos BLACKLIST
             (_('Blacklist'), 0),
             # se cuentan todos los eventos ABANDON
             (_('Abandonadas por el cliente'), 0),
             # se cuentan todos los eventos ABANDONWEL
             (_('Abandonadas durante anuncio'), 0),
             # se cuentan todos los eventos EXITWITHTIMEOUT
             (_('Expiradas'), 0),
             # se cuentan todos los eventos CONGESTION
             (_('Canal congestionado'), 0),
             # se cuentan todos los eventos NONDIALPLAN
             (_('Problema de enrutamiento'), 0)]
        )
        # LlamadaLog.EVENTOS_NO_CONEXION
        self.eventos_headers = {
            'NOANSWER': _('Cliente no atiende'),
            'CANCEL': _('Cancelado'),
            'AMD': _('AMD Detected'),
            'EXIT_AMD': _('AMD Detected'),
            'BUSY': _('Ocupado'),
            'CHANUNAVAIL': _('Canales No disponibles'),
            'FAIL': _('Fallidas'),
            'OTHER': _('Otro'),
            'BLACKLIST': _('Blacklist'),
            'ABANDON': _('Abandonadas por el cliente'),
            'ABANDONWEL': _('Abandonadas durante anuncio'),
            'EXITWITHTIMEOUT': _('Expiradas'),
            'CONGESTION': _('Canal congestionado'),
            'NONDIALPLAN': _('Problema de enrutamiento'),
        }

        self.total_no_atendidos = 0


class ReporteTotalesCalificacionesAgentes:
    total_calificados = 0
    total_ventas = 0

    def __init__(self, opciones_calificaciones):
        self.dict_calificaciones = OrderedDict({})
        self.dict_agentes = {}
        for opcion_calificacion in opciones_calificaciones.values():
            self.dict_calificaciones[opcion_calificacion.nombre] = 0


class ReporteTotalesCalificaciones:

    dict_calificaciones = OrderedDict({})

    def __init__(self, dict_calificaciones):
        self.dict_calificaciones_atendidas = dict_calificaciones.copy()
        self.dict_calificaciones_no_atendidas = dict_calificaciones.copy()


class ReporteTotalesLlamadas:

    _llamadas_pendientes = 0
    llamadas_realizadas = 0
    _llamadas_recibidas = 0
    _llamadas_conectadas = 0
    _tiempo_acumulado_espera = 0
    _llamadas_abandonadas = 0
    _tiempo_acumulado_abandono = 0

    def __init__(self, campana):
        self.campana = campana

    @property
    def llamadas_recibidas(self):
        if not self.campana.es_entrante:
            return None
        return self._llamadas_recibidas

    @property
    def llamadas_pendientes(self):
        if not self.campana.es_preview:
            llamadas_pendientes_extra = 0
        else:
            llamadas_pendientes_extra = AgenteEnContacto.objects.filter(
                estado=AgenteEnContacto.ESTADO_INICIAL, campana_id=self.campana.pk,
                es_originario=True).count()
        if self.campana.es_dialer:
            dialer_service = get_dialer_service()
            llamadas_pendientes_extra = dialer_service.obtener_llamadas_pendientes(self.campana)
        return self._llamadas_pendientes + llamadas_pendientes_extra

    @property
    def tiempo_promedio_espera(self):
        if not self.campana.es_entrante:
            return None
        if self._llamadas_conectadas == 0:
            return 0
        return self._tiempo_acumulado_espera / self._llamadas_conectadas

    @property
    def tiempo_promedio_abandono(self):
        if not self.campana.es_entrante:
            return None
        if self._llamadas_abandonadas == 0:
            return 0
        return self._tiempo_acumulado_abandono / self._llamadas_abandonadas


class EstadisticasService(EstadisticasBaseCampana):

    def __init__(self, campana, fecha_desde, fecha_hasta):
        self.campana = campana
        self.bd_contacto = campana.bd_contacto
        self.fecha_desde = fecha_desde
        self.fecha_hasta = fecha_hasta

        self.tipo_campana = campana.type

        self._inicializar_valores_estadisticas()
        
        # Determinar qué modelo usar para las constantes
        self._modelo_constantes = self._obtener_modelo_constantes()

        # valores del reporte

        self.reporte_no_atendidos = ReporteNoAtendidos()
        self.reporte_calificaciones_agentes = ReporteTotalesCalificacionesAgentes(
            self.opciones_calificacion_campana)
        self.reporte_calificaciones = ReporteTotalesCalificaciones(
            self.reporte_calificaciones_agentes.dict_calificaciones)
        self.reporte_totales_llamadas = ReporteTotalesLlamadas(self.campana)
        self.llamadas_atendidas_sin_calificacion = 0

        if self.campana.es_dialer:
            self.reporte_detalle_llamadas = ReporteDetalleLlamadasDialer()
        elif self.campana.es_entrante:
            self.reporte_detalle_llamadas = ReporteDetalleLlamadasEntrantes()
        elif self.campana._es_manual:
            self.reporte_detalle_llamadas = ReporteDetalleLlamadasManual()
        else:
            # self.campana.es_preview
            self.reporte_detalle_llamadas = ReporteDetalleLlamadasPreview()

    def _obtener_llamadas_atendidas_sin_calificacion(
            self, evento, agente_id, calificacion_final, calificacion_historica):
        # obtener_llamadas_atendidas_sin_calificacion(log_llamada)
        if not calificacion_final and not calificacion_historica:
            # Si es dialer, una misma llamada tiene ANSWER y CONNECT por lo que estaba
            # contabilizando doble
            if evento in self._modelo_constantes.EVENTOS_INICIO_CONEXION_AGENTE and agente_id != -1:
                # TODO: analizar consecuencias de que los eventos obtenidos
                # cada llamada son los ultimos de cada llamada
                # TODO: ver que pasaría con 'BT-ANSWER', 'CT-ACCEPT'
                self.llamadas_atendidas_sin_calificacion += 1

    def _obtener_total_llamadas(
            self, evento, es_campana_entrante, calificacion_final, callid,
            callids_analizados, bridge_wait_time):
        if calificacion_final and calificacion_final.opcion_calificacion.es_agenda() and \
           callid not in callids_analizados:
            self.reporte_totales_llamadas._llamadas_pendientes += 1
        if evento == 'DIAL':
            self.reporte_totales_llamadas.llamadas_realizadas += 1
        if es_campana_entrante:
            if evento in ['ENTERQUEUE', 'ABANDONWEL', 'ENTERQUEUE-TRANSFER']:
                self.reporte_totales_llamadas._llamadas_recibidas += 1
                if evento == 'ABANDONWEL':
                    self.reporte_totales_llamadas._llamadas_abandonadas += 1
                    self.reporte_totales_llamadas._tiempo_acumulado_abandono += bridge_wait_time
            elif evento == 'ABANDON':
                self.reporte_totales_llamadas._llamadas_abandonadas += 1
                self.reporte_totales_llamadas._tiempo_acumulado_abandono += bridge_wait_time
            elif evento == 'CONNECT':
                self.reporte_totales_llamadas._llamadas_conectadas += 1
                self.reporte_totales_llamadas._tiempo_acumulado_espera += bridge_wait_time

    def _obtener_reporte_no_atendidos(self, log_llamada, evento):
        # obtener_cantidad_no_atendidos(log_llamada) + datos_csv
        if evento in self.reporte_no_atendidos.eventos_headers.keys():
            evento_header = self.reporte_no_atendidos.eventos_headers[evento]
            self.reporte_no_atendidos.reporte[evento_header] += 1
            self.reporte_no_atendidos.total_no_atendidos += 1

    def _obtener_cantidad_calificacion(
            self, es_campana_entrante, calificacion_historica, calificacion_final,
            tipo_llamada, evento):
        if es_campana_entrante and calificacion_historica:
            nombre_opcion = calificacion_historica.opcion_calificacion.nombre
            # agrupamos las calificaciones finales que hayan sido conectadas con el agente
            if (evento == 'ANSWER' and tipo_llamada == self._modelo_constantes.LLAMADA_MANUAL) or \
               evento == 'CONNECT':
                # atendidas en campaña entrante
                self.reporte_calificaciones.dict_calificaciones_atendidas[nombre_opcion] += 1
            elif evento in self._modelo_constantes.EVENTOS_NO_CONEXION:   # TODO: que busque en set fijo
                # no atendidas en campaña entrante
                self.reporte_calificaciones.dict_calificaciones_no_atendidas[nombre_opcion] += 1
        elif calificacion_final:
            nombre_opcion = calificacion_final.opcion_calificacion.nombre
            if (evento == 'CONNECT' or
                (evento == 'ANSWER' and tipo_llamada == self._modelo_constantes.LLAMADA_MANUAL
                 and self.campana.es_dialer) or
                    (evento == 'ANSWER' and (self.campana._es_manual
                                             or self.campana.es_preview))):
                # atendidas en campaña no entrante
                self.reporte_calificaciones.dict_calificaciones_atendidas[nombre_opcion] += 1
            elif evento in self._modelo_constantes.EVENTOS_NO_CONEXION:  # TODO: que busque en set fijo
                # no atendidas en campaña no entrante
                self.reporte_calificaciones.dict_calificaciones_no_atendidas[nombre_opcion] += 1

    def _obtener_total_calificacion_agente_datos_calificaciones(
            self, es_campana_entrante, calificacion_historica, calificacion_final, log_llamada,
            calificaciones_analizadas):
        if es_campana_entrante:
            calificacion = calificacion_historica
        else:
            calificacion = calificacion_final
        if calificacion and (calificacion.pk not in calificaciones_analizadas):
            opcion_calificacion = calificacion.opcion_calificacion
            es_gestion = int(opcion_calificacion.es_gestion())
            self.reporte_calificaciones_agentes.total_calificados += 1
            if es_gestion:
                self.reporte_calificaciones_agentes.total_ventas += 1
            agente = calificacion.agente
            agente_id = agente.pk
            if not self.reporte_calificaciones_agentes.dict_agentes.get(agente_id, False):
                dict_calificaciones = self.reporte_calificaciones_agentes.dict_calificaciones
                self.reporte_calificaciones_agentes.dict_agentes[agente_id] = OrderedDict({
                    'nombre': agente.user.get_full_name(),
                    'totales_calificaciones': dict_calificaciones.copy(),
                    'total_calificados': 1,
                    'total_gestionados': es_gestion,
                })
            else:
                self.reporte_calificaciones_agentes.dict_agentes[
                    agente_id]['total_calificados'] += 1
                self.reporte_calificaciones_agentes.dict_agentes[
                    agente_id]['total_gestionados'] += es_gestion
            self.reporte_calificaciones_agentes.dict_agentes[
                agente_id]['totales_calificaciones'][
                    opcion_calificacion.nombre] += 1
            calificaciones_analizadas.add(calificacion.pk)

    def _es_llamada_resumen(self):
        """Verifica si estamos usando LlamadaResumen en lugar de LlamadaLog"""
        return (self.campana.es_dialer and 
                hasattr(settings, 'OML_DIALER_ENGINE') and 
                settings.OML_DIALER_ENGINE == 'omnidialer')

    def _mapear_evento_resumen_a_eventos_log(self, evento, agente_id):
        """
        Mapea el evento final de LlamadaResumen a los eventos que espera el código
        basado en LlamadaLog. Retorna una lista de eventos simulados.
        NOTA: Para evitar conteo duplicado, cuando hay agente_id y EXIT_ANSWERED,
        solo simulamos ANSWER (no CONNECT), ya que "Conectadas al agente" se calcula
        directamente desde LlamadaResumen.
        """
        eventos_simulados = []
        
        # Siempre simulamos un DIAL para contar como llamada realizada
        eventos_simulados.append('DIAL')
        
        # Mapear eventos finales de LlamadaResumen a eventos de LlamadaLog
        if evento == 'EXIT_ANSWERED':
            # Fue atendida, simulamos solo ANSWER (no CONNECT para evitar duplicado)
            # "Conectadas al agente" se calcula directamente desde LlamadaResumen
            eventos_simulados.append('ANSWER')
        elif evento == 'EXIT_TIMEOUT':
            eventos_simulados.append('EXITWITHTIMEOUT')
        elif evento == 'EXIT_ABANDON':
            eventos_simulados.append('ABANDON')
        elif evento == 'EXIT_AMD':
            # Mapear EXIT_AMD a AMD para compatibilidad
            eventos_simulados.append('AMD')
        elif evento in self._modelo_constantes.EVENTOS_NO_CONEXION:
            # Eventos tradicionales de no conexión
            eventos_simulados.append(evento)
        elif evento and evento.startswith('EXIT_'):
            # Otros eventos EXIT_* se tratan como no conexión
            eventos_simulados.append('OTHER')
        else:
            # Si no hay evento claro, asumimos no conexión
            eventos_simulados.append('OTHER')
        
        return eventos_simulados
    
    def _calcular_detalle_llamadas_desde_resumen(self):
        """
        Calcula el detalle de llamadas directamente desde LlamadaResumen
        cuando OML_DIALER_ENGINE=omnidialer, evitando conteos duplicados.
        """
        if not self._es_llamada_resumen():
            return
        
        # Consultar LlamadaResumen para calcular estadísticas directamente
        resumenes = LlamadaResumen.objects.using('replica').filter(
            campana_id=self.campana.pk,
            fecha_fin__range=(self.fecha_desde, self.fecha_hasta)
        )
        
        callids_procesados = set()
        
        for resumen in resumenes:
            callid = resumen.callid
            evento = resumen.event
            tipo_llamada = resumen.tipo_llamada or self._modelo_constantes.LLAMADA_DIALER
            agente_id = resumen.agente_id
            
            # Evitar procesar el mismo callid múltiples veces
            if callid in callids_procesados:
                continue
            callids_procesados.add(callid)
            
            # Contar como discada (siempre hay un DIAL implícito)
            if tipo_llamada != self._modelo_constantes.LLAMADA_MANUAL:
                self.reporte_detalle_llamadas.reporte[_('Discadas')] += 1
            else:
                self.reporte_detalle_llamadas.reporte[_('Manuales')] += 1
            
            # Procesar según el evento final
            if evento == 'EXIT_ANSWERED':
                if tipo_llamada != self._modelo_constantes.LLAMADA_MANUAL:
                    # Atendida (cliente contestó)
                    self.reporte_detalle_llamadas.reporte[_('Atendidas')] += 1
                    # Conectada al agente (si tiene agente_id)
                    if agente_id and agente_id != -1:
                        self.reporte_detalle_llamadas.reporte[_('Conectadas al agente')] += 1
                else:
                    self.reporte_detalle_llamadas.reporte[_('Manuales atendidas')] += 1
            elif evento == 'EXIT_TIMEOUT':
                if tipo_llamada != self._modelo_constantes.LLAMADA_MANUAL:
                    self.reporte_detalle_llamadas.reporte[_('Perdidas')] += 1
                else:
                    self.reporte_detalle_llamadas.reporte[_('Manuales no atendidas')] += 1
            elif evento == 'EXIT_ABANDON':
                if tipo_llamada != self._modelo_constantes.LLAMADA_MANUAL:
                    self.reporte_detalle_llamadas.reporte[_('Perdidas')] += 1
                else:
                    self.reporte_detalle_llamadas.reporte[_('Manuales no atendidas')] += 1
            elif evento == 'AMD' or evento == 'EXIT_AMD':
                self.reporte_detalle_llamadas.reporte[_('Contestador detectado')] += 1
            elif evento in self._modelo_constantes.EVENTOS_NO_CONEXION:
                if tipo_llamada != self._modelo_constantes.LLAMADA_MANUAL:
                    # Ya se contó como discada, no se cuenta como no atendida aquí
                    pass
                else:
                    self.reporte_detalle_llamadas.reporte[_('Manuales no atendidas')] += 1

    def calcular_estadisticas_totales(self):
        calificaciones_analizadas = set()
        callids_analizados = set()
        usar_resumen = self._es_llamada_resumen()
        
        # Si usamos LlamadaResumen, calcular detalle directamente para evitar duplicados
        if usar_resumen and self.campana.es_dialer:
            self._calcular_detalle_llamadas_desde_resumen()
        
        logs_llamadas = self._obtener_logs_de_llamadas()
        
        for log_llamada in logs_llamadas:
            evento = log_llamada.event
            callid = log_llamada.callid
            agente_id = log_llamada.agente_id
            tipo_llamada = log_llamada.tipo_llamada
            bridge_wait_time = log_llamada.bridge_wait_time
            es_campana_entrante = self.campana.es_entrante
            calificacion_historica = self.calificaciones_historicas_dict.get(callid, False)
            calificacion_final = self.calificaciones_finales_dict.get(callid, False)
            
            # Si usamos LlamadaResumen, el detalle ya se calculó, solo procesamos otros aspectos
            if usar_resumen:
                # Para LlamadaResumen, solo simulamos eventos necesarios para otras estadísticas
                # pero NO para el detalle de llamadas (ya calculado)
                eventos_procesar = self._mapear_evento_resumen_a_eventos_log(evento, agente_id)
                # Procesar cada evento simulado (excepto detalle de llamadas)
                for evento_simulado in eventos_procesar:
                    self._obtener_llamadas_atendidas_sin_calificacion(
                        evento_simulado, agente_id, calificacion_final, calificacion_historica)
                    # NO llamar a _calcular_detalle aquí, ya se calculó desde resumen
                    self._obtener_reporte_no_atendidos(log_llamada, evento_simulado)
                    self._obtener_total_llamadas(
                        evento_simulado, es_campana_entrante, calificacion_final, callid, 
                        callids_analizados, bridge_wait_time)
                    self._obtener_cantidad_calificacion(
                        es_campana_entrante, calificacion_historica, calificacion_final, 
                        tipo_llamada, evento_simulado)
            else:
                # Procesamiento normal con LlamadaLog
                self._obtener_llamadas_atendidas_sin_calificacion(
                    evento, agente_id, calificacion_final, calificacion_historica)
                self.reporte_detalle_llamadas._calcular_detalle(evento, tipo_llamada, self._modelo_constantes)
                self._obtener_reporte_no_atendidos(log_llamada, evento)
                self._obtener_total_llamadas(
                    evento, es_campana_entrante, calificacion_final, callid, callids_analizados,
                    bridge_wait_time)
                self._obtener_cantidad_calificacion(
                    es_campana_entrante, calificacion_historica, calificacion_final, tipo_llamada,
                    evento)
            
            # obtener_total_calificacion_agente(log_llamada) y reporte csv_calificados
            self._obtener_total_calificacion_agente_datos_calificaciones(
                es_campana_entrante, calificacion_historica, calificacion_final, log_llamada,
                calificaciones_analizadas)
            callids_analizados.add(callid)

    def _crear_serie_con_color(self, campana, cantidad_llamadas):
        """ crea la lista del diccionario con los colores de la serie"""

        serie = []

        if campana.type == Campana.TYPE_ENTRANTE:
            serie = [
                {'value': cantidad_llamadas[1][0], 'color': 'yellow'},
                {'value': cantidad_llamadas[1][1], 'color': 'green'},
                {'value': cantidad_llamadas[1][2], 'color': 'green'},
                {'value': cantidad_llamadas[1][3], 'color': 'red'},
                {'value': cantidad_llamadas[1][4], 'color': 'red'},
                {'value': cantidad_llamadas[1][5], 'color': 'yellow'},
                {'value': cantidad_llamadas[1][6], 'color': 'green'},
            ]
        elif campana.type == Campana.TYPE_DIALER:
            serie = [
                {'value': cantidad_llamadas[1][0], 'color': 'yellow'},
                {'value': cantidad_llamadas[1][1], 'color': 'green'},
                {'value': cantidad_llamadas[1][2], 'color': 'green'},
                {'value': cantidad_llamadas[1][3], 'color': 'red'},
                {'value': cantidad_llamadas[1][4], 'color': 'yellow'},
                {'value': cantidad_llamadas[1][5], 'color': 'green'},
                {'value': cantidad_llamadas[1][6], 'color': 'red'},
            ]
        elif campana.type == Campana.TYPE_MANUAL:
            serie = [
                {'value': cantidad_llamadas[1][0], 'color': 'yellow'},
                {'value': cantidad_llamadas[1][1], 'color': 'green'},
                {'value': cantidad_llamadas[1][2], 'color': 'red'},
            ]
        else:
            serie = [
                {'value': cantidad_llamadas[1][0], 'color': 'yellow'},
                {'value': cantidad_llamadas[1][1], 'color': 'green'},
                {'value': cantidad_llamadas[1][2], 'color': 'red'},
                {'value': cantidad_llamadas[1][3], 'color': 'yellow'},
                {'value': cantidad_llamadas[1][4], 'color': 'green'},
                {'value': cantidad_llamadas[1][5], 'color': 'red'},

            ]
        return serie

    def _calcular_estadisticas_llamadas_por_agente_omnidialer(self):
        """
        Calcula las estadísticas de llamadas ofrecidas, atendidas y no atendidas
        por agente desde la tabla LlamadaResumen.
        Solo se usa cuando OML_DIALER_ENGINE=omnidialer
        """
        if not self._es_llamada_resumen():
            return None
        
        from django.db.models import Count, Q, Case, When, IntegerField
        
        # Consultar LlamadaResumen agrupando por agente_id usando agregación
        resumenes_por_agente = LlamadaResumen.objects.using('replica').filter(
            campana_id=self.campana.pk,
            fecha_fin__range=(self.fecha_desde, self.fecha_hasta),
            agente_id__isnull=False
        ).exclude(agente_id=-1).values('agente_id', 'event').annotate(
            cantidad=Count('callid')
        )
        
        # Agrupar por agente y contar
        estadisticas_por_agente = {}
        
        for item in resumenes_por_agente:
            agente_id = item['agente_id']
            evento = item['event']
            cantidad = item['cantidad']
            
            if agente_id not in estadisticas_por_agente:
                # Obtener el agente del diccionario o de la BD
                if agente_id in self.agentes_dict:
                    agente = self.agentes_dict[agente_id]
                else:
                    try:
                        agente = AgenteProfile.objects.get(pk=agente_id)
                        self.agentes_dict[agente_id] = agente
                    except AgenteProfile.DoesNotExist:
                        continue
                
                estadisticas_por_agente[agente_id] = {
                    'agente_id': agente_id,
                    'nombre': agente.user.get_full_name() or agente.user.username,
                    'ofrecidas': 0,
                    'atendidas': 0,
                    'no_atendidas': 0,
                }
            
            # Contar como ofrecida (tiene agente_id)
            estadisticas_por_agente[agente_id]['ofrecidas'] += cantidad
            
            # Determinar si fue atendida o no atendida
            if evento == 'EXIT_ANSWERED':
                estadisticas_por_agente[agente_id]['atendidas'] += cantidad
            else:
                # No atendida: cualquier otro evento cuando hay agente_id
                estadisticas_por_agente[agente_id]['no_atendidas'] += cantidad
        
        return estadisticas_por_agente

    def _calcular_estadisticas(self, campana, fecha_desde, fecha_hasta):

        self.calcular_estadisticas_totales()

        # obtener cantidad de calificaciones por campana
        reporte_atendidas_dict = self.reporte_calificaciones.dict_calificaciones_atendidas
        header_no_calificadas = _('Llamadas Atendidas sin calificación')
        reporte_atendidas_dict[header_no_calificadas] = self.llamadas_atendidas_sin_calificacion
        calificaciones_nombre = reporte_atendidas_dict.keys()
        calificaciones_cantidad = reporte_atendidas_dict.values()
        total_asignados = sum(reporte_atendidas_dict.values())
        # obtiene detalle de llamados no atendidos
        resultado_nombre = self.reporte_no_atendidos.reporte.keys()
        resultado_cantidad = self.reporte_no_atendidos.reporte.values()
        total_no_atendidos = self.reporte_no_atendidos.total_no_atendidos

        # obtiene el total de calificaciones por agente
        agentes_venta = self.reporte_calificaciones_agentes.dict_agentes
        total_calificados = self.reporte_calificaciones_agentes.total_calificados
        total_ventas = self.reporte_calificaciones_agentes.total_ventas
        calificaciones = tuple(self.reporte_calificaciones_agentes.dict_calificaciones.keys())

        # obtiene las llamadas pendientes y realizadas por campana
        llamadas_pendientes = self.reporte_totales_llamadas.llamadas_pendientes
        llamadas_realizadas = self.reporte_totales_llamadas.llamadas_realizadas
        llamadas_recibidas = self.reporte_totales_llamadas.llamadas_recibidas
        tiempo_promedio_espera = self.reporte_totales_llamadas.tiempo_promedio_espera
        tiempo_promedio_abandono = self.reporte_totales_llamadas.tiempo_promedio_abandono

        # obtiene las cantidades totales por evento de las llamadas
        reporte = self.reporte_detalle_llamadas.reporte
        cantidad_llamadas = (list(reporte.keys()), list(reporte.values()))

        # Calcular estadísticas de llamadas por agente (solo para omnidialer)
        estadisticas_llamadas_por_agente = self._calcular_estadisticas_llamadas_por_agente_omnidialer()
        
        # Calcular totales de llamadas por agente
        total_ofrecidas = 0
        total_atendidas = 0
        total_no_atendidas = 0
        if estadisticas_llamadas_por_agente:
            for estadisticas in estadisticas_llamadas_por_agente.values():
                total_ofrecidas += estadisticas['ofrecidas']
                total_atendidas += estadisticas['atendidas']
                total_no_atendidas += estadisticas['no_atendidas']

        dic_estadisticas = {
            'agentes_venta': agentes_venta,
            'total_asignados': total_asignados,
            'total_ventas': total_ventas,
            'calificaciones_nombre': calificaciones_nombre,
            'calificaciones_cantidad': calificaciones_cantidad,
            'total_calificados': total_calificados,
            'resultado_nombre': resultado_nombre,
            'resultado_cantidad': resultado_cantidad,
            'total_no_atendidos': total_no_atendidos,
            'llamadas_pendientes': llamadas_pendientes,
            'llamadas_realizadas': llamadas_realizadas,
            'llamadas_recibidas': llamadas_recibidas,
            'tiempo_promedio_espera': tiempo_promedio_espera,
            'tiempo_promedio_abandono': tiempo_promedio_abandono,
            'calificaciones': calificaciones,
            'cantidad_llamadas': cantidad_llamadas,
            'estadisticas_llamadas_por_agente': estadisticas_llamadas_por_agente,
            'total_llamadas_ofrecidas': total_ofrecidas,
            'total_llamadas_atendidas': total_atendidas,
            'total_llamadas_no_atendidas': total_no_atendidas,
        }
        return dic_estadisticas

    def general_campana(self):
        estadisticas = self._calcular_estadisticas(self.campana, self.fecha_desde, self.fecha_hasta)
        if estadisticas:
            logger.info(_("Generando grafico calificaciones de campana por cliente "))

        reporte_campana_dir = os.path.join(settings.MEDIA_ROOT, "reporte_campana")
        try:
            os.stat(reporte_campana_dir)
        except IOError:
            os.mkdir(reporte_campana_dir)

        # Barra: Cantidad de calificacion de cliente
        barra_campana_calificacion = pygal.Bar(  # @UndefinedVariable
            show_legend=False, style=LightGreenStyle, width=1000, height=400)
        barra_campana_calificacion.title = _('Calificaciones de Clientes Contactados ')

        barra_campana_calificacion.x_labels = \
            estadisticas['calificaciones_nombre']
        barra_campana_calificacion.add('cantidad',
                                       estadisticas['calificaciones_cantidad'])
        barra_campana_calificacion.render_to_png(
            os.path.join(reporte_campana_dir, "barra_campana_calificacion_{}.png"
                                              .format(self.campana.id)))

        barra_campana_calificacion = adicionar_render_unicode(barra_campana_calificacion)

        # Barra: Total de llamados no atendidos en cada intento por campana.
        barra_campana_no_atendido = pygal.Bar(  # @UndefinedVariable
            show_legend=False,
            style=DefaultStyle(colors=('#b93229',)), width=1000, height=400)
        barra_campana_no_atendido.title = _('Cantidad de llamadas no atendidos ')

        barra_campana_no_atendido.x_labels = \
            estadisticas['resultado_nombre']
        barra_campana_no_atendido.add('cantidad',
                                      estadisticas['resultado_cantidad'])
        barra_campana_no_atendido.render_to_png(
            os.path.join(reporte_campana_dir, "barra_campana_no_atendido_{}.png"
                                              .format(self.campana.id)))

        barra_campana_no_atendido = adicionar_render_unicode(barra_campana_no_atendido)

        # Barra: Detalles de llamadas por evento de llamada.
        barra_campana_llamadas = pygal.Bar(show_legend=False, width=1000, height=400)
        barra_campana_llamadas.title = _('Detalles de llamadas ')

        barra_campana_llamadas.x_labels = \
            estadisticas['cantidad_llamadas'][0]
        barra_campana_llamadas.add('cantidad', self._crear_serie_con_color(
            self.campana, estadisticas['cantidad_llamadas']))
        barra_campana_llamadas = adicionar_render_unicode(barra_campana_llamadas)

        return {
            'estadisticas': estadisticas,
            'barra_campana_calificacion': barra_campana_calificacion,
            'dict_campana_counter': list(zip(estadisticas['calificaciones_nombre'],
                                             estadisticas['calificaciones_cantidad'])),
            'total_asignados': estadisticas['total_asignados'],
            'agentes_venta': estadisticas['agentes_venta'],
            'total_calificados': estadisticas['total_calificados'],
            'total_ventas': estadisticas['total_ventas'],
            'barra_campana_no_atendido': barra_campana_no_atendido,
            'dict_no_atendido_counter': list(zip(estadisticas['resultado_nombre'],
                                                 estadisticas['resultado_cantidad'])),
            'total_no_atendidos': estadisticas['total_no_atendidos'],
            'calificaciones': estadisticas['calificaciones'],
            'barra_campana_llamadas': barra_campana_llamadas,
            'dict_llamadas_counter': list(zip(estadisticas['cantidad_llamadas'][0],
                                              estadisticas['cantidad_llamadas'][1])),
            'estadisticas_llamadas_por_agente': estadisticas.get('estadisticas_llamadas_por_agente'),
            'total_llamadas_ofrecidas': estadisticas.get('total_llamadas_ofrecidas', 0),
            'total_llamadas_atendidas': estadisticas.get('total_llamadas_atendidas', 0),
            'total_llamadas_no_atendidas': estadisticas.get('total_llamadas_no_atendidas', 0),
        }
