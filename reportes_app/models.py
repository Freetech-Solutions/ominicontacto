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

from __future__ import unicode_literals

from django.utils.timezone import localtime, timedelta
from ominicontacto_app.utiles import crear_segmento_grabaciones_url, datetime_hora_maxima_dia, \
    datetime_hora_minima_dia, fecha_local
import urllib.parse
from django.db import models, connection
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.core.exceptions import SuspiciousOperation
from django.utils.translation import gettext as _
from django.conf import settings
from django.forms.models import model_to_dict

from ominicontacto_app.models import AgenteProfile, CalificacionCliente, Campana, Contacto, \
    GrabacionMarca, HistoricalCalificacionCliente


class QueueLog(models.Model):
    """ Tabla queue_log para la insercion de Logs desde Asterisk """
    # time character varying(26) DEFAULT NULL::character varying,
    time = models.CharField(max_length=100, blank=True,
                            null=True, default=None)
    # callid character varying(32) DEFAULT ''::character varying NOT NULL,
    callid = models.CharField(
        max_length=100, blank=True, null=False, default='')
    # queuename character varying(32) DEFAULT ''::character varying NOT NULL,
    queuename = models.CharField(max_length=100, blank=True, default='')
    # agent character varying(32) DEFAULT ''::character varying NOT NULL,
    agent = models.CharField(max_length=100, blank=True, default='')
    # event character varying(32) DEFAULT ''::character varying NOT NULL,
    event = models.CharField(max_length=100, blank=True, default='')
    # data1 character varying(100) DEFAULT ''::character varying NOT NULL,
    data1 = models.CharField(max_length=100, blank=True, default='')
    # data2 character varying(100) DEFAULT ''::character varying NOT NULL,
    data2 = models.CharField(max_length=100, blank=True, default='')
    # data3 character varying(100) DEFAULT ''::character varying NOT NULL,
    data3 = models.CharField(max_length=100, blank=True, default='')
    # data4 character varying(100) DEFAULT ''::character varying NOT NULL,
    data4 = models.CharField(max_length=100, blank=True, default='')
    # data5 character varying(100) DEFAULT ''::character varying NOT NULL
    data5 = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        db_table = 'queue_log'


class LlamadaLogManager(models.Manager):

    def obtener_tiempo_llamadas_agente(self, eventos, fecha_desde, fecha_hasta, agentes):
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        result = LlamadaLog.objects.values_list('agente_id') \
                                   .annotate(sum=Sum('duracion_llamada')) \
                                   .filter(time__gte=fecha_desde, time__lte=fecha_hasta) \
                                   .filter(event__in=eventos) \
                                   .filter(agente_id__in=agentes) \
                                   .exclude(campana_id=0) \
                                   .order_by('agente_id')

        return result

    def obtener_count_evento_agente(self, eventos, fecha_desde, fecha_hasta, agentes):
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        cursor = connection.cursor()
        sql = """select agente_id, count(*)
                 from reportes_app_llamadalog where time between %(fecha_desde)s and
                 %(fecha_hasta)s and event = ANY(%(eventos)s) and agente_id = ANY(%(agentes)s)
                 AND NOT campana_id = '0'
                 GROUP BY agente_id order by agente_id
        """
        params = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'eventos': eventos,
            'agentes': agentes,
        }

        cursor.execute(sql, params)
        values = cursor.fetchall()
        return values

    def obtener_agentes_campanas_total(self, eventos, fecha_desde, fecha_hasta, agentes,
                                       campanas):
        """
        Query que sumariza por agente y campaña la cantidad y duración de
        llamadas para los eventos indicados.
        """

        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        cursor = connection.cursor()
        sql = """select agente_id, campana_id, SUM(duracion_llamada::integer), Count(*)
                 from reportes_app_llamadalog where time between %(fecha_desde)s and
                 %(fecha_hasta)s and event = ANY(%(eventos)s) and agente_id = ANY(%(agentes)s)
                 and campana_id = ANY(%(campanas)s) GROUP BY agente_id, campana_id order by
                 agente_id, campana_id
        """
        params = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'eventos': eventos,
            'agentes': agentes,
            'campanas': [campana.id for campana in campanas],
        }

        cursor.execute(sql, params)
        values = cursor.fetchall()
        return values

    def obtener_count_agente(self):
        try:
            return self.values('agente_id').annotate(
                cantidad=Count('agente_id')).order_by('agente_id')
        except LlamadaLog.DoesNotExist:
            raise (SuspiciousOperation(_("No se encontraron llamadas ")))

    def obtener_tiempo_llamada_agente(self, eventos, fecha_desde, fecha_hasta, agente_id):
        """devuelve la duracion de llamadas y fecha"""
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        try:
            return self.filter(agente_id=agente_id, event__in=eventos,
                               time__range=(fecha_desde, fecha_hasta))
        except LlamadaLog.DoesNotExist:
            raise (SuspiciousOperation(_("No se encontraron llamadas ")))

    def obtener_count_evento_agente_agrupado_fecha(self, eventos, fecha_desde,
                                                   fecha_hasta, agente_id):
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        return LlamadaLog.objects.filter(event__in=eventos, agente_id=agente_id,
                                         time__range=(fecha_desde, fecha_hasta)).exclude(
            campana_id=0).annotate(
                fecha=TruncDate('time')).values('fecha').annotate(cantidad=Count('fecha'))

    def obtener_historico_llamadas_del_dia(self, agente_id, fecha):
        fecha_desde = datetime_hora_minima_dia(fecha)
        fecha_hasta = datetime_hora_maxima_dia(fecha)
        return self.filter(agente_id=agente_id,
                           time__gte=fecha_desde, time__lte=fecha_hasta,
                           event__in=LlamadaLog.EVENTOS_FIN_CONEXION + LlamadaLog.EVENTOS_REJECT
                           + list(LlamadaLog.EVENTOS_NO_CONEXION))

    def entrantes_espera(self):
        campanas_eliminadas_ids = list(
            Campana.objects.obtener_borradas().values_list('pk', flat=True))
        ids_llamadas_entrantes = list(self.filter(
            tipo_campana=Campana.TYPE_ENTRANTE, event='ENTERQUEUE').values_list(
                'callid', flat=True).exclude(campana_id__in=campanas_eliminadas_ids))
        logs = self.filter(callid__in=ids_llamadas_entrantes, event='CONNECT')
        return logs

    def entrantes_abandono(self):
        campanas_eliminadas_ids = list(
            Campana.objects.obtener_borradas().values_list('pk', flat=True))
        return self.filter(
            tipo_campana=Campana.TYPE_ENTRANTE,
            tipo_llamada=LlamadaLog.LLAMADA_ENTRANTE,
            event__in=['ABANDON', 'ABANDONWEL']).exclude(
                campana_id__in=campanas_eliminadas_ids)

    def obtener_grabaciones_by_fecha_intervalo_campanas(self, fecha_inicio, fecha_fin, campanas):
        fecha_inicio = datetime_hora_minima_dia(fecha_inicio)
        fecha_fin = datetime_hora_maxima_dia(fecha_fin)
        INCLUDED_EVENTS = ['COMPLETEAGENT', 'COMPLETEOUTNUM', 'BT-COMPLETE', 'COMPLETE-BT',
                           'CT-ANSWER', 'CT-COMPLETE', 'COMPLETE-CT',
                           'CAMPCT-COMPLETE', 'COMPLETE-CAMPCT',
                           'CAMPT-COMPLETE', 'COMPLETE-CAMPT',
                           'BTOUT-COMPLETE', 'COMPLETE-BTOUT', 'CTOUT-COMPLETE',
                           'COMPLETE-CTOUT', 'CAMPT-FAIL', 'BT-BUSY', 'BTOUT-TRY', 'CT-ABANDON',
                           'CTOUT-TRY', 'BT-TRY']

        query = self.filter(time__range=(fecha_inicio, fecha_fin),
                            campana_id__in=campanas,
                            event__in=INCLUDED_EVENTS,
                            archivo_grabacion__isnull=False)
        query = query.filter(Q(duracion_llamada__gt=0) | Q(event='CT-ANSWER'))
        query = query.order_by('-time')
        return query.exclude(archivo_grabacion='-1')

    def obtener_grabaciones_by_filtro(self, fecha_desde, fecha_hasta, tipo_llamada, tel_cliente,
                                      callid, id_contacto_externo, agente, campana, campanas,
                                      marcadas, duracion, gestion, calificaciones):
        INCLUDED_EVENTS = ['COMPLETEAGENT', 'COMPLETEOUTNUM', 'BT-COMPLETE', 'COMPLETE-BT',
                           'CT-ANSWER', 'CT-COMPLETE', 'COMPLETE-CT',
                           'CAMPCT-COMPLETE', 'COMPLETE-CAMPCT',
                           'CAMPT-COMPLETE', 'COMPLETE-CAMPT',
                           'BTOUT-COMPLETE', 'COMPLETE-BTOUT', 'CTOUT-COMPLETE',
                           'COMPLETE-CTOUT', 'CAMPT-FAIL', 'BT-BUSY', 'BTOUT-TRY', 'CT-ABANDON',
                           'CTOUT-TRY', 'BT-TRY']
        # Campañas a Filtrar:
        campanas_id = set([campana.id for campana in campanas])
        if campana:
            if campana != 'activas' and campana != 'borradas':
                campanas_id = [campana]
            else:
                for camp in campanas:
                    if (camp.estado == Campana.ESTADO_BORRADA and campana == 'activas') or \
                            (camp.estado != Campana.ESTADO_BORRADA and campana == 'borradas'):
                        campanas_id.remove(camp.id)
        grabaciones = self.filter(campana_id__in=campanas_id,
                                  archivo_grabacion__isnull=False,
                                  event__in=INCLUDED_EVENTS)

        grabaciones = grabaciones.filter(Q(duracion_llamada__gt=0) | Q(event='CT-ANSWER'))
        grabaciones = grabaciones.exclude(archivo_grabacion='-1')

        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)
            grabaciones = grabaciones.filter(time__range=(fecha_desde, fecha_hasta))

        if calificaciones:
            historicals = HistoricalCalificacionCliente.objects.filter(
                opcion_calificacion_id__in=calificaciones)
            # Optimizo filtro calificaciones historicas por fecha
            if fecha_desde and fecha_hasta:
                historicals = historicals.filter(modified__range=(fecha_desde, fecha_hasta))
            call_ids = historicals.values_list('callid', flat=True)
            grabaciones = grabaciones.filter(callid__in=call_ids)

        if tipo_llamada:
            grabaciones = grabaciones.filter(tipo_llamada=tipo_llamada)
        if tel_cliente:
            grabaciones = grabaciones.filter(
                numero_marcado__contains=tel_cliente)
        if callid:
            grabaciones = grabaciones.filter(callid=callid)
        if agente:
            grabaciones = grabaciones.filter(agente_id=agente.id)

        if duracion and duracion > 0:
            grabaciones = grabaciones.filter(duracion_llamada__gte=duracion)
        if id_contacto_externo:
            telefonos_contacto = Contacto.objects.values('telefono')
            telefono_id_externo = telefonos_contacto.filter(
                id_externo=id_contacto_externo)
            grabaciones = grabaciones.filter(
                numero_marcado__in=[t['telefono'] for t in telefono_id_externo])
        if marcadas:
            total_grabaciones_marcadas = self.obtener_grabaciones_marcadas()
            grabaciones = grabaciones & total_grabaciones_marcadas
        if gestion:
            calificaciones_gestion_campanas = CalificacionCliente.obtener_califs_gestion_campanas(
                campanas, fecha_desde, fecha_hasta)
            callids_calificaciones_gestion = list(calificaciones_gestion_campanas.values_list(
                'callid', flat=True))
            grabaciones = grabaciones.filter(
                callid__in=callids_calificaciones_gestion)

        return grabaciones.order_by('-time')

    def obtener_grabaciones_marcadas(self):
        marcaciones = list(GrabacionMarca.objects.values_list('callid', flat=True))
        return self.filter(callid__in=marcaciones, archivo_grabacion__isnull=False,
                           duracion_llamada__gt=0).exclude(archivo_grabacion='-1') \
            .exclude(event='ENTERQUEUE-TRANSFER')

    def obtener_evento_hold_fecha(self, eventos, fecha_desde, fecha_hasta, agente_id):
        """devuelve el hold"""
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        try:
            return self.filter(agente_id=agente_id, event__in=eventos,
                               time__range=(fecha_desde, fecha_hasta))
        except LlamadaLog.DoesNotExist:
            raise (SuspiciousOperation(_("No se encontraron holds ")))

    def obtener_cantidades_de_transferencias_recibidas(
            self, fecha_inicial, fecha_final, agentes, campanas_ids):
        """
            Contabiliza Transferencias directas A AGENTE. Agrupa por agente y por campaña
        """
        resultados = self.filter(
            time__range=(fecha_inicial, fecha_final),
            agente_id__in=agentes, campana_id__in=campanas_ids,
            event__in=['BT-ANSWER', 'CT-ACCEPT']).values('agente_id', 'campana_id').annotate(
                cant=Count('id')).order_by('agente_id', 'campana_id')
        cantidades = {agente_id: {} for agente_id in agentes}
        for resultado in resultados:
            cantidades[resultado['agente_id']][resultado['campana_id']] = resultado['cant']
        return cantidades

    def cantidad_contactos_llamados(self, campana):
        return self.filter(
            campana_id=campana.id,
            contacto_id__in=Contacto.objects.filter(
                bd_contacto=campana.bd_contacto,
                es_originario=True,
            ),
        ).only("id").distinct("contacto_id").count()

    def cantidad_llamadas_rechazadas_fecha(self, agente_id, fecha_inferior, fecha_superior):
        fecha_desde = datetime_hora_minima_dia(fecha_inferior)
        fecha_hasta = datetime_hora_maxima_dia(fecha_superior)
        return self.filter(agente_id=agente_id, agente_extra_id=agente_id,
                           time__gte=fecha_desde, time__lte=fecha_hasta,
                           event__in=LlamadaLog.EVENTOS_REJECT).exclude(campana_id='0').count()

    def cantidad_llamadas_no_atendidas_fecha(self, agente_id, fecha_inferior, fecha_superior):
        fecha_desde = datetime_hora_minima_dia(fecha_inferior)
        fecha_hasta = datetime_hora_maxima_dia(fecha_superior)
        return self.filter(
            agente_id=agente_id,
            agente_extra_id=-1,
            time__gte=fecha_desde,
            time__lte=fecha_hasta,
            event__in=LlamadaLog.EVENTOS_REJECT).exclude(campana_id='0').count()

    def get_datos_grabacion(self, callid):
        log = self.filter(callid=callid, archivo_grabacion__isnull=False,
                          duracion_llamada__gt=0).exclude(archivo_grabacion='-1').first()
        if not log:
            return None, None
        return log.str_dia_grabacion, log.archivo_grabacion


