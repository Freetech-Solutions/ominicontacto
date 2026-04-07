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

import copy
import datetime
import json

from django.utils.timezone import now, localtime, timedelta
from django.utils.translation import gettext as _

from reportes_app.models import InteractionsSummary
from reportes_app.services.agent_activity_session_source import get_agent_session_data_for_reports
from reportes_app.services.agent_interactions_kpis import (
    get_agent_hold_seconds,
    get_agent_interactions_kpis,
    get_agent_transfer_counts,
    get_agent_transfer_in_counts,
    _get_agent_whatsapp_in_out_counts,
)

from ominicontacto_app.utiles import (
    datetime_hora_maxima_dia, datetime_hora_minima_dia, format_total_seconds)
from ominicontacto_app.models import (CalificacionCliente, AgenteProfile, Campana, Pausa)

try:
    from whatsapp_app.models import ConversacionWhatsapp
except ImportError:
    ConversacionWhatsapp = None

from ominicontacto_app.services.asterisk.redis_database import AbstractRedisChanelPublisher
from ominicontacto_app.services.redis.connection import create_redis_connection

import logging as _logging

logger = _logging.getLogger(__name__)

AGENTDATA_KEY_TEMPLATE = 'OML:AGENTDATA:AGENT:{0}'


def _safe_int_redis(value, default=0):
    """Convierte un valor a int de forma segura (maneja bytes de Redis)."""
    try:
        if value is None:
            return default
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


def _normalize_redis_dict(redis_dict):
    """Normaliza un diccionario de Redis convirtiendo bytes a strings."""
    if not redis_dict:
        return {}
    normalized = {}
    for key, value in redis_dict.items():
        try:
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            normalized[key] = value
        except (AttributeError, UnicodeDecodeError):
            continue
    return normalized


class ReporteActividadAgente:

    def __init__(self):
        self.pausa = timedelta()
        self.sesion = timedelta()
        self.pausa_recreativa = timedelta()
        self.pausa_productiva = timedelta()

    def _to_dict(self):
        seconds_pausa = self.pausa.total_seconds()
        seconds_pausa_recreativa = self.pausa_recreativa.total_seconds()
        seconds_pausa_productiva = self.pausa_productiva.total_seconds()
        seconds_sesion = self.sesion.total_seconds()

        result = {
            'pausa': seconds_pausa,
            'pausa_recreativa': seconds_pausa_recreativa,
            'pausa_productiva': seconds_pausa_productiva,
            'sesion': seconds_sesion,
        }
        pausa_productiva = self.pausa_productiva -\
            datetime.timedelta(microseconds=self.pausa_productiva.microseconds)
        pausa_recreativa = self.pausa_recreativa -\
            datetime.timedelta(microseconds=self.pausa_recreativa.microseconds)
        result['tiempo_pausa'] = _("{0} hs".format(str(pausa_productiva + pausa_recreativa)))
        return result


# Constantes de tipo de llamada (compatibles con Campana.TYPE_*)
LLAMADA_ENTRANTE = Campana.TYPE_ENTRANTE
TIPOS_LLAMADAS_SALIENTES = (
    Campana.TYPE_MANUAL,
    Campana.TYPE_DIALER,
    Campana.TYPE_PREVIEW,
)


