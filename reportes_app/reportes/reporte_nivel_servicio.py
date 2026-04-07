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
Reporte de Nivel de Servicio (Service Level)
Calcula KPIs basados en el tiempo de espera en cola y porcentaje de llamadas contestadas
"""
from collections import defaultdict
from decimal import Decimal
from django.db.models import Count, Q, Sum, Avg
from django.utils.encoding import force_str

from reportes_app.models import LlamadaResumen, ActividadAgenteLog
from ominicontacto_app.utiles import datetime_hora_maxima_dia, datetime_hora_minima_dia
from ominicontacto_app.models import Campana
from django.utils import timezone

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


class ReporteNivelServicio(object):
    """
    Reporte que calcula el Nivel de Servicio (Service Level) basado en:
    - Porcentaje de llamadas contestadas dentro de un tiempo objetivo
    - Tiempo promedio de espera en cola
    - Distribución de llamadas por rangos de tiempo de espera
    """
    
    # Tiempo objetivo por defecto (20 segundos para 80/20)
    TIEMPO_OBJETIVO_DEFAULT = 20
    
    # Eventos que indican que la llamada fue contestada
    # Para entrantes: CONNECT, ANSWER
    # Para dialer (omnidialer): EXIT_ANSWERED
    EVENTOS_CONTESTADAS = ['CONNECT', 'ANSWER', 'EXIT_ANSWERED']
    
    # Eventos que indican que la llamada no fue contestada
    # Para entrantes: ABANDON, ABANDONWEL, EXITWITHTIMEOUT
    # Para dialer (omnidialer): EXIT_TIMEOUT, EXIT_ABANDON
    EVENTOS_NO_CONTESTADAS = [
        'ABANDON', 'ABANDONWEL', 'EXITWITHTIMEOUT', 'EXIT_TIMEOUT', 'EXIT_ABANDON',
        'EXIT_HANDOFF_TIMEOUT', 'EXIT_HANDOFF_ABANDON',
    ]
    
    # Todos los eventos relevantes para el cálculo
    EVENTOS_RELEVANTES = EVENTOS_CONTESTADAS + EVENTOS_NO_CONTESTADAS
    
    def __init__(self, fecha_desde=None, fecha_hasta=None, campanas=None, 
                 tiempo_objetivo=None):
        """
        Inicializa el reporte de Nivel de Servicio
        
        Args:
            fecha_desde: Fecha de inicio del período (datetime)
            fecha_hasta: Fecha de fin del período (datetime)
            campanas: Lista de campañas a analizar (QuerySet o lista de IDs)
            tiempo_objetivo: Tiempo objetivo en segundos (default: 20)
        """
        self.fecha_desde = fecha_desde
        self.fecha_hasta = fecha_hasta
        self.tiempo_objetivo = tiempo_objetivo or self.TIEMPO_OBJETIVO_DEFAULT
        self.campanas = campanas or []
        
        # Normalizar fechas
        if self.fecha_desde:
            self.fecha_desde = datetime_hora_minima_dia(self.fecha_desde)
        if self.fecha_hasta:
            self.fecha_hasta = datetime_hora_maxima_dia(self.fecha_hasta)
        
        # Resultados del reporte
        self.estadisticas = {}
        self.estadisticas_por_campana = {}
        
        # Calcular estadísticas
        self._calcular_estadisticas()
    
    def _calcular_estadisticas(self):
        """Calcula todas las estadísticas del reporte"""
        if not self.fecha_desde or not self.fecha_hasta:
            logger.warning("Fechas no especificadas para el reporte de Service Level")
            return
        
        # Obtener llamadas entrantes y Dialer en el período
        llamadas = self._obtener_llamadas()
        
        # Calcular estadísticas generales
        self._calcular_estadisticas_generales(llamadas)
        
        # Calcular estadísticas por campaña
        self._calcular_estadisticas_por_campana(llamadas)
    
    def _obtener_llamadas(self):
        """
        Obtiene las llamadas entrantes y Dialer relevantes para el cálculo del Service Level
        """
        filtros = {
            'fecha_fin__gte': self.fecha_desde,
            'fecha_fin__lte': self.fecha_hasta,
            'tipo_llamada__in': [LlamadaResumen.LLAMADA_ENTRANTE, LlamadaResumen.LLAMADA_DIALER],
            'event__in': self.EVENTOS_RELEVANTES,
        }
        
        # Filtrar por campañas si se especificaron
        if self.campanas:
            if isinstance(self.campanas[0], Campana):
                campanas_ids = [c.id for c in self.campanas]
            else:
                campanas_ids = self.campanas
            filtros['campana_id__in'] = campanas_ids
        
        return LlamadaResumen.objects.filter(**filtros)
    
    def _calcular_estadisticas_generales(self, llamadas):
        """
        Calcula estadísticas generales (todas las campañas juntas)
        """
        total_llamadas = llamadas.count()
        
        # Llamadas contestadas
        llamadas_contestadas = llamadas.filter(event__in=self.EVENTOS_CONTESTADAS)
        total_contestadas = llamadas_contestadas.count()
        
        # Llamadas contestadas dentro del tiempo objetivo
        llamadas_objetivo = llamadas_contestadas.filter(
            bridge_wait_time__lte=self.tiempo_objetivo
        )
        total_objetivo = llamadas_objetivo.count()
        
        # Llamadas no contestadas
        llamadas_no_contestadas = llamadas.filter(event__in=self.EVENTOS_NO_CONTESTADAS)
        total_no_contestadas = llamadas_no_contestadas.count()
        
        # Llamadas transferidas
        llamadas_transferidas = llamadas.filter(es_transferencia=True)
        total_transferidas = llamadas_transferidas.count()
        
        # Calcular porcentajes
        porcentaje_objetivo = 0.0
        porcentaje_contestadas = 0.0
        tasa_abandono = 0.0
        tasa_transferencia = 0.0
        if total_llamadas > 0:
            porcentaje_objetivo = (total_objetivo / total_llamadas) * 100
            porcentaje_contestadas = (total_contestadas / total_llamadas) * 100
            tasa_abandono = (total_no_contestadas / total_llamadas) * 100
            tasa_transferencia = (total_transferidas / total_llamadas) * 100
        
        # Tiempo promedio de espera (solo para llamadas contestadas)
        tiempo_promedio_espera = None
        if llamadas_contestadas.exists():
            tiempo_promedio = llamadas_contestadas.aggregate(
                promedio=Avg('bridge_wait_time')
            )['promedio']
            if tiempo_promedio:
                tiempo_promedio_espera = float(tiempo_promedio)
        
        # Tiempo promedio de espera antes de abandonar
        tiempo_promedio_abandono = None
        if llamadas_no_contestadas.exists():
            tiempo_abandono = llamadas_no_contestadas.aggregate(
                promedio=Avg('bridge_wait_time')
            )['promedio']
            if tiempo_abandono:
                tiempo_promedio_abandono = float(tiempo_abandono)
        
        # Distribución por rangos de tiempo
        distribucion_rangos = self._calcular_distribucion_rangos(llamadas_contestadas)
        
        # Calcular KPI de Eficiencia (Tiempo de conversación + Hold + ACW)
        kpi_eficiencia = self._calcular_kpi_eficiencia(llamadas_contestadas)
        
        self.estadisticas = {
            'total_llamadas': total_llamadas,
            'total_contestadas': total_contestadas,
            'total_no_contestadas': total_no_contestadas,
            'total_transferidas': total_transferidas,
            'total_objetivo': total_objetivo,
            'porcentaje_objetivo': round(porcentaje_objetivo, 2),
            'porcentaje_contestadas': round(porcentaje_contestadas, 2),
            'tasa_abandono': round(tasa_abandono, 2),
            'tasa_transferencia': round(tasa_transferencia, 2),
            'tiempo_objetivo': self.tiempo_objetivo,
            'tiempo_promedio_espera': round(tiempo_promedio_espera, 2) if tiempo_promedio_espera else None,
            'tiempo_promedio_abandono': round(tiempo_promedio_abandono, 2) if tiempo_promedio_abandono else None,
            'distribucion_rangos': distribucion_rangos,
            'kpi_eficiencia': kpi_eficiencia,
        }
    
    def _calcular_estadisticas_por_campana(self, llamadas):
        """
        Calcula estadísticas desglosadas por campaña
        """
        # Agrupar por campaña
        campanas_ids = llamadas.values_list('campana_id', flat=True).distinct()
        
        for campana_id in campanas_ids:
            if not campana_id:
                continue
            
            try:
                campana = Campana.objects.get(id=campana_id)
            except Campana.DoesNotExist:
                continue
            
            llamadas_campana = llamadas.filter(campana_id=campana_id)
            
            total_llamadas = llamadas_campana.count()
            
            # Llamadas contestadas
            llamadas_contestadas = llamadas_campana.filter(event__in=self.EVENTOS_CONTESTADAS)
            total_contestadas = llamadas_contestadas.count()
            
            # Llamadas contestadas dentro del tiempo objetivo
            llamadas_objetivo = llamadas_contestadas.filter(
                bridge_wait_time__lte=self.tiempo_objetivo
            )
            total_objetivo = llamadas_objetivo.count()
            
            # Llamadas no contestadas
            llamadas_no_contestadas = llamadas_campana.filter(event__in=self.EVENTOS_NO_CONTESTADAS)
            total_no_contestadas = llamadas_no_contestadas.count()
            
            # Llamadas transferidas
            llamadas_transferidas = llamadas_campana.filter(es_transferencia=True)
            total_transferidas = llamadas_transferidas.count()
            
            # Calcular porcentajes
            porcentaje_objetivo = 0.0
            porcentaje_contestadas = 0.0
            tasa_abandono = 0.0
            tasa_transferencia = 0.0
            if total_llamadas > 0:
                porcentaje_objetivo = (total_objetivo / total_llamadas) * 100
                porcentaje_contestadas = (total_contestadas / total_llamadas) * 100
                tasa_abandono = (total_no_contestadas / total_llamadas) * 100
                tasa_transferencia = (total_transferidas / total_llamadas) * 100
            
            # Tiempo promedio de espera
            tiempo_promedio_espera = None
            if llamadas_contestadas.exists():
                tiempo_promedio = llamadas_contestadas.aggregate(
                    promedio=Avg('bridge_wait_time')
                )['promedio']
                if tiempo_promedio:
                    tiempo_promedio_espera = float(tiempo_promedio)
            
            # Tiempo promedio de abandono
            tiempo_promedio_abandono = None
            if llamadas_no_contestadas.exists():
                tiempo_abandono = llamadas_no_contestadas.aggregate(
                    promedio=Avg('bridge_wait_time')
                )['promedio']
                if tiempo_abandono:
                    tiempo_promedio_abandono = float(tiempo_abandono)
            
            # Distribución por rangos
            distribucion_rangos = self._calcular_distribucion_rangos(llamadas_contestadas)
            
            # Calcular KPI de Eficiencia por campaña
            kpi_eficiencia = self._calcular_kpi_eficiencia(llamadas_contestadas)
            
            self.estadisticas_por_campana[campana_id] = {
                'campana_id': campana_id,
                'campana_nombre': force_str(campana.nombre),
                'total_llamadas': total_llamadas,
                'total_contestadas': total_contestadas,
                'total_no_contestadas': total_no_contestadas,
                'total_transferidas': total_transferidas,
                'total_objetivo': total_objetivo,
                'porcentaje_objetivo': round(porcentaje_objetivo, 2),
                'porcentaje_contestadas': round(porcentaje_contestadas, 2),
                'tasa_abandono': round(tasa_abandono, 2),
                'tasa_transferencia': round(tasa_transferencia, 2),
                'tiempo_promedio_espera': round(tiempo_promedio_espera, 2) if tiempo_promedio_espera else None,
                'tiempo_promedio_abandono': round(tiempo_promedio_abandono, 2) if tiempo_promedio_abandono else None,
                'distribucion_rangos': distribucion_rangos,
                'kpi_eficiencia': kpi_eficiencia,
            }
    
    def _calcular_distribucion_rangos(self, llamadas_contestadas):
        """
        Calcula la distribución de llamadas contestadas por rangos de tiempo de espera
        """
        rangos = [
            {'nombre': '0-10s', 'min': 0, 'max': 10, 'cantidad': 0},
            {'nombre': '10-20s', 'min': 10, 'max': 20, 'cantidad': 0},
            {'nombre': '20-30s', 'min': 20, 'max': 30, 'cantidad': 0},
            {'nombre': '30-60s', 'min': 30, 'max': 60, 'cantidad': 0},
            {'nombre': '60s+', 'min': 60, 'max': None, 'cantidad': 0},
        ]
        
        for llamada in llamadas_contestadas:
            wait_time = float(llamada.bridge_wait_time or 0)
            
            for rango in rangos:
                if rango['max'] is None:
                    # Último rango (60s+)
                    if wait_time >= rango['min']:
                        rango['cantidad'] += 1
                        break
                else:
                    if rango['min'] <= wait_time < rango['max']:
                        rango['cantidad'] += 1
                        break
        
        # Calcular porcentajes
        total = sum(r['cantidad'] for r in rangos)
        for rango in rangos:
            porcentaje = (rango['cantidad'] / total * 100) if total > 0 else 0
            rango['porcentaje'] = round(porcentaje, 2)
        
        return rangos
    
    def _calcular_kpi_eficiencia(self, llamadas_contestadas):
        """
        Calcula el KPI de Eficiencia: Suma del tiempo de conversación, 
        tiempo en espera (Hold) y tiempo administrativo tras la llamada (ACW).
        
        Returns:
            dict con los valores del KPI de eficiencia
        """
        if not llamadas_contestadas.exists():
            return {
                'tiempo_total_segundos': 0,
                'tiempo_total_minutos': 0,
                'tiempo_conversacion_segundos': 0,
                'tiempo_hold_segundos': 0,
                'tiempo_acw_segundos': 0,
                'promedio_por_llamada_segundos': 0,
            }
        
        # 1. Tiempo de conversación: suma de duracion_segundos de todas las llamadas contestadas
        tiempo_conversacion = llamadas_contestadas.aggregate(
            total=Sum('duracion_segundos')
        )['total'] or Decimal('0')
        tiempo_conversacion_segundos = float(tiempo_conversacion)
        
        # 2. Tiempo en Hold: calcular suma de tiempos entre eventos HOLD y UNHOLD
        tiempo_hold_segundos = self._calcular_tiempo_hold_total(llamadas_contestadas)
        
        # 3. Tiempo ACW: tiempo de pausa ACW (pausa_id='0') después de cada llamada
        tiempo_acw_segundos = self._calcular_tiempo_acw_total(llamadas_contestadas)
        
        # Suma total
        tiempo_total_segundos = tiempo_conversacion_segundos + tiempo_hold_segundos + tiempo_acw_segundos
        tiempo_total_minutos = tiempo_total_segundos / 60.0
        
        # Promedio por llamada
        total_llamadas = llamadas_contestadas.count()
        promedio_por_llamada_segundos = tiempo_total_segundos / total_llamadas if total_llamadas > 0 else 0
        
        return {
            'tiempo_total_segundos': round(tiempo_total_segundos, 2),
            'tiempo_total_minutos': round(tiempo_total_minutos, 2),
            'tiempo_conversacion_segundos': round(tiempo_conversacion_segundos, 2),
            'tiempo_hold_segundos': round(tiempo_hold_segundos, 2),
            'tiempo_acw_segundos': round(tiempo_acw_segundos, 2),
            'promedio_por_llamada_segundos': round(promedio_por_llamada_segundos, 2),
        }
    
    def _calcular_tiempo_hold_total(self, llamadas_contestadas):
        """
        Calcula el tiempo total en Hold para las llamadas contestadas.
        Suma los tiempos entre eventos HOLD y UNHOLD.
        """
        tiempo_hold_total = 0.0
        
        # Obtener todos los callids de las llamadas contestadas
        callids = llamadas_contestadas.values_list('callid', flat=True).distinct()
        
        # Filtrar por campañas si se especificaron
        filtros_hold = {
            'fecha_fin__gte': self.fecha_desde,
            'fecha_fin__lte': self.fecha_hasta,
            'event': 'HOLD',
            'callid__in': callids,
        }
        
        if self.campanas:
            if isinstance(self.campanas[0], Campana):
                campanas_ids = [c.id for c in self.campanas]
            else:
                campanas_ids = self.campanas
            filtros_hold['campana_id__in'] = campanas_ids
        
        # Obtener todos los eventos HOLD
        eventos_hold = LlamadaResumen.objects.filter(**filtros_hold).order_by('fecha_fin')
        
        for hold_event in eventos_hold:
            inicio_hold = hold_event.fecha_fin
            callid = hold_event.callid
            
            # Buscar el siguiente evento UNHOLD para el mismo callid
            unhold_event = LlamadaResumen.objects.filter(
                callid=callid,
                event='UNHOLD',
                fecha_fin__gt=inicio_hold,
                fecha_fin__lte=self.fecha_hasta
            ).order_by('fecha_fin').first()
            
            if unhold_event:
                # Hay un UNHOLD, calcular la diferencia
                fin_hold = unhold_event.fecha_fin
                tiempo_hold = (fin_hold - inicio_hold).total_seconds()
                tiempo_hold_total += max(0, tiempo_hold)
            else:
                # No hay UNHOLD, buscar el siguiente evento de finalización de llamada
                # o usar la fecha de fin de la llamada contestada
                llamada_final = llamadas_contestadas.filter(callid=callid).first()
                if llamada_final and llamada_final.fecha_fin:
                    fin_hold = llamada_final.fecha_fin
                    tiempo_hold = (fin_hold - inicio_hold).total_seconds()
                    tiempo_hold_total += max(0, tiempo_hold)
        
        return tiempo_hold_total
    
    def _calcular_tiempo_acw_total(self, llamadas_contestadas):
        """
        Calcula el tiempo total de ACW (After Call Work) después de las llamadas contestadas.
        ACW es la pausa con pausa_id='0' que ocurre después de cada llamada.
        """
        tiempo_acw_total = 0.0
        
        # Obtener todos los callids y agentes de las llamadas contestadas
        llamadas_info = llamadas_contestadas.values('callid', 'agente_id', 'fecha_fin').distinct()
        
        for llamada_info in llamadas_info:
            callid = llamada_info['callid']
            agente_id = llamada_info['agente_id']
            fecha_fin_llamada = llamada_info['fecha_fin']
            
            if not agente_id or not fecha_fin_llamada:
                continue
            
            # Buscar eventos PAUSEALL con pausa_id='0' (ACW) después de la finalización de la llamada
            # dentro de un rango razonable (ej: hasta 1 hora después)
            fecha_limite_acw = fecha_fin_llamada + timedelta(hours=1)
            
            pausa_acw = ActividadAgenteLog.objects.filter(
                agente_id=agente_id,
                event='PAUSEALL',
                pausa_id='0',
                time__gte=fecha_fin_llamada,
                time__lte=min(fecha_limite_acw, self.fecha_hasta)
            ).order_by('time').first()
            
            if pausa_acw:
                inicio_acw = pausa_acw.time
                
                # Buscar el siguiente UNPAUSEALL para el mismo agente
                unpause_acw = ActividadAgenteLog.objects.filter(
                    agente_id=agente_id,
                    event='UNPAUSEALL',
                    pausa_id='0',
                    time__gt=inicio_acw,
                    time__lte=self.fecha_hasta
                ).order_by('time').first()
                
                if unpause_acw:
                    fin_acw = unpause_acw.time
                    tiempo_acw = (fin_acw - inicio_acw).total_seconds()
                    tiempo_acw_total += max(0, tiempo_acw)
                else:
                    # Si no hay UNPAUSEALL, usar un límite razonable (ej: 30 minutos máximo)
                    fin_acw = min(inicio_acw + timedelta(minutes=30), self.fecha_hasta)
                    tiempo_acw = (fin_acw - inicio_acw).total_seconds()
                    tiempo_acw_total += max(0, tiempo_acw)
        
        return tiempo_acw_total
    
    def obtener_kpis(self):
        """
        Retorna los KPIs principales del reporte
        """
        return {
            'nivel_servicio': self.estadisticas.get('porcentaje_objetivo', 0),
            'tiempo_objetivo': self.tiempo_objetivo,
            'total_llamadas': self.estadisticas.get('total_llamadas', 0),
            'llamadas_objetivo': self.estadisticas.get('total_objetivo', 0),
            'tiempo_promedio_espera': self.estadisticas.get('tiempo_promedio_espera'),
            'tasa_abandono': self.estadisticas.get('tasa_abandono', 0),
            'tasa_transferencia': self.estadisticas.get('tasa_transferencia', 0),
            'kpi_eficiencia': self.estadisticas.get('kpi_eficiencia', {}),
        }