class LlamadaLog(models.Model):
    """
    Define la estructura de un evento de log de cola relacionado con una llamada
    """

    # Tipos de llamada
    LLAMADA_MANUAL = 1
    LLAMADA_DIALER = 2
    LLAMADA_ENTRANTE = 3
    LLAMADA_PREVIEW = 4
    LLAMADA_CLICK2CALL = 6
    LLAMADA_TRANSFER_INTERNA = 8
    LLAMADA_TRANSFER_EXTERNA = 9

    TIPOS_LLAMADAS_SALIENTES = (
        LLAMADA_MANUAL, LLAMADA_PREVIEW, LLAMADA_CLICK2CALL)

    TYPE_LLAMADA_CHOICES = (
        (LLAMADA_DIALER, 'DIALER'),
        (LLAMADA_ENTRANTE, 'INBOUND'),
        (LLAMADA_MANUAL, 'MANUAL'),
        (LLAMADA_PREVIEW, 'PREVIEW'),
    )

    EVENTOS_NO_CONTACTACION = ('NOANSWER', 'CANCEL', 'BUSY', 'CHANUNAVAIL', 'FAIL', 'OTHER',
                               'BLACKLIST', 'CONGESTION', 'NONDIALPLAN')

    EVENTOS_NO_DIALOGO = (
        'EXIT_ABANDON',
        'EXIT_TIMEOUT',
        'EXIT_HANDOFF_ABANDON',
        'EXIT_HANDOFF_TIMEOUT',
    )

    EVENTOS_NO_CONEXION = EVENTOS_NO_CONTACTACION + EVENTOS_NO_DIALOGO

    # Eventos que indican que no se pudo completar una transferencia
    EVENTOS_NO_CONEXION_TRANSFER = [
        'BT-BUSY', 'BT-CANCEL', 'BT-CHANUNAVAIL', 'BT-CONGESTION', 'BT-NOANSWER', 'BT-ABANDON',
        'CT-DISCARD', 'CT-BUSY', 'CT-CANCEL', 'CT-CHANUNAVAIL', 'CT-CONGESTION',
        'CAMPCT-DISCARD', 'CAMPCT-BUSY', 'CAMPCT-CANCEL', 'CAMPCT-CHANUNAVAIL', 'CAMPCT-CONGESTION',
        'BTOUT-BUSY', 'BTOUT-CANCEL', 'BTOUT-CONGESTION', 'BTOUT-CHANUNAVAIL', 'BTOUT-ABANDON',
        'CTOUT-DISCARD', 'CTOUT-BUSY', 'CTOUT-CANCEL', 'CTOUT-CHANUNAVAIL', 'CTOUT-CONGESTION'
    ]

    # Eventos que marcan el fin de la conexion con un agente. (Puede ser por conectar con otro)
    EVENTOS_FIN_CONEXION = ['COMPLETEAGENT', 'COMPLETEOUTNUM',
                            'BT-TRY', 'COMPLETE-BT',
                            'CAMPT-COMPLETE', 'CAMPT-FAIL', 'COMPLETE-CAMPT',
                            'CT-COMPLETE', 'COMPLETE-CT', 'ABANDON-CT',
                            'CAMPCT-COMPLETE', 'COMPLETE-CAMPCT', 'ABANDON-CAMPCT',
                            'BTOUT-TRY',
                            'CTOUT-COMPLETE', ]

    # Marcan el fin de la conexion por una transferencia para el agente original
    EVENTOS_FIN_CONEXION_POR_TRANSFER = ['BT-TRY', 'BTOUT-TRY',
                                         'CAMPT-COMPLETE', 'CAMPT-FAIL',
                                         'CT-COMPLETE', 'CAMPCT-COMPLETE', 'CTOUT-COMPLETE']

    EVENTOS_INICIO_CONEXION = ['CONNECT', 'ANSWER',
                               'BT-ANSWER', 'CT-ACCEPT']  # Con id_agente

    # eventos inicio conexion de una llamada
    # (No incluye valores de eventos de transferencias si ocurren luego)
    EVENTOS_INICIO_CONEXION_AGENTE = ['CONNECT', 'ANSWER']  # Con id_agente

    # eventos fin conexion de una llamada
    # (No incluye valores de eventos de transferencias si ocurren luego)
    EVENTOS_FIN_CONEXION_AGENTE = ['COMPLETEAGENT', 'COMPLETEOUTNUM']  # Con id_agente

    # eventos de hold en una llamada
    EVENTOS_HOLD = ['HOLD', 'UNHOLD']

    # eventos de no atendida una llamada
    EVENTOS_REJECT = ['RINGNOANSWER']

    # EVENTOS_TRANSFER_TRY_IN = ['BT-TRY', 'ENTERQUEUE-TRANSFER', 'CT-TRY']
    # EVENTOS_TRANSFER_TRY_OUT = ['BTOUT-TRY', 'CTOUT-TRY']
    # EVENTOS_TRANSFER_TRY = EVENTOS_TRANSFER_TRY_IN + EVENTOS_TRANSFER_TRY_OUT
    # EVENTOS_TRANSFER_OK = ['BT-ANSWER', 'CONNECT', 'CT-ACCEPT', 'BTOUT-ANSWER', 'CTOUT-ACCEPT']
    # EVENTOS_BT_NO_CONNECT = ['BT-BUSY', 'BT-CANCEL', 'BT-CHANUNAVAIL', 'BT-CONGESTION',
    #                          'BT-ABANDON', 'BT-NOANSWER']
    # EVENTOS_CT_NO_CONNECT = ['CT-DISCARD', 'CT-BUSY', 'CT-CANCEL', 'CT-CHANUNAVAIL',
    #                          'CT-CONGESTION']
    # EVENTOS_BTOUT_NO_CONNECT = ['BTOUT-BUSY', 'BTOUT-CANCEL', 'BTOUT-CONGESTION',
    #                             'BTOUT-CHANUNAVAIL', 'BTOUT-ABANDON']
    # EVENTOS_CTOUT_NO_CONNECT = ['CTOUT-DISCARD', 'CTOUT-BUSY', 'CTOUT-CANCEL',
    #                             'CTOUT-CHANUNAVAIL', 'CTOUT-CONGESTION']
    # EVENTOS_TRANSFER_FAIL = EVENTOS_BT_NO_CONNECT + ['CAMPT-FAIL'] + EVENTOS_CT_NO_CONNECT + \
    #     EVENTOS_BTOUT_NO_CONNECT

    objects = LlamadaLogManager()

    time = models.DateTimeField(db_index=True)
    callid = models.CharField(db_index=True, max_length=32, blank=True, null=True)
    campana_id = models.IntegerField(db_index=True, blank=True, null=True)
    tipo_campana = models.IntegerField(blank=True, null=True)
    tipo_llamada = models.IntegerField(blank=True, null=True)
    agente_id = models.IntegerField(db_index=True, blank=True, null=True)
    event = models.CharField(max_length=32, blank=True, null=True)
    numero_marcado = models.CharField(max_length=128, blank=True, null=True)
    contacto_id = models.IntegerField(db_index=True, blank=True, null=True)
    bridge_wait_time = models.IntegerField(blank=True, null=True)
    duracion_llamada = models.IntegerField(blank=True, null=True)
    archivo_grabacion = models.CharField(max_length=100, blank=True, null=True)

    # campos sólo para algunos logs transferencias
    agente_extra_id = models.IntegerField(db_index=True, blank=True, null=True)
    campana_extra_id = models.IntegerField(
        db_index=True, blank=True, null=True)
    numero_extra = models.CharField(max_length=128, blank=True, null=True)

    def __str__(self):
        return "Log de llamada con fecha {0} con id de campaña {1} con id de agente {2} " \
               "con el evento {3} duración {4}".format(self.time, self.campana_id,
                                                       self.agente_id, self.event,
                                                       self.duracion_llamada)

    def delta_inicio(self):
        delta = 0
        if self.duracion_llamada > 0:
            delta += self.duracion_llamada
        if self.bridge_wait_time > 0:
            delta += self.bridge_wait_time
        return delta

    @property
    def str_dia_grabacion(self):
        dia_grabacion = fecha_local(self.time - timedelta(seconds=self.delta_inicio()))
        return dia_grabacion.strftime("%Y-%m-%d")

    @property
    def url_archivo_grabacion(self):
        filename = "/".join([crear_segmento_grabaciones_url(),
                             self.str_dia_grabacion,
                             self.archivo_grabacion])
        return filename + '.' + settings.MONITORFORMAT

    @property
    def url_archivo_grabacion_url_encoded(self):
        # TODO: Refactorizar junto con url_archivo_grabacion para eliminar duplicidad de código
        filename = "/".join([crear_segmento_grabaciones_url(),
                             self.str_dia_grabacion,
                             urllib.parse.quote(self.archivo_grabacion)])
        return filename + '.' + settings.MONITORFORMAT

    @property
    def campana(self):
        return Campana.objects.get(id=self.campana_id)

    @property
    def tipo_llamada_show(self):
        switcher = {
            1: _('Llamada manual'),
            2: _('Llamada dialer'),
            3: _('Llamada entrante'),
            4: _('Llamada preview'),
            6: _('Llamada click2call'),
            8: _('Llamada transferencia interna'),
            9: _('Llamada transferencia externa')
        }
        return switcher.get(self.tipo_llamada, None)

    @property
    def agente(self):
        return AgenteProfile.objects.get(id=self.agente_id)