class ReporteEstadisticasDiariaAgente(object):

    CANTIDAD_LOGS = 10

    def _obtener_interacciones_conectadas(self):
        """Interacciones VOICE contestadas del día desde InteractionsSummary."""
        agent_ids = list(self.estadisticas.keys())
        if not agent_ids:
            return []
        return list(
            InteractionsSummary.objects.using('replica')
            .filter(
                end_time__gte=self.desde,
                end_time__lte=self.hasta,
                agent_id__in=agent_ids,
                channel_type='VOICE',
                status='EXIT_ANSWERED',
            )
            .order_by('-end_time')
        )

    def _tipo_campana_y_llamada_desde_interaccion(self, interaction):
        """Deriva tipo_campana y tipo_llamada desde direction e initiation_method."""
        campaign_id = interaction.campaign_id
        if campaign_id:
            tipo = Campana.objects.filter(pk=campaign_id).values_list('type', flat=True).first()
            if tipo is not None:
                return tipo, tipo
        direction = (interaction.direction or '').upper().strip()
        initiation = (interaction.initiation_method or '').upper().strip()
        if direction == 'INBOUND':
            return Campana.TYPE_ENTRANTE, LLAMADA_ENTRANTE
        if initiation == 'DIALER':
            return Campana.TYPE_DIALER, Campana.TYPE_DIALER
        if initiation == 'AGENT' or initiation == 'BOT':
            return Campana.TYPE_MANUAL, Campana.TYPE_MANUAL
        return Campana.TYPE_MANUAL, Campana.TYPE_MANUAL

    def _obtener_estadisticas_calificacion(self):
        return CalificacionCliente.objects.using('replica').filter(
            fecha__gte=self.desde, fecha__lte=self.hasta).select_related(
                'auditoriacalificacion', 'agente', 'opcion_calificacion')

    def _obtener_conversaciones_whatsapp(self):
        """Conversaciones WhatsApp del día con agente asignado, ordenadas por última interacción."""
        if ConversacionWhatsapp is None:
            return []
        agent_ids = list(self.estadisticas.keys())
        if not agent_ids:
            return []
        from django.db.models.functions import Coalesce
        return list(
            ConversacionWhatsapp.objects
            .filter(
                timestamp__gte=self.desde,
                timestamp__lte=self.hasta,
                agent_id__in=agent_ids,
            )
            .select_related('client', 'campana', 'conversation_disposition', 'conversation_disposition__opcion_calificacion')
            .order_by(Coalesce('date_last_interaction', 'timestamp').desc())
        )

    def __init__(self):
        self.calificaciones_dict = {}
        self.estadisticas_dict_base = {
            'conectadas': {
                'total': 0,
                'salientes': 0,
                'entrantes': 0
            },
            'venta': {
                'total': 0,
                'observadas': 0
            },
            'logs': [],
        }
        self.estadisticas = {}
        self.callids_entrantes = set()
        self.callids_salientes = set()
        hoy = localtime(now())
        self.desde = datetime_hora_minima_dia(hoy)
        self.hasta = datetime_hora_maxima_dia(hoy)
        self.inicializar_estadisticas()
        self.interacciones_conectadas = self._obtener_interacciones_conectadas()
        self.calificaciones = list(self._obtener_estadisticas_calificacion())
        self.calcular_estadisticas()

    def inicializar_estadisticas(self):
        for agente in AgenteProfile.objects.obtener_activos():
            self.estadisticas[agente.pk] = copy.deepcopy(self.estadisticas_dict_base.copy())
            self.estadisticas[agente.pk]['tiempos'] = ReporteActividadAgente()
            self.estadisticas[agente.pk]['pausas'] = []
            # Nuevas métricas para dashboard v2
            self.estadisticas[agente.pk]['ready_seconds'] = 0
            self.estadisticas[agente.pk]['acw_seconds'] = 0
            self.estadisticas[agente.pk]['talk_seconds'] = 0.0
            self.estadisticas[agente.pk]['avg_talk_seconds'] = 0.0
            self.estadisticas[agente.pk]['transfer_in'] = 0
            self.estadisticas[agente.pk]['transfer_out'] = 0
            self.estadisticas[agente.pk]['hold_seconds'] = 0
            self.estadisticas[agente.pk]['whatsapp_entrantes'] = 0
            self.estadisticas[agente.pk]['whatsapp_salientes'] = 0
            self.estadisticas[agente.pk]['whatsapp_total'] = 0

    def _calcular_pausas(self, info_agente):
        tipo_pausa = info_agente['tipo_de_pausa']
        self.estadisticas[info_agente['id']]['pausas'].append(
            {'nombre': info_agente['pausa'].nombre,
             'valor': format_total_seconds(info_agente['tiempo'])})

        if tipo_pausa == Pausa.CHOICE_RECREATIVA:
            tiempo_pausa = info_agente['tiempo']
            self.estadisticas[info_agente['id']]['tiempos'].pausa_recreativa += tiempo_pausa

        if tipo_pausa == Pausa.CHOICE_PRODUCTIVA:
            tiempo_pausa = info_agente['tiempo']
            self.estadisticas[info_agente['id']]['tiempos'].pausa_productiva += tiempo_pausa

    def contabilizar_estadisticas_actividad(self):
        hoy = localtime(now()).date()
        date_str = hoy.isoformat()
        session_data = get_agent_session_data_for_reports(date_str, date_str)

        for agente_id, data in session_data.items():
            if agente_id not in self.estadisticas:
                continue
            self.estadisticas[agente_id]['tiempos'].sesion = data['session']
            self.estadisticas[agente_id]['tiempos'].pausa = data['pause']
            self.estadisticas[agente_id]['ready_seconds'] = data.get('ready_seconds', 0) or 0
            self.estadisticas[agente_id]['acw_seconds'] = data.get('acw_seconds', 0) or 0
            for info_pausa in data['pausas_list']:
                self._calcular_pausas(info_pausa)

    def adicionar_log(
            self, numero_marcado, callid, agente_id, campana_id, tipo_campana, contacto_id,
            sort_time=None):
        numero_marcado = numero_marcado
        datos = ''
        es_gestion = ''
        calificacion_nombre = ''
        observaciones = ''
        auditoria_status = ''
        actions = ''
        calificacion = self.calificaciones_dict.get(callid, False)
        if calificacion:
            actions = {
                'calificacionId': calificacion.pk,
                'contactoId': calificacion.contacto_id,
                'campanaId': campana_id
            }
            datos = calificacion.contacto.datos
            es_gestion = calificacion.opcion_calificacion.es_gestion()
            calificacion_nombre = calificacion.opcion_calificacion.nombre
            auditoria = calificacion.obtener_auditoria()
            if auditoria:
                auditoria_status = auditoria.get_resultado_display()
            if es_gestion and calificacion.respuesta_formulario_gestion.exists():
                respuesta_formulario_gestion = calificacion.respuesta_formulario_gestion.first()
                actions['gestionId'] = respuesta_formulario_gestion.pk
            observaciones = calificacion.observaciones
        linea_log = {'phone': numero_marcado,
                     'data': datos,
                     'engaged': es_gestion,
                     'callDisposition': calificacion_nombre,
                     'comments': observaciones,
                     'audit': auditoria_status,
                     'actions': actions,
                     'campana_id': campana_id,
                     'contacto_id': contacto_id,
                     'tipo_campana': tipo_campana,
                     'channel': 'VOICE',
                     'sort_time': sort_time.isoformat() if sort_time else ''
                     }
        self.estadisticas[agente_id]['logs'].append(linea_log)

    def adicionar_log_whatsapp(self, conversacion):
        """Añade una línea de log para una conversación WhatsApp (misma estructura que voz)."""
        agente_id = conversacion.agent_id
        if agente_id not in self.estadisticas:
            return
        phone = conversacion.destination or ''
        data = conversacion.client.datos if conversacion.client_id and conversacion.client else ''
        disp = conversacion.conversation_disposition
        es_gestion = False
        calificacion_nombre = ''
        observaciones = ''
        auditoria_status = ''
        actions = {}
        if disp:
            if disp.opcion_calificacion_id:
                try:
                    opcion = disp.opcion_calificacion
                    calificacion_nombre = opcion.nombre
                    es_gestion = opcion.es_gestion()
                except Exception:
                    pass
            observaciones = (disp.observaciones or '') if hasattr(disp, 'observaciones') else ''
            try:
                auditoria = disp.obtener_auditoria()
                if auditoria:
                    auditoria_status = auditoria.get_resultado_display()
            except Exception:
                pass
            if conversacion.campana_id and conversacion.client_id:
                actions = {
                    'calificacionId': disp.id,
                    'contactoId': conversacion.client_id,
                    'campanaId': conversacion.campana_id,
                }
        sort_dt = conversacion.date_last_interaction or conversacion.timestamp
        sort_time = sort_dt.isoformat() if sort_dt else ''
        tipo_campana = conversacion.campana.type if conversacion.campana_id and conversacion.campana else None
        linea_log = {
            'phone': phone,
            'data': data,
            'engaged': es_gestion,
            'callDisposition': calificacion_nombre,
            'comments': observaciones,
            'audit': auditoria_status,
            'actions': actions,
            'campana_id': conversacion.campana_id,
            'contacto_id': conversacion.client_id,
            'tipo_campana': tipo_campana,
            'channel': 'WHATSAPP',
            'sort_time': sort_time,
        }
        self.estadisticas[agente_id]['logs'].append(linea_log)

    def contabilizar_estadisticas_conectadas(
            self, tipo_campana, tipo_llamada, numero_marcado, callid, evento, agente_id,
            campana_id, contacto_id, end_time=None):
        # Si el log no corresponde a un agente activo lo ignoro.
        if agente_id not in self.estadisticas:
            return
        if evento == 'ANSWER' and tipo_campana != Campana.TYPE_DIALER:
            self.adicionar_log(numero_marcado, callid, agente_id, campana_id, tipo_campana,
                              contacto_id, sort_time=end_time)
            self.estadisticas[agente_id]['conectadas']['total'] += 1
            self.estadisticas[agente_id]['conectadas']['salientes'] += 1
        if evento == 'CONNECT':
            self.adicionar_log(numero_marcado, callid, agente_id, campana_id, tipo_campana,
                              contacto_id, sort_time=end_time)
            self.estadisticas[agente_id]['conectadas']['total'] += 1
            if tipo_llamada == LLAMADA_ENTRANTE:
                self.estadisticas[agente_id]['conectadas']['entrantes'] += 1
            elif tipo_llamada in TIPOS_LLAMADAS_SALIENTES:
                self.estadisticas[agente_id]['conectadas']['salientes'] += 1

    def contabilizar_estadisticas_conectadas_desde_redis(self):
        """
        Sobrescribe conectadas (total, entrantes, salientes) con datos de Redis DB2.
        OML:AGENTDATA:AGENT:{id} - campos: ANSWERED_TOTAL_CALLS:IN, :MANUAL, :DIALER.
        """
        redis_conn = None
        try:
            redis_conn = create_redis_connection(db=2)
            redis_conn.ping()
        except Exception as e:
            logger.warning(
                "Error conectando a Redis DB2 para OML:AGENTDATA: %s. "
                "conectadas permanecerá con valores de InteractionsSummary.", e
            )
            return

        agent_ids = list(self.estadisticas.keys())
        if not agent_ids:
            return

        try:
            pipeline = redis_conn.pipeline()
            for agent_id in agent_ids:
                key = AGENTDATA_KEY_TEMPLATE.format(agent_id)
                pipeline.hgetall(key)
            results = pipeline.execute()
        except Exception as e:
            logger.warning("Error leyendo OML:AGENTDATA desde Redis: %s", e)
            return

        for idx, agent_id in enumerate(agent_ids):
            if agent_id not in self.estadisticas:
                continue
            agentdata_raw = results[idx] if idx < len(results) else None
            agentdata = _normalize_redis_dict(agentdata_raw) if agentdata_raw else {}

            entrantes = _safe_int_redis(agentdata.get('ANSWERED_TOTAL_CALLS:IN', '0'), 0)
            manual = _safe_int_redis(agentdata.get('ANSWERED_TOTAL_CALLS:MANUAL', '0'), 0)
            dialer = _safe_int_redis(agentdata.get('ANSWERED_TOTAL_CALLS:DIALER', '0'), 0)
            salientes = manual + dialer
            total = entrantes + salientes

            self.estadisticas[agent_id]['conectadas'] = {
                'total': total,
                'entrantes': entrantes,
                'salientes': salientes,
            }

    def contabilizar_estadisticas_extra(self):
        """Talk time, ATT, transferencias y hold desde servicios externos."""
        from django.conf import settings

        tz_name = getattr(settings, 'TIME_ZONE', 'UTC')
        interactions = get_agent_interactions_kpis(
            self.desde, self.hasta, agent_id=None, group_by='agent',
            timezone_name=tz_name
        )
        for row in interactions:
            aid = row.get('agent_id')
            if aid in self.estadisticas:
                self.estadisticas[aid]['talk_seconds'] = float(row.get('talk_seconds') or 0)
                self.estadisticas[aid]['avg_talk_seconds'] = float(
                    row.get('avg_talk_seconds_answered') or 0
                )

        for row in get_agent_transfer_counts(self.desde, self.hasta):
            aid = row.get('agent_id')
            if aid in self.estadisticas:
                self.estadisticas[aid]['transfer_out'] = row.get('transfer_count', 0) or 0

        for row in get_agent_transfer_in_counts(self.desde, self.hasta):
            aid = row.get('agent_id')
            if aid in self.estadisticas:
                self.estadisticas[aid]['transfer_in'] = row.get('transfer_in_count', 0) or 0

        for row in get_agent_hold_seconds(self.desde, self.hasta):
            aid = row.get('agent_id')
            if aid in self.estadisticas:
                self.estadisticas[aid]['hold_seconds'] = int(row.get('hold_seconds', 0) or 0)

        for row in _get_agent_whatsapp_in_out_counts(
                self.desde, self.hasta, agent_id=None, group_by='agent',
                timezone_name=tz_name):
            aid = row.get('agent_id')
            if aid in self.estadisticas:
                wa_in = row.get('interactions_inbound_wa') or 0
                wa_out = row.get('interactions_outbound_wa') or 0
                self.estadisticas[aid]['whatsapp_entrantes'] = wa_in
                self.estadisticas[aid]['whatsapp_salientes'] = wa_out
                self.estadisticas[aid]['whatsapp_total'] = wa_in + wa_out

    def contabilizar_estadisticas_calificaciones(self, calificacion):
        self.calificaciones_dict[calificacion.callid] = calificacion
        agente_id = calificacion.agente.pk
        if calificacion.opcion_calificacion.es_gestion():
            if agente_id not in self.estadisticas:
                return
            self.estadisticas[agente_id]['venta']['total'] += 1
        if calificacion.obtener_auditoria() and calificacion.tiene_auditoria_observada():
            if agente_id not in self.estadisticas:
                return
            self.estadisticas[agente_id]['venta']['observadas'] += 1

    def calcular_estadisticas(self):
        self.contabilizar_estadisticas_actividad()
        self.contabilizar_estadisticas_extra()
        for calificacion in self.calificaciones:
            self.contabilizar_estadisticas_calificaciones(calificacion)

        for interaction in self.interacciones_conectadas:
            callid = interaction.interaction_id
            agente_id = interaction.agent_id
            campana_id = interaction.campaign_id
            tipo_campana, tipo_llamada = self._tipo_campana_y_llamada_desde_interaccion(
                interaction
            )
            numero_marcado = interaction.numero_marcado or ''
            contacto_id = interaction.customer_id
            self.contabilizar_estadisticas_conectadas(
                tipo_campana, tipo_llamada, numero_marcado, callid, 'CONNECT', agente_id,
                campana_id, contacto_id, end_time=interaction.end_time
            )

        # Incluir logs de WhatsApp y unificar con voz: ordenar por fecha y limitar
        conversaciones_wa = self._obtener_conversaciones_whatsapp()
        for conversacion in conversaciones_wa:
            self.adicionar_log_whatsapp(conversacion)
        for agente_id in self.estadisticas:
            logs = self.estadisticas[agente_id]['logs']
            logs_sorted = sorted(
                logs,
                key=lambda x: x.get('sort_time') or '',
                reverse=True
            )
            self.estadisticas[agente_id]['logs'] = logs_sorted[:self.CANTIDAD_LOGS]

        self.contabilizar_estadisticas_conectadas_desde_redis()