class ActividadAgenteLogManager(models.Manager):
    """
    Manager de actividadAgenteLog
    """

    def obtener_tiempos_event_agentes(self, eventos, fecha_desde, fecha_hasta,
                                      agentes):

        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        result = ActividadAgenteLog.objects.values_list('agente_id', 'time', 'event', 'pausa_id') \
                                           .filter(time__gte=fecha_desde, time__lte=fecha_hasta) \
                                           .filter(event__in=eventos) \
                                           .filter(agente_id__in=agentes) \
                                           .order_by('agente_id', '-time')

        return result

    def obtener_pausas_por_agente_fechas_pausa(self, fecha_desde,
                                               fecha_hasta, agente_id):
        """Devuelve todas las pausas del agente por una pausa en particular"""
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)
        try:
            es_evento_pausa = Q(event__in=['PAUSEALL', 'UNPAUSEALL'])
            es_evento_sesion = Q(event__in=ActividadAgenteLog.EVENTOS_LOGOUT)
            return self.filter(agente_id=agente_id, time__range=(fecha_desde, fecha_hasta)).filter(
                es_evento_pausa | es_evento_sesion).order_by('-time')

        except ActividadAgenteLog.DoesNotExist:
            raise (SuspiciousOperation(_("No se encontraron pausas ")))


class ActividadAgenteLog(models.Model):
    """
    Define la estructura de un evento de log de cola relacionado con la actividad de un agente
    """
    PAUSE = 'PAUSEALL'
    UNPAUSE = 'UNPAUSEALL'
    SESSION_LOGIN = 'SESSION_LOGIN'
    SESSION_LOGOUT = 'SESSION_LOGOUT'
    # deprecated: use SESSION_LOGIN for new code; legacy data still uses ADDMEMBER
    LOGIN = 'ADDMEMBER'
    # deprecated: use SESSION_LOGOUT for new code; legacy data still uses REMOVEMEMBER
    LOGOUT = 'REMOVEMEMBER'

    EVENTOS_LOGIN = frozenset([SESSION_LOGIN, LOGIN])
    EVENTOS_LOGOUT = frozenset([SESSION_LOGOUT, LOGOUT])

    objects = ActividadAgenteLogManager()

    time = models.DateTimeField(auto_now_add=True, db_index=True)
    agente_id = models.IntegerField(db_index=True, blank=True, null=True)
    event = models.CharField(max_length=32, blank=True, null=True)
    pausa_id = models.CharField(max_length=128, blank=True, null=True)

    def __str__(self):
        return "Log de actividad agente con fecha {0} para agente de id {1} con el evento {2} " \
               "con id de pausa {3}".format(self.time, self.agente_id,
                                            self.event, self.pausa_id)


class TransferenciaAEncuestaLog(models.Model):
    """
    Registro de transferencia a una encuesta
    """
    time = models.DateTimeField(db_index=True, auto_now_add=True)
    agente_id = models.IntegerField(db_index=True, blank=True, null=True)
    campana_id = models.IntegerField(db_index=True, blank=True, null=True)
    encuesta_id = models.IntegerField(db_index=True, blank=True, null=True)
    callid = models.CharField(db_index=True, max_length=32, blank=True, null=True)


class AnalisisSentimiento(models.Model):
    """
    Registro de analis de sentimientos por callid
    """
    time = models.DateTimeField(db_index=True, auto_now_add=True)
    callid = models.CharField(max_length=32, unique=True)
    result = models.CharField(max_length=32, null=True, blank=True)
    url_audio = models.TextField(null=True, blank=True)
    url_transcription = models.TextField(null=True, blank=True)


class SpeechAnalysis(models.Model):
    EMPTY = 0
    PROCESSING = 1
    COMPLETED = 2
    ERROR = 3
    STATUS_CHOICES = (
        (EMPTY, _('Vacío')),
        (PROCESSING, _('Procesando')),
        (COMPLETED, _('Finalizado')),
        (ERROR, _('Error')),
    )
    time = models.DateTimeField(db_index=True, auto_now=True)
    callid = models.CharField(max_length=32, unique=True)
    transcription_status = models.SmallIntegerField(choices=STATUS_CHOICES, default=EMPTY)
    transcription_file = models.CharField(max_length=100, blank=True, null=True)
    sentiment_status = models.SmallIntegerField(choices=STATUS_CHOICES, default=EMPTY)
    sentiment_file = models.CharField(max_length=100, blank=True, null=True)
    qa_status = models.SmallIntegerField(choices=STATUS_CHOICES, default=EMPTY)
    qa_file = models.CharField(max_length=100, blank=True, null=True)

    def as_dict(self):
        data = model_to_dict(self)
        data['time'] = self.time.isoformat()
        return data
    # TODO: Agregar forma de obtener el path para descargar los archivos?


class LlamadaResumenManager(models.Manager):

    def obtener_tiempo_llamadas_agente(self, eventos, fecha_desde, fecha_hasta, agentes):
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        result = LlamadaResumen.objects.values_list('agente_id') \
                                   .annotate(sum=Sum('duracion_segundos')) \
                                   .filter(fecha_fin__gte=fecha_desde, fecha_fin__lte=fecha_hasta) \
                                   .filter(event__in=eventos) \
                                   .filter(agente_id__in=agentes) \
                                   .exclude(campana_id=0) \
                                   .order_by('agente_id')

        return result

    def obtener_count_evento_agente(self, eventos, fecha_desde, fecha_hasta, agentes):
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        cursor = connection.cursor()
        sql = """select agente_id, count(*)
                 from reportes_app_llamada_resumen where fecha_fin between %(fecha_desde)s and
                 %(fecha_hasta)s and event = ANY(%(eventos)s) and agente_id = ANY(%(agentes)s)
                 AND NOT campana_id = '0'
                 GROUP BY agente_id order by agente_id
        """
        params = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'eventos': eventos,
            'agentes': agentes,
        }

        cursor.execute(sql, params)
        values = cursor.fetchall()
        return values

    def obtener_agentes_campanas_total(self, eventos, fecha_desde, fecha_hasta, agentes,
                                       campanas):
        """
        Query que sumariza por agente y campaña la cantidad y duración de
        llamadas para los eventos indicados.
        """

        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        cursor = connection.cursor()
        sql = """select agente_id, campana_id, SUM(duracion_segundos::numeric), Count(*)
                 from reportes_app_llamada_resumen where fecha_fin between %(fecha_desde)s and
                 %(fecha_hasta)s and event = ANY(%(eventos)s) and agente_id = ANY(%(agentes)s)
                 and campana_id = ANY(%(campanas)s) GROUP BY agente_id, campana_id order by
                 agente_id, campana_id
        """
        params = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'eventos': eventos,
            'agentes': agentes,
            'campanas': [campana.id for campana in campanas],
        }

        cursor.execute(sql, params)
        values = cursor.fetchall()
        return values

    def obtener_count_agente(self):
        try:
            return self.values('agente_id').annotate(
                cantidad=Count('agente_id')).order_by('agente_id')
        except LlamadaResumen.DoesNotExist:
            raise (SuspiciousOperation(_("No se encontraron llamadas ")))

    def obtener_tiempo_llamada_agente(self, eventos, fecha_desde, fecha_hasta, agente_id):
        """devuelve la duracion de llamadas y fecha"""
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        try:
            return self.filter(agente_id=agente_id, event__in=eventos,
                               fecha_fin__range=(fecha_desde, fecha_hasta))
        except LlamadaResumen.DoesNotExist:
            raise (SuspiciousOperation(_("No se encontraron llamadas ")))

    def obtener_count_evento_agente_agrupado_fecha(self, eventos, fecha_desde,
                                                   fecha_hasta, agente_id):
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        return LlamadaResumen.objects.filter(event__in=eventos, agente_id=agente_id,
                                         fecha_fin__range=(fecha_desde, fecha_hasta)).exclude(
            campana_id=0).annotate(
                fecha=TruncDate('fecha_fin')).values('fecha').annotate(cantidad=Count('fecha'))

    def obtener_historico_llamadas_del_dia(self, agente_id, fecha):
        fecha_desde = datetime_hora_minima_dia(fecha)
        fecha_hasta = datetime_hora_maxima_dia(fecha)
        return self.filter(agente_id=agente_id,
                           fecha_fin__gte=fecha_desde, fecha_fin__lte=fecha_hasta,
                           event__in=LlamadaResumen.EVENTOS_FIN_CONEXION + LlamadaResumen.EVENTOS_REJECT
                           + list(LlamadaResumen.EVENTOS_NO_CONEXION))

    def obtener_evento_hold_fecha(self, eventos, fecha_desde, fecha_hasta, agente_id):
        """devuelve el hold"""
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)

        try:
            return self.filter(agente_id=agente_id, event__in=eventos,
                               fecha_fin__range=(fecha_desde, fecha_hasta))
        except LlamadaResumen.DoesNotExist:
            raise (SuspiciousOperation(_("No se encontraron holds ")))

    def obtener_cantidades_de_transferencias_recibidas(
            self, fecha_inicial, fecha_final, agentes, campanas_ids):
        """
            Contabiliza Transferencias directas A AGENTE. Agrupa por agente y por campaña
        """
        resultados = self.filter(
            fecha_fin__range=(fecha_inicial, fecha_final),
            agente_id__in=agentes, campana_id__in=campanas_ids,
            event__in=['BT-ANSWER', 'CT-ACCEPT']).values('agente_id', 'campana_id').annotate(
                cant=Count('id')).order_by('agente_id', 'campana_id')
        cantidades = {agente_id: {} for agente_id in agentes}
        for resultado in resultados:
            cantidades[resultado['agente_id']][resultado['campana_id']] = resultado['cant']
        return cantidades

    def cantidad_llamadas_rechazadas_fecha(self, agente_id, fecha_inferior, fecha_superior):
        fecha_desde = datetime_hora_minima_dia(fecha_inferior)
        fecha_hasta = datetime_hora_maxima_dia(fecha_superior)
        # Nota: agente_extra_id no existe en LlamadaResumen, se usa agente_id directamente
        return self.filter(agente_id=agente_id,
                           fecha_fin__gte=fecha_desde, fecha_fin__lte=fecha_hasta,
                           event__in=LlamadaResumen.EVENTOS_REJECT).exclude(campana_id='0').count()

    def cantidad_llamadas_no_atendidas_fecha(self, agente_id, fecha_inferior, fecha_superior):
        fecha_desde = datetime_hora_minima_dia(fecha_inferior)
        fecha_hasta = datetime_hora_maxima_dia(fecha_superior)
        # Nota: agente_extra_id no existe en LlamadaResumen, se filtra por agente_id y tipo_llamada
        return self.filter(
            agente_id=agente_id,
            tipo_llamada=LlamadaResumen.LLAMADA_ENTRANTE,
            fecha_fin__gte=fecha_desde,
            fecha_fin__lte=fecha_hasta,
            event__in=LlamadaResumen.EVENTOS_REJECT).exclude(campana_id='0').count()

    def obtener_grabaciones_by_filtro(self, fecha_desde, fecha_hasta, tipo_llamada, tel_cliente,
                                      callid, id_contacto_externo, agente, campana, campanas,
                                      marcadas, duracion, gestion, calificaciones):
        """
        Método equivalente a LlamadaLog.obtener_grabaciones_by_filtro pero usando LlamadaResumen.
        """
        INCLUDED_EVENTS = ['COMPLETEAGENT', 'COMPLETEOUTNUM', 'BT-COMPLETE', 'COMPLETE-BT',
                           'CT-ANSWER', 'CT-COMPLETE', 'COMPLETE-CT',
                           'CAMPCT-COMPLETE', 'COMPLETE-CAMPCT',
                           'CAMPT-COMPLETE', 'COMPLETE-CAMPT',
                           'BTOUT-COMPLETE', 'COMPLETE-BTOUT', 'CTOUT-COMPLETE',
                           'COMPLETE-CTOUT', 'CAMPT-FAIL', 'BT-BUSY', 'BTOUT-TRY', 'CT-ABANDON',
                           'CTOUT-TRY', 'BT-TRY', 'EXIT_ANSWERED']  # Agregar EXIT_ANSWERED para omnidialer
        
        # Campañas a Filtrar:
        campanas_id = set([campana.id for campana in campanas])
        if campana:
            if campana != 'activas' and campana != 'borradas':
                campanas_id = [campana]
            else:
                for camp in campanas:
                    if (camp.estado == Campana.ESTADO_BORRADA and campana == 'activas') or \
                            (camp.estado != Campana.ESTADO_BORRADA and campana == 'borradas'):
                        campanas_id.remove(camp.id)
        
        grabaciones = self.filter(campana_id__in=campanas_id,
                                  archivo_grabacion__isnull=False,
                                  event__in=INCLUDED_EVENTS)
        
        # En LlamadaResumen usamos duracion_segundos en lugar de duracion_llamada
        grabaciones = grabaciones.filter(Q(duracion_segundos__gt=0) | Q(event='CT-ANSWER'))
        grabaciones = grabaciones.exclude(archivo_grabacion='-1')
        
        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)
            # LlamadaResumen usa fecha_fin en lugar de time
            grabaciones = grabaciones.filter(fecha_fin__range=(fecha_desde, fecha_hasta))
        
        # Calificaciones: en LlamadaResumen ya están desnormalizadas
        if calificaciones:
            grabaciones = grabaciones.filter(opcion_calificacion_id__in=calificaciones)
        
        if tipo_llamada:
            grabaciones = grabaciones.filter(tipo_llamada=tipo_llamada)
        if tel_cliente:
            grabaciones = grabaciones.filter(numero_marcado__contains=tel_cliente)
        if callid:
            grabaciones = grabaciones.filter(callid=callid)
        if agente:
            grabaciones = grabaciones.filter(agente_id=agente.id)
        
        if duracion and duracion > 0:
            # Convertir duracion (probablemente en segundos) para comparar con duracion_segundos
            grabaciones = grabaciones.filter(duracion_segundos__gte=duracion)
        
        if id_contacto_externo:
            telefonos_contacto = Contacto.objects.values('telefono')
            telefono_id_externo = telefonos_contacto.filter(id_externo=id_contacto_externo)
            grabaciones = grabaciones.filter(
                numero_marcado__in=[t['telefono'] for t in telefono_id_externo])
        
        if marcadas:
            total_grabaciones_marcadas = self.obtener_grabaciones_marcadas()
            grabaciones = grabaciones & total_grabaciones_marcadas
        
        if gestion:
            # En LlamadaResumen, gestion se puede filtrar por opcion_calificacion_tipo
            # Asumiendo que gestion = True significa que tiene calificación de gestión
            grabaciones = grabaciones.exclude(opcion_calificacion_id__isnull=True)
        
        # Ordenar por fecha_fin en lugar de time
        return grabaciones.order_by('-fecha_fin')

    def obtener_grabaciones_marcadas(self):
        """
        Método equivalente para obtener grabaciones marcadas usando LlamadaResumen.
        """
        marcaciones = list(GrabacionMarca.objects.values_list('callid', flat=True))
        return self.filter(callid__in=marcaciones, archivo_grabacion__isnull=False,
                           duracion_segundos__gt=0).exclude(archivo_grabacion='-1')