class ReporteDiarioAgentesFamily(AbstractRedisChanelPublisher):

    def _create_dict(self, family_member):
        return family_member[1]

    def _format_session_display(self, td):
        """Formato HH:MM:SS para tiempo de sesión."""
        return format_total_seconds(td) if td else '00:00:00'

    def _obtener_todos(self):
        reporte = ReporteEstadisticasDiariaAgente()
        reporte_resultados = []
        for agente_id, datos in reporte.estadisticas.items():
            tiempos_obj = datos['tiempos']
            tiempos_dict = tiempos_obj._to_dict()
            session_seconds = int(tiempos_dict.get('sesion', 0))
            pause_seconds = int(tiempos_obj.pausa.total_seconds())
            ready_seconds = datos.get('ready_seconds', 0) or 0
            acw_seconds = datos.get('acw_seconds', 0) or 0
            talk_seconds = int(datos.get('talk_seconds', 0) or 0)
            total_avail = ready_seconds + acw_seconds + pause_seconds + talk_seconds
            ready_pct = round(100 * ready_seconds / total_avail, 1) if total_avail > 0 else 0
            acw_pct = round(100 * acw_seconds / total_avail, 1) if total_avail > 0 else 0
            pause_pct = round(100 * pause_seconds / total_avail, 1) if total_avail > 0 else 0
            talk_pct = round(100 * talk_seconds / total_avail, 1) if total_avail > 0 else 0

            # Normalizar para que la suma sea exactamente 100% (evitar 99.9 o 100.1 por redondeo)
            pcts = [ready_pct, acw_pct, pause_pct, talk_pct]
            total_pct = sum(pcts)
            if total_pct != 100 and total_avail > 0:
                idx_max = pcts.index(max(pcts))
                pcts[idx_max] = round(pcts[idx_max] + (100 - total_pct), 1)
                ready_pct, acw_pct, pause_pct, talk_pct = pcts

            datos['tiempos'] = json.dumps(tiempos_dict)
            datos['conectadas'] = json.dumps(datos['conectadas'])
            # Quitar sort_time de cada log antes de enviar al frontend
            logs_export = []
            for log_item in datos['logs']:
                log_copy = {k: v for k, v in log_item.items() if k != 'sort_time'}
                logs_export.append(log_copy)
            datos['logs'] = json.dumps(logs_export)
            datos['venta'] = json.dumps(datos['venta'])
            datos['pausas'] = json.dumps(datos['pausas'])
            # Nuevas métricas para dashboard v2
            datos['session_seconds'] = session_seconds
            datos['session_display'] = self._format_session_display(tiempos_obj.sesion)
            datos['ready_seconds'] = ready_seconds
            datos['acw_seconds'] = acw_seconds
            datos['pause_seconds'] = pause_seconds
            datos['ready_pct'] = ready_pct
            datos['acw_pct'] = acw_pct
            datos['pause_pct'] = pause_pct
            datos['talk_pct'] = talk_pct
            datos['talk_seconds'] = round(float(datos.get('talk_seconds', 0) or 0), 2)
            datos['avg_talk_seconds'] = round(float(datos.get('avg_talk_seconds', 0) or 0), 2)
            datos['transfer_in'] = datos.get('transfer_in', 0) or 0
            datos['transfer_out'] = datos.get('transfer_out', 0) or 0
            datos['hold_seconds'] = int(datos.get('hold_seconds', 0) or 0)
            datos['whatsapp_entrantes'] = datos.get('whatsapp_entrantes', 0) or 0
            datos['whatsapp_salientes'] = datos.get('whatsapp_salientes', 0) or 0
            datos['whatsapp_total'] = datos.get('whatsapp_total', 0) or 0
            reporte_resultados.append((agente_id, datos))
        return reporte_resultados

    def _get_nombre_family(self, family_member):
        task_id = 'dashboard1'
        channel = "{0}:{1}:{2}".format(self.get_nombre_families(), family_member[0], task_id)
        return channel

    def get_nombre_families(self):
        return "OML:AGENT_REPORT:CURRENT_DAY_STATS"

    def regenerar_families(self):
        """regenera la family"""
        self._delete_tree_family()
        self._create_families()

    def regenerar_family(self, family_member):
        """regenera una family"""
        self.delete_family(family_member)
        self._create_family(family_member)