class LlamadaResumen(models.Model):
    """
    Modelo para acceder a la tabla de resumen de llamadas (Fact Table)
    desnormalizada para optimizar consultas de reportes sin JOINs.
    Esta tabla se usa cuando OML_DIALER_ENGINE=omnidialer
    """
    # Constantes de tipos de llamada (compatibilidad con LlamadaLog)
    LLAMADA_MANUAL = 1
    LLAMADA_DIALER = 2
    LLAMADA_ENTRANTE = 3
    LLAMADA_PREVIEW = 4
    LLAMADA_CLICK2CALL = 6
    LLAMADA_TRANSFER_INTERNA = 8
    LLAMADA_TRANSFER_EXTERNA = 9

    TIPOS_LLAMADAS_SALIENTES = (
        LLAMADA_MANUAL, LLAMADA_PREVIEW, LLAMADA_CLICK2CALL)

    # Constantes de eventos (compatibilidad con LlamadaLog)
    EVENTOS_NO_CONTACTACION = ('NOANSWER', 'CANCEL', 'BUSY', 'CHANUNAVAIL', 'FAIL', 'OTHER',
                               'BLACKLIST', 'CONGESTION', 'NONDIALPLAN')

    EVENTOS_NO_DIALOGO = ('ABANDON', 'EXITWITHTIMEOUT', 'AMD', 'EXIT_AMD', 'ABANDONWEL',
                          'EXIT_ABANDON', 'EXIT_TIMEOUT', 'EXIT_HANDOFF_ABANDON', 'EXIT_HANDOFF_TIMEOUT')

    EVENTOS_NO_CONEXION = EVENTOS_NO_CONTACTACION + EVENTOS_NO_DIALOGO

    # Eventos que indican que no se pudo completar una transferencia
    EVENTOS_NO_CONEXION_TRANSFER = [
        'BT-BUSY', 'BT-CANCEL', 'BT-CHANUNAVAIL', 'BT-CONGESTION', 'BT-NOANSWER', 'BT-ABANDON',
        'CT-DISCARD', 'CT-BUSY', 'CT-CANCEL', 'CT-CHANUNAVAIL', 'CT-CONGESTION',
        'CAMPCT-DISCARD', 'CAMPCT-BUSY', 'CAMPCT-CANCEL', 'CAMPCT-CHANUNAVAIL', 'CAMPCT-CONGESTION',
        'BTOUT-BUSY', 'BTOUT-CANCEL', 'BTOUT-CONGESTION', 'BTOUT-CHANUNAVAIL', 'BTOUT-ABANDON',
        'CTOUT-DISCARD', 'CTOUT-BUSY', 'CTOUT-CANCEL', 'CTOUT-CHANUNAVAIL', 'CTOUT-CONGESTION'
    ]

    # Eventos que marcan el fin de la conexion con un agente. (Puede ser por conectar con otro)
    EVENTOS_FIN_CONEXION = ['COMPLETEAGENT', 'COMPLETEOUTNUM',
                            'BT-TRY', 'COMPLETE-BT',
                            'CAMPT-COMPLETE', 'CAMPT-FAIL', 'COMPLETE-CAMPT',
                            'CT-COMPLETE', 'COMPLETE-CT', 'ABANDON-CT',
                            'CAMPCT-COMPLETE', 'COMPLETE-CAMPCT', 'ABANDON-CAMPCT',
                            'BTOUT-TRY',
                            'CTOUT-COMPLETE', 'EXIT_ANSWERED']  # Agregar EXIT_ANSWERED para omnidialer

    # Marcan el fin de la conexion por una transferencia para el agente original
    EVENTOS_FIN_CONEXION_POR_TRANSFER = ['BT-TRY', 'BTOUT-TRY',
                                         'CAMPT-COMPLETE', 'CAMPT-FAIL',
                                         'CT-COMPLETE', 'CAMPCT-COMPLETE', 'CTOUT-COMPLETE']

    EVENTOS_INICIO_CONEXION = ['CONNECT', 'ANSWER',
                               'BT-ANSWER', 'CT-ACCEPT']  # Con id_agente

    # eventos inicio conexion de una llamada
    # (No incluye valores de eventos de transferencias si ocurren luego)
    EVENTOS_INICIO_CONEXION_AGENTE = ['CONNECT', 'ANSWER']  # Con id_agente

    # eventos fin conexion de una llamada
    # (No incluye valores de eventos de transferencias si ocurren luego)
    EVENTOS_FIN_CONEXION_AGENTE = ['COMPLETEAGENT', 'COMPLETEOUTNUM']  # Con id_agente

    # eventos de hold en una llamada
    EVENTOS_HOLD = ['HOLD', 'UNHOLD']

    # eventos de no atendida una llamada
    EVENTOS_REJECT = ['RINGNOANSWER']

    id = models.BigAutoField(primary_key=True)
    callid = models.CharField(max_length=64, unique=True, db_index=True)

    # Negocio
    campana_id = models.IntegerField(blank=True, null=True, db_index=True)
    tipo_campana = models.IntegerField(blank=True, null=True)
    tipo_llamada = models.IntegerField(blank=True, null=True)
    agente_id = models.IntegerField(blank=True, null=True, db_index=True)
    contacto_id = models.IntegerField(blank=True, null=True)
    numero_marcado = models.CharField(max_length=128, blank=True, null=True)
    
    # Tiempos
    fecha_inicio = models.DateTimeField(blank=True, null=True)
    fecha_fin = models.DateTimeField(blank=True, null=True, db_index=True)
    duracion_segundos = models.DecimalField(max_digits=10, decimal_places=3, blank=True, null=True)
    bridge_wait_time = models.DecimalField(max_digits=10, decimal_places=3, blank=True, null=True)
    
    # Evento
    event = models.CharField(max_length=32, blank=True, null=True)
    archivo_grabacion = models.CharField(max_length=256, blank=True, null=True)
    es_transferencia = models.BooleanField(default=False)
    
    # Calificación
    calificacion_id = models.IntegerField(blank=True, null=True, db_index=True)
    opcion_calificacion_id = models.IntegerField(blank=True, null=True)
    opcion_calificacion_nombre = models.CharField(max_length=100, blank=True, null=True)
    opcion_calificacion_tipo = models.IntegerField(blank=True, null=True)
    subcalificacion = models.CharField(max_length=200, blank=True, null=True)
    es_venta = models.BooleanField(default=False, db_index=True)
    
    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = LlamadaResumenManager()

    node_id = models.CharField(max_length=64, db_index=True, null=True, blank=True)
    tenant_id = models.CharField(max_length=64, db_index=True, null=True, blank=True)
    
    # Hangup trigger: quién corta la llamada
    HANGUP_TRIGGER_AGENT = 'AGENT'
    HANGUP_TRIGGER_EXTERNAL = 'EXTERNAL'
    HANGUP_TRIGGER_OTHER = 'OTHER'
    
    HANGUP_TRIGGER_CHOICES = (
        (HANGUP_TRIGGER_AGENT, 'AGENT'),
        (HANGUP_TRIGGER_EXTERNAL, 'EXTERNAL'),
        (HANGUP_TRIGGER_OTHER, 'OTHER'),
    )
    
    hangup_trigger = models.CharField(
        max_length=16,
        choices=HANGUP_TRIGGER_CHOICES,
        blank=True,
        null=True,
        help_text='Indica quién cortó la llamada: AGENT (agente), EXTERNAL (cliente/externo), OTHER (sistema/otro)'
    )
    
    def __str__(self):
        return "Resumen de llamada con fecha {0} con id de campaña {1} con id de agente {2} " \
               "con el evento {3} duración {4}".format(self.fecha_fin, self.campana_id,
                                                       self.agente_id, self.event,
                                                       self.duracion_segundos)

    def delta_inicio(self):
        """Compatibilidad con LlamadaLog para cálculo de delta"""
        delta = 0
        if self.duracion_segundos and self.duracion_segundos > 0:
            delta += float(self.duracion_segundos)
        if self.bridge_wait_time and self.bridge_wait_time > 0:
            delta += float(self.bridge_wait_time)
        return delta

    @property
    def time(self):
        """
        Propiedad de compatibilidad: LlamadaLog usa 'time', LlamadaResumen usa 'fecha_fin'
        """
        return self.fecha_fin

    @property
    def duracion_llamada(self):
        """
        Propiedad de compatibilidad: LlamadaLog usa 'duracion_llamada' (int), 
        LlamadaResumen usa 'duracion_segundos' (Decimal)
        """
        if self.duracion_segundos:
            return int(float(self.duracion_segundos))
        return None

    @property
    def url_archivo_grabacion(self):
        """
        Compatibilidad con LlamadaLog para URL de grabación.
        En LlamadaResumen, archivo_grabacion ya viene con formato completo como está en S3: '20260102/1767378633.10.mp3'
        El API espera el filename tal cual está en S3, sin agregar fechas adicionales.
        """
        if not self.archivo_grabacion or self.archivo_grabacion == '-1':
            return None
        
        # Si archivo_grabacion ya incluye fecha y extensión (formato: YYYYMMDD/filename.mp3)
        # que es exactamente como está en S3, usarlo directamente
        if '/' in self.archivo_grabacion and self.archivo_grabacion.endswith('.mp3'):
            # El archivo ya está en el formato correcto para S3: '20260102/1767379374.26.mp3'
            # Solo necesitamos agregar el / al inicio para el parámetro filename
            path_archivo = f"/{self.archivo_grabacion}"
            return crear_segmento_grabaciones_url() + path_archivo
        else:
            # Si no tiene el formato esperado (sin fecha o sin extensión), usar lógica de LlamadaLog
            dia_grabacion = fecha_local(self.fecha_fin - timedelta(seconds=self.delta_inicio()))
            path_archivo = f"/{dia_grabacion.strftime('%Y-%m-%d')}/{self.archivo_grabacion}"
            # Agregar extensión si no la tiene
            if not self.archivo_grabacion.endswith('.' + settings.MONITORFORMAT):
                path_archivo += '.' + settings.MONITORFORMAT
            return crear_segmento_grabaciones_url() + path_archivo

    @property
    def url_archivo_grabacion_url_encoded(self):
        """
        Compatibilidad con LlamadaLog para URL codificada de grabación.
        En LlamadaResumen, archivo_grabacion ya viene con formato completo como está en S3: '20260102/1767378633.10.mp3'
        El API espera el filename tal cual está en S3, codificado para URL.
        """
        if not self.archivo_grabacion or self.archivo_grabacion == '-1':
            return None
        
        # Si archivo_grabacion ya incluye fecha y extensión (formato: YYYYMMDD/filename.mp3)
        # que es exactamente como está en S3, codificarlo y usarlo directamente
        if '/' in self.archivo_grabacion and self.archivo_grabacion.endswith('.mp3'):
            # El archivo ya está en el formato correcto para S3: '20260102/1767379374.26.mp3'
            # Codificar la ruta completa para URL
            archivo_codificado = urllib.parse.quote(self.archivo_grabacion, safe='/')
            path_archivo = f"/{archivo_codificado}"
            return crear_segmento_grabaciones_url() + path_archivo
        else:
            # Si no tiene el formato esperado (sin fecha o sin extensión), usar lógica de LlamadaLog
            dia_grabacion = fecha_local(self.fecha_fin - timedelta(seconds=self.delta_inicio()))
            archivo_codificado = urllib.parse.quote(self.archivo_grabacion)
            path_archivo = f"/{dia_grabacion.strftime('%Y-%m-%d')}/{archivo_codificado}"
            # Agregar extensión si no la tiene
            if not self.archivo_grabacion.endswith('.' + settings.MONITORFORMAT):
                path_archivo += '.' + settings.MONITORFORMAT
            return crear_segmento_grabaciones_url() + path_archivo

    @property
    def campana(self):
        """Compatibilidad con LlamadaLog"""
        if self.campana_id:
            return Campana.objects.get(id=self.campana_id)
        return None

    @property
    def tipo_llamada_show(self):
        """Compatibilidad con LlamadaLog"""
        switcher = {
            1: _('Llamada manual'),
            2: _('Llamada dialer'),
            3: _('Llamada entrante'),
            4: _('Llamada preview'),
            6: _('Llamada click2call'),
            8: _('Llamada transferencia interna'),
            9: _('Llamada transferencia externa')
        }
        return switcher.get(self.tipo_llamada, None)

    @property
    def agente(self):
        """Compatibilidad con LlamadaLog"""
        if self.agente_id:
            return AgenteProfile.objects.get(id=self.agente_id)
        return None

    @property
    def numero_extra(self):
        """
        Compatibilidad con LlamadaLog para transferencias.
        En LlamadaResumen no tenemos este campo, retornamos '-1' por compatibilidad.
        """
        return '-1'
    
    class Meta:
        db_table = 'reportes_app_llamada_resumen'
        managed = False  # La tabla ya existe, no la gestionamos con migrations


class TransferLog(models.Model):
    """
    Modelo para acceder a la tabla de transferencias.
    Esta tabla registra todas las transferencias de llamadas.
    """
    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(db_index=True)
    
    # Origen
    callid = models.CharField(max_length=64, db_index=True)
    leg_unique_id = models.CharField(max_length=64, blank=True, null=True)
    contacto_id = models.IntegerField(blank=True, null=True)
    campana_id_origen = models.IntegerField(blank=True, null=True)
    agente_origen_id = models.IntegerField(blank=True, null=True, db_index=True)
    
    # Lógica Transferencia
    initiated_by = models.CharField(max_length=16, default='AGENTE')
    transfer_type = models.CharField(max_length=16)
    
    # Destino
    numero_extra = models.CharField(max_length=64, blank=True, null=True)
    target_agent_id = models.IntegerField(blank=True, null=True)
    target_campaign_id = models.IntegerField(blank=True, null=True)
    
    # Resultado Técnico
    new_leg_unique_id = models.CharField(max_length=64, blank=True, null=True)
    resultado = models.CharField(max_length=32, default='INIT')
    sip_code = models.IntegerField(blank=True, null=True)
    sip_reason = models.CharField(max_length=64, blank=True, null=True)
    
    # Tiempos
    duration_ms = models.IntegerField(blank=True, null=True)
    talk_time = models.IntegerField(blank=True, null=True)
    
    class Meta:
        db_table = 'reportes_app_transferlog'
        managed = False  # La tabla ya existe, no la gestionamos con migrations
        indexes = [
            models.Index(fields=['callid'], name='idx_transferlog_callid'),
            models.Index(fields=['created_at'], name='idx_transferlog_created_at'),
            models.Index(fields=['agente_origen_id'], name='idx_transferlog_agente'),
        ]


class InitiationMethod(models.TextChoices):
    """Método de iniciación de la interacción (quién/origen la inició)."""
    AGENT = 'AGENT', _('Agent')
    DIALER = 'DIALER', _('Dialer')
    BOT = 'BOT', _('Bot')


class InteractionsSummaryManager(models.Manager):
    """
    Manager para InteractionsSummary con método obtener_grabaciones_by_filtro
    compatible con la búsqueda de grabaciones (grabacion/buscar) cuando
    OML_DIALER_ENGINE=omnidialer. No usa archivo_grabacion; la grabación
    se infiere como YYYY-MM-DD/interaction_id.mp3 para status EXIT_ANSWERED.
    """

    def obtener_grabaciones_by_filtro(self, fecha_desde, fecha_hasta, tipo_llamada, tel_cliente,
                                      callid, id_contacto_externo, agente, campana, campanas,
                                      marcadas, duracion, gestion, calificaciones):
        """
        Filtra interacciones con grabación (status EXIT_ANSWERED).
        Firma compatible con LlamadaResumen.obtener_grabaciones_by_filtro.
        """
        # Solo interacciones contestadas con grabación (sin campo archivo_grabacion)
        grabaciones = self.filter(status='EXIT_ANSWERED')
        grabaciones = grabaciones.filter(
            Q(total_duration__gt=0) | Q(agent_duration__gt=0)
        )

        # Campañas a filtrar (misma lógica que LlamadaResumen)
        campanas_id = set([c.id for c in campanas])
        if campana:
            if campana != 'activas' and campana != 'borradas':
                campanas_id = [campana]
            else:
                for camp in campanas:
                    if (camp.estado == Campana.ESTADO_BORRADA and campana == 'activas') or \
                            (camp.estado != Campana.ESTADO_BORRADA and campana == 'borradas'):
                        campanas_id.discard(camp.id)
        grabaciones = grabaciones.filter(campaign_id__in=campanas_id)

        if fecha_desde and fecha_hasta:
            fecha_desde = datetime_hora_minima_dia(fecha_desde)
            fecha_hasta = datetime_hora_maxima_dia(fecha_hasta)
            grabaciones = grabaciones.filter(end_time__range=(fecha_desde, fecha_hasta))

        if calificaciones:
            historicals = HistoricalCalificacionCliente.objects.filter(
                opcion_calificacion_id__in=calificaciones
            )
            if fecha_desde and fecha_hasta:
                historicals = historicals.filter(modified__range=(fecha_desde, fecha_hasta))
            call_ids = list(historicals.values_list('callid', flat=True))
            grabaciones = grabaciones.filter(interaction_id__in=call_ids)

        # tipo_llamada: 1=manual(AGENT), 2/4=dialer/preview(DIALER), 3=entrante(INBOUND), 6=click2call(AGENT)
        if tipo_llamada:
            if tipo_llamada == 3:
                grabaciones = grabaciones.filter(direction='INBOUND')
            elif tipo_llamada in (1, 6):
                grabaciones = grabaciones.filter(initiation_method=InitiationMethod.AGENT)
            elif tipo_llamada in (2, 4):
                grabaciones = grabaciones.filter(initiation_method=InitiationMethod.DIALER)

        if tel_cliente:
            grabaciones = grabaciones.filter(
                Q(destination_address__contains=tel_cliente) |
                Q(source_address__contains=tel_cliente)
            )
        if callid:
            grabaciones = grabaciones.filter(interaction_id=callid)
        if agente:
            grabaciones = grabaciones.filter(agent_id=agente.id)
        if duracion and duracion > 0:
            grabaciones = grabaciones.filter(total_duration__gte=duracion)
        if id_contacto_externo:
            telefonos_contacto = Contacto.objects.filter(
                id_externo=id_contacto_externo
            ).values_list('telefono', flat=True)
            grabaciones = grabaciones.filter(
                Q(destination_address__in=list(telefonos_contacto)) |
                Q(source_address__in=list(telefonos_contacto))
            )
        if marcadas:
            total_grabaciones_marcadas = self.obtener_grabaciones_marcadas()
            grabaciones = grabaciones.filter(
                interaction_id__in=total_grabaciones_marcadas.values_list('interaction_id', flat=True)
            )
        if gestion:
            calificaciones_gestion = CalificacionCliente.obtener_califs_gestion_campanas(
                campanas, fecha_desde, fecha_hasta
            )
            callids_gestion = list(calificaciones_gestion.values_list('callid', flat=True))
            grabaciones = grabaciones.filter(interaction_id__in=callids_gestion)

        return grabaciones.order_by('-end_time')

    def obtener_grabaciones_marcadas(self):
        """Interacciones marcadas para grabación (callid = interaction_id en GrabacionMarca)."""
        marcaciones = list(GrabacionMarca.objects.values_list('callid', flat=True))
        return self.filter(
            interaction_id__in=marcaciones,
            status='EXIT_ANSWERED',
            total_duration__gt=0,
        )

    def get_datos_grabacion(self, callid):
        """
        Devuelve (date_folder, source_file) para la ruta de grabación YYYY-MM-DD/interaction_id.mp3,
        o (None, None) si no hay registro válido. Usado por la API de análisis/transcripción.
        """
        obj = self.filter(
            interaction_id=callid,
            status='EXIT_ANSWERED',
            end_time__isnull=False,
        ).first()
        if not obj:
            return None, None
        date_folder = localtime(obj.end_time).strftime('%Y-%m-%d')
        source_file = f'{obj.interaction_id}.mp3'
        return date_folder, source_file


class InteractionsSummary(models.Model):
    """
    Modelo para la tabla public.interactions_summary (resumen omnicanal e KPIs).
    Tabla creada por la migración 0012; el ORM no gestiona el esquema.
    """
    id = models.BigAutoField(primary_key=True)
    interaction_id = models.CharField(max_length=64, unique=True)
    tenant_id = models.CharField(max_length=64)
    node_id = models.CharField(max_length=64, null=True, blank=True)
    campaign_id = models.IntegerField(null=True, blank=True)
    channel_type = models.CharField(max_length=16)
    direction = models.CharField(max_length=16, default='INBOUND')
    initiation_method = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        choices=InitiationMethod.choices,
    )
    status = models.CharField(max_length=32)
    hangup_cause = models.CharField(max_length=32, null=True, blank=True)
    source_address = models.CharField(max_length=256, null=True, blank=True)
    destination_address = models.CharField(max_length=256, null=True, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    total_duration = models.DecimalField(max_digits=10, decimal_places=3, default=0, null=True, blank=True)
    bot_duration = models.DecimalField(max_digits=10, decimal_places=3, default=0, null=True, blank=True)
    wait_conn_duration = models.DecimalField(max_digits=10, decimal_places=3, default=0, null=True, blank=True)
    agent_duration = models.DecimalField(max_digits=10, decimal_places=3, default=0, null=True, blank=True)
    agent_id = models.IntegerField(null=True, blank=True)
    qualification_id = models.IntegerField(null=True, blank=True, db_column='disposition_id')
    customer_id = models.IntegerField(null=True, blank=True)
    is_sale = models.BooleanField(default=False, db_column='outcome')
    is_transferred = models.BooleanField(default=False)
    transfer_count = models.IntegerField(default=0)
    channel_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    objects = InteractionsSummaryManager()

    class Meta:
        db_table = 'interactions_summary'
        managed = False  # La tabla la crea la migración 0012
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(initiation_method__isnull=True) |
                    Q(initiation_method__in=list(InitiationMethod.values))
                ),
                name='interactions_summary_initiation_method_valid',
            ),
        ]

    # --- Propiedades de compatibilidad para vista de grabaciones (grabacion/buscar) ---
    # Permiten usar las mismas plantillas que LlamadaResumen/LlamadaLog.
    # Grabación inferida como YYYY-MM-DD/interaction_id.mp3 (no existe archivo_grabacion).

    @property
    def callid(self):
        """Compatibilidad: interaction_id como callid."""
        return self.interaction_id

    @property
    def time(self):
        """Compatibilidad: end_time como time."""
        return self.end_time

    @property
    def fecha_fin(self):
        """Compatibilidad: end_time como fecha_fin."""
        return self.end_time

    @property
    def contacto_id(self):
        """Compatibilidad: customer_id como contacto_id."""
        return self.customer_id

    @property
    def campana_id(self):
        """Compatibilidad: campaign_id (campana_id es el nombre en templates)."""
        return self.campaign_id

    @property
    def duracion_llamada(self):
        """Compatibilidad: total_duration como entero."""
        if self.total_duration is not None:
            return int(float(self.total_duration))
        return None

    @property
    def duracion_segundos(self):
        """Compatibilidad: total_duration como duracion_segundos."""
        return self.total_duration

    @property
    def numero_marcado(self):
        """Compatibilidad: número según dirección (outbound=destination, inbound=source)."""
        if self.direction == 'OUTBOUND' and self.destination_address:
            return self.destination_address
        if self.source_address:
            return self.source_address
        return self.destination_address or ''

    @property
    def tipo_llamada_show(self):
        """Compatibilidad: texto legible según initiation_method y direction."""
        if self.direction == 'INBOUND':
            return _('Llamada entrante')
        if self.initiation_method == InitiationMethod.AGENT:
            return _('Llamada manual')
        if self.initiation_method == InitiationMethod.DIALER:
            return _('Llamada dialer')
        if self.initiation_method == InitiationMethod.BOT:
            return _('Llamada bot')
        return _('Llamada')  # fallback

    @property
    def agente(self):
        """Compatibilidad: AgenteProfile por agent_id."""
        if not self.agent_id:
            return None
        try:
            return AgenteProfile.objects.get(id=self.agent_id)
        except AgenteProfile.DoesNotExist:
            return None

    @property
    def campana(self):
        """Compatibilidad: Campana por campaign_id."""
        if not self.campaign_id:
            return None
        try:
            return Campana.objects.get(id=self.campaign_id)
        except Campana.DoesNotExist:
            return None

    @property
    def url_archivo_grabacion(self):
        """
        URL de grabación inferida: YYYY-MM-DD/interaction_id.mp3 (no existe archivo_grabacion).
        Ubicación en bucket: YYYY-MM-DD/callid.mp3 con callid = interaction_id.
        """
        if not self.end_time:
            return None
        dia_grabacion = fecha_local(self.end_time)
        path_archivo = f"/{dia_grabacion.strftime('%Y-%m-%d')}/{self.interaction_id}.mp3"
        return crear_segmento_grabaciones_url() + path_archivo

    @property
    def url_archivo_grabacion_url_encoded(self):
        """URL de grabación codificada para uso en query string (YYYY-MM-DD/interaction_id.mp3)."""
        if not self.end_time:
            return None
        dia_grabacion = fecha_local(self.end_time)
        path = f"{dia_grabacion.strftime('%Y-%m-%d')}/{self.interaction_id}.mp3"
        archivo_codificado = urllib.parse.quote(path, safe='/')
        return crear_segmento_grabaciones_url() + "/" + archivo_codificado


class InteractionJourney(models.Model):
    """
    Modelo para la tabla public.interaction_journey (trazabilidad paso a paso del customer journey).
    Tabla creada por la migración 0012; el ORM no gestiona el esquema.
    """
    id = models.BigAutoField(primary_key=True)
    interaction_id = models.CharField(max_length=64)
    sequence_number = models.IntegerField()
    node_type = models.CharField(max_length=32)
    node_name = models.CharField(max_length=128, null=True, blank=True)
    action = models.CharField(max_length=32, null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'interaction_journey'
        managed = False  # La tabla la crea la migración 0012


class InteractionTransfers(models.Model):
    """
    Modelo para la tabla public.interaction_transfers (transferencias vinculadas al journey).
    Tabla creada por la migración 0012; el ORM no gestiona el esquema.
    """
    id = models.BigAutoField(primary_key=True)
    interaction_id = models.CharField(max_length=64)
    journey_entry = models.ForeignKey(
        'reportes_app.InteractionJourney',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='journey_entry_id',
        related_name='transfers',
    )
    source_agent_id = models.IntegerField(null=True, blank=True)
    source_channel = models.CharField(max_length=128, null=True, blank=True)
    destination_target = models.CharField(max_length=128)
    destination_type = models.CharField(max_length=32, null=True, blank=True)
    destination_agent_id = models.IntegerField(null=True, blank=True)
    destination_campaign_id = models.IntegerField(null=True, blank=True)
    destination_external_endpoint = models.CharField(max_length=128, null=True, blank=True)
    transfer_type = models.CharField(max_length=20, null=True, blank=True)
    status = models.CharField(max_length=20, null=True, blank=True)
    fail_reason = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    talk_time_after = models.DecimalField(
        max_digits=10, decimal_places=3, default=0, null=True, blank=True
    )

    class Meta:
        db_table = 'interaction_transfers'
        managed = False  # La tabla la crea la migración 0012


def q_interaction_transfers_campaign_blind_consult():
    """
    Q para InteractionTransfers: solo transferencias OK hacia otra campaña con
    destination_type CAMPAIGN y mecánica BLIND o CONSULT (excluye AGENT, EXTERNAL, ATTENDED, etc.).
    Compartido entre reporte centro de contacto y estadísticas de campaña V2.
    """
    return (
        Q(destination_campaign_id__isnull=False)
        & Q(status__iexact='OK')
        & Q(destination_type__iexact='CAMPAIGN')
        & (Q(transfer_type__iexact='BLIND') | Q(transfer_type__iexact='CONSULT'))
    )


class AgentActivityEventV2(models.Model):
    """Eventos de actividad de agente (login, logout, estados)."""

    class EventType(models.TextChoices):
        SESSION_LOGIN = 'SESSION_LOGIN', 'SESSION_LOGIN'
        SESSION_LOGOUT = 'SESSION_LOGOUT', 'SESSION_LOGOUT'
        STATE_READY = 'STATE_READY', 'STATE_READY'
        STATE_PAUSED = 'STATE_PAUSED', 'STATE_PAUSED'
        STATE_ACW = 'STATE_ACW', 'STATE_ACW'
        STATE_ON_HOLD = 'STATE_ON_HOLD', 'STATE_ON_HOLD'
        STATE_OFF_HOLD = 'STATE_OFF_HOLD', 'STATE_OFF_HOLD'

    id = models.BigAutoField(primary_key=True)
    ts = models.DateTimeField(db_index=True)
    agente_id = models.IntegerField(db_index=True)
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    pause = models.ForeignKey(
        'ominicontacto_app.Pausa',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    aux_code = models.CharField(max_length=32, null=True, blank=True)
    source = models.CharField(max_length=16, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reportes_app_agentactivityeventv2'
        indexes = [
            models.Index(fields=['agente_id', '-ts'], name='reports_aae2_agente_ts'),
            models.Index(fields=['-ts'], name='reports_aae2_ts_desc'),
            models.Index(fields=['event_type'], name='reports_aae2_event_type'),
        ]
