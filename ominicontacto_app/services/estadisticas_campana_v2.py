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

"""
Servicio V2 para generar reporte gráfico de una campaña usando principalmente
InteractionsSummary (tabla interactions_summary), con excepción del KPI de
interacciones WhatsApp por agente, que usa ConversacionWhatsapp.

Diferencias semánticas respecto a V1 (estadisticas_campana.py):
- Una fila por interacción/llamada; no hay eventos transitorios (DIAL/ANSWER/CONNECT).
- direction solo INBOUND/OUTBOUND: no se distingue manual/dialer/preview por fila;
  las columnas "Manuales", "Manuales atendidas", "Manuales no atendidas" se dejan en 0
  salvo que se pueda inferir de channel_data sin usar LlamadaLog/LlamadaResumen.
- Tiempos: wait_conn_duration reemplaza bridge_wait_time; agent_duration reemplaza
  tiempo hablado por agente.
- No atendidos y detalle se reconstruyen desde status y hangup_cause (mapeo documentado
  en HANGUP_STATUS_TO_NO_ATENDIDO_LABEL).
- Entrantes: transferencia OK hacia otra campaña (interaction_transfers: destination_type
  CAMPAIGN, transfer_type BLIND o CONSULT) en la fila nativa de la campaña origen se refleja
  como effective_status EXIT_TRANSFERRED_OUT: cuenta como recibida pero no como
  atendida/expirada/abandonada en el detalle de esa campaña.

Calificaciones CRM:
- Las secciones "Calificaciones de Clientes Contactados" y "Calificaciones por Agente"
  NO usan InteractionsSummary.qualification_id (no es confiable). Se calculan desde
  los modelos CRM: CalificacionCliente e HistoricalCalificacionCliente (igual que V1
  sin omnidialer).
- Criterio temporal: CalificacionCliente se filtra por modified__range (cuándo se
  creó/modificó la calificación); HistoricalCalificacionCliente por history_date__range
  (cuándo se generó esa versión en el historial). Para campañas no entrantes se usa
  solo CalificacionCliente; para entrantes solo HistoricalCalificacionCliente, para
  evitar doble conteo.
- Entrantes: se deduplican históricos por callid tomando una sola calificación efectiva
  por llamada (la última por history_date, luego history_id). Impacto: total_calificados,
  total_ventas y totales por agente reflejan una calificación por llamada, no por cada
  versión histórica en el rango (evita inflar números cuando hay varias actualizaciones).
- Entrantes: callid no nulo, no vacío y no solo espacios (Trim(callid)!=''). El "último por callid" se elige
  incluyendo todos los history_type; luego se excluyen history_type='-' (create+delete
  en rango cuenta 0).
- Rango temporal: __range es inclusivo en ambos extremos (fecha_desde <= x <= fecha_hasta).
  Se asume que fecha_desde/fecha_hasta son timezone-aware y comparables con modified/history_date.
- Llamadas atendidas sin calificación: "atendida por humano" = EXIT_ANSWERED y (agent_duration>0
  o agent_id no nulo y distinto de -1). Cualquiera de las dos condiciones basta (inbound/outbound).

Notas de compatibilidad:
- La fuente de datos es únicamente interactions_summary para métricas de interacción
  (totales, no atendidos, tiempos, agent/bot, detalle llamadas).
- El contrato de salida (keys de _calcular_estadisticas y general_campana) es el mismo
  que V1 para que los templates y el PDF sigan funcionando.
- llamadas_pendientes no viene de InteractionsSummary: se usa la misma lógica que V1
  (AgenteEnContacto para preview, get_dialer_service() para dialer).

Índices recomendados para rendimiento (opcional, vía migración):
- HistoricalCalificacionCliente: (opcion_calificacion_id, history_date, callid, history_id)
  o (callid, history_date DESC, history_id DESC) para la ventana por callid.
- CalificacionCliente: (opcion_calificacion_id, modified) para el rango por campaña.
"""

from __future__ import unicode_literals

import os
import logging as _logging

import pygal
from collections import OrderedDict
from pygal.style import LightGreenStyle, DefaultStyle
from django.conf import settings
from django.db import connections
from django.db.models import (
    Q, Count, Avg, Sum, Subquery, OuterRef, F, Window,
    Case, When, Value, CharField, Exists,
)
from django.db.models.functions import RowNumber, Trim
from django.utils.translation import gettext as _, gettext_lazy

from ominicontacto_app.models import (
    AgenteEnContacto,
    CalificacionCliente,
    Campana,
    AgenteProfile,
    HistoricalCalificacionCliente,
    OpcionCalificacion,
)
from ominicontacto_app.services.dialer import get_dialer_service
from reportes_app.models import (
    InteractionsSummary,
    InteractionTransfers,
    q_interaction_transfers_campaign_blind_consult,
)
from utiles_globales import adicionar_render_unicode
from whatsapp_app.models import ConversacionWhatsapp

logger = _logging.getLogger(__name__)

# Labels para reporte no atendidos (mismo orden y textos que V1).
# gettext_lazy para que se traduzcan en runtime según idioma del request, no en import time.
_NO_ATENDIDO_LABELS = (
    gettext_lazy('No atiende'),
    gettext_lazy('Cancelado'),
    gettext_lazy('Contestador detectado'),
    gettext_lazy('Ocupado'),
    gettext_lazy('Destino no disponibles'),
    gettext_lazy('Fallidas'),
    gettext_lazy('Otro'),
    gettext_lazy('Blacklist'),
    gettext_lazy('Abandonadas esperando agente'),
    gettext_lazy('Abandonadas durante anuncio'),
    gettext_lazy('Expiradas esperando agente'),
    gettext_lazy('Canales congestionados'),
    gettext_lazy('Numero no enrutable'),
    gettext_lazy('Shortcall'),
)

# Mapeo (status, hangup_cause) -> índice en _NO_ATENDIDO_LABELS (0..13). "Otro" = 6.
# Preferir hangup_cause cuando exista; si no, derivar de status.
def _build_no_atendido_mapping():
    idx_otro = 6
    mapping = {}
    # hangup_cause / status -> label index
    cause_to_idx = {
        'NOANSWER': 0,
        'CANCEL': 1,
        'EXIT_AMD': 2,
        'BUSY': 3,
        'CHANUNAVAIL': 4,
        'FAIL': 5,
        'OTHER': 6,
        'BLACKLIST': 7,
        'EXIT_ABANDON': 8,
        'EXIT_ABANDON_WEL': 9,
        'EXIT_HANDOFF_ABANDON': 8,
        'EXIT_TIMEOUT': 10,
        'EXIT_HANDOFF_TIMEOUT': 10,
        'CONGESTION': 11,
        'NONDIALPLAN': 12,
        'EXIT_SHORTCALL': 13,
    }
    for key, idx in cause_to_idx.items():
        mapping[(None, key)] = idx
        mapping[(key, None)] = idx
        mapping[(key, '')] = idx
    mapping[(None, None)] = idx_otro
    return mapping, idx_otro

_HANGUP_STATUS_TO_NO_ATENDIDO_IDX, _IDX_OTRO = _build_no_atendido_mapping()


def _no_atendido_index(status, hangup_cause):
    status = (status or '').strip().upper() or None
    hc = (hangup_cause or '').strip().upper() or None
    if not hc and not status:
        return _IDX_OTRO
    # Prefer hangup_cause
    if hc:
        idx = _HANGUP_STATUS_TO_NO_ATENDIDO_IDX.get((None, hc))
        if idx is not None:
            return idx
    if status:
        idx = _HANGUP_STATUS_TO_NO_ATENDIDO_IDX.get((status, None))
        if idx is not None:
            return idx
    return _IDX_OTRO


class EstadisticasServiceV2:
    """
    Servicio de estadísticas de campaña basado principalmente en
    InteractionsSummary (sin imports de LlamadaLog ni LlamadaResumen).
    Excepción: KPI de interacciones WhatsApp por agente, desde ConversacionWhatsapp.
    """

    def __init__(self, campana, fecha_desde, fecha_hasta):
        self.campana = campana
        self.fecha_desde = fecha_desde
        self.fecha_hasta = fecha_hasta
        self._transferidas_in_ids = None
        self.opciones_calificacion_campana = {
            opcion.pk: opcion
            for opcion in campana.opciones_calificacion.all().select_related('formulario')
        }
        self._qualification_ids_gestion = [
            pk for pk, op in self.opciones_calificacion_campana.items() if op.es_gestion()
        ]
        agentes_campana = AgenteProfile.objects.obtener_agentes_campana(
            campana
        ).select_related('user')
        self.agentes_dict = {agente.pk: agente for agente in agentes_campana}

        # Rellenados por calcular_estadisticas_totales()
        self._llamadas_realizadas = 0
        self._llamadas_recibidas = 0
        self._tiempo_promedio_espera = None
        self._tiempo_promedio_abandono = None
        self._llamadas_pendientes_extra = 0
        self.reporte_detalle_llamadas = None  # OrderedDict
        self.reporte_no_atendidos = None  # OrderedDict, total_no_atendidos
        self.llamadas_atendidas_sin_calificacion = 0
        self.reporte_calificaciones_atendidas = None  # dict nombre -> count
        self.reporte_calificaciones_agentes_dict = {}  # agente_id -> {nombre, totales_calificaciones, total_calificados, total_gestionados}
        self.total_calificados = 0
        self.total_ventas = 0
        self.estadisticas_llamadas_por_agente = None  # dict agente_id -> {ofrecidas, atendidas, no_atendidas, nombre}
        # Agent vs Bot (EXIT_ANSWERED only): human_only, ai_only, colaboración
        self._llamadas_humano_only = 0
        self._llamadas_ai_only = 0
        self._llamadas_colaboracion = 0
        # WhatsApp conectadas: Humano vs IA (desde ConversacionWhatsapp)
        self._wa_conectadas_humano = 0
        self._wa_conectadas_ia = 0
        self._wa_conectadas_colaboracion = 0
        # WhatsApp recibidos (conversaciones inbound): solo si campana tiene canalidad WA
        self._whatsapp_recibidos = None
        # KPI Interacciones por Agente (omnicanal: VOICE, WA, FBMSN, EMAIL)
        self.interacciones_por_agente = []
        # KPI Performance de agentes (VOICE + Chat)
        self.performance_agentes = []

    def _get_transferidas_in_ids(self):
        if self._transferidas_in_ids is None:
            self._transferidas_in_ids = (
                InteractionTransfers.objects.using('replica')
                .filter(destination_campaign_id=self.campana.pk)
                .filter(q_interaction_transfers_campaign_blind_consult())
                .values_list('interaction_id', flat=True)
                .distinct()
            )
        return self._transferidas_in_ids

    def _get_campaign_filter(self):
        campaign_filter = Q(campaign_id=self.campana.pk)
        if not self.campana.es_entrante:
            return campaign_filter
        return campaign_filter | Q(
            interaction_id__in=self._get_transferidas_in_ids()
        )

    def _annotate_has_transfer_and_effective_status(self, qs):
        """
        has_transfer: existe alguna fila en InteractionTransfers para la interacción
        (p. ej. KPIs de transfer por agente).

        effective_status: si la fila es nativa de esta campaña (campaign_id == self.campana)
        y hubo transferencia OK hacia otra campaña (CAMPAIGN, BLIND/CONSULT;
        destination_campaign_id distinto del campaign_id del resumen), se usa
        EXIT_TRANSFERRED_OUT: no cuenta como atendida,
        expirada ni abandonada en el detalle de la campaña de origen. Las filas incluidas
        solo por transferencia entrante (campaign_id distinto de self.campana) conservan
        status real para reflejar el desenlace en la campaña destino.
        """
        transfers_exists = InteractionTransfers.objects.using('replica').filter(
            interaction_id=OuterRef('interaction_id')
        )
        xfer_out_other_campaign = Exists(
            InteractionTransfers.objects.using('replica')
            .filter(interaction_id=OuterRef('interaction_id'))
            .filter(q_interaction_transfers_campaign_blind_consult())
            .exclude(destination_campaign_id=OuterRef('campaign_id'))
        )
        return qs.annotate(has_transfer=Exists(transfers_exists)).annotate(
            xfer_out_other_campaign=xfer_out_other_campaign
        ).annotate(
            effective_status=Case(
                When(
                    Q(campaign_id=self.campana.pk) & Q(xfer_out_other_campaign=True),
                    then=Value('EXIT_TRANSFERRED_OUT'),
                ),
                default=F('status'),
                output_field=CharField(),
            )
        )

    def _get_base_queryset(self):
        qs = (
            InteractionsSummary.objects.using('replica')
            .filter(
                self._get_campaign_filter(),
                start_time__gte=self.fecha_desde,
                start_time__lte=self.fecha_hasta,
            )
            .filter(channel_type__iexact='VOICE')
        )
        return self._annotate_has_transfer_and_effective_status(qs)

    def _get_queryset_interacciones_por_agente(self):
        """Queryset de InteractionsSummary por campaña y fechas, sin filtrar por channel_type."""
        qs = (
            InteractionsSummary.objects.using('replica')
            .filter(
                self._get_campaign_filter(),
                start_time__gte=self.fecha_desde,
                start_time__lte=self.fecha_hasta,
            )
        )
        return self._annotate_has_transfer_and_effective_status(qs)

    def _interacciones_por_agente(self, qs_all):
        """
        KPI Interacciones por Agente: una fila por agente con 8 columnas
        (tel/wa/fbmsn/email × outbound/inbound).

        - Tel/FBMSN/Email: InteractionsSummary
        - WhatsApp (wa_out/wa_in): ConversacionWhatsapp (saliente True/False)

        Solo agent_id IS NOT NULL y != -1.
        """
        qs = qs_all.filter(agent_id__isnull=False).exclude(agent_id=-1)
        q_voice = Q(channel_type__iexact='VOICE')
        q_fbmsn = (
            Q(channel_type__iexact='FBMSN')
            | Q(channel_type__iexact='FACEBOOK_MSN')
        )
        q_email = Q(channel_type__iexact='EMAIL')
        q_out = Q(direction__iexact='OUTBOUND')
        q_in = Q(direction__iexact='INBOUND')

        rows = list(
            qs.values('agent_id')
            .annotate(
                tel_out=Count('id', filter=q_voice & q_out),
                tel_in=Count('id', filter=q_voice & q_in),
                fbmsn_out=Count('id', filter=q_fbmsn & q_out),
                fbmsn_in=Count('id', filter=q_fbmsn & q_in),
                email_out=Count('id', filter=q_email & q_out),
                email_in=Count('id', filter=q_email & q_in),
            )
        )

        wa_rows = list(
            ConversacionWhatsapp.objects.filter(
                campana_id=self.campana.pk,
                timestamp__gte=self.fecha_desde,
                timestamp__lte=self.fecha_hasta,
                agent_id__isnull=False,
            )
            .exclude(agent_id=-1)
            .values('agent_id')
            .annotate(
                wa_out=Count('id', filter=Q(saliente=True)),
                wa_in=Count('id', filter=Q(saliente=False)),
            )
        )

        merged_rows = {}
        for row in rows:
            aid = row['agent_id']
            merged_rows[aid] = {
                'agent_id': aid,
                'tel_out': row['tel_out'] or 0,
                'tel_in': row['tel_in'] or 0,
                'wa_out': 0,
                'wa_in': 0,
                'fbmsn_out': row['fbmsn_out'] or 0,
                'fbmsn_in': row['fbmsn_in'] or 0,
                'email_out': row['email_out'] or 0,
                'email_in': row['email_in'] or 0,
            }

        for wa_row in wa_rows:
            aid = wa_row['agent_id']
            if aid not in merged_rows:
                merged_rows[aid] = {
                    'agent_id': aid,
                    'tel_out': 0,
                    'tel_in': 0,
                    'wa_out': 0,
                    'wa_in': 0,
                    'fbmsn_out': 0,
                    'fbmsn_in': 0,
                    'email_out': 0,
                    'email_in': 0,
                }
            merged_rows[aid]['wa_out'] += wa_row['wa_out'] or 0
            merged_rows[aid]['wa_in'] += wa_row['wa_in'] or 0

        if not merged_rows:
            self.interacciones_por_agente = []
            return

        missing_ids = [
            aid for aid in merged_rows.keys() if self.agentes_dict.get(aid) is None
        ]
        extra_agentes = {}
        if missing_ids:
            for agente in AgenteProfile.objects.filter(
                pk__in=missing_ids
            ).select_related('user'):
                extra_agentes[agente.pk] = (
                    agente.user.get_full_name() or agente.user.username
                )

        result = []
        for aid, merged_row in merged_rows.items():
            agente = self.agentes_dict.get(aid)
            if agente:
                nombre = agente.user.get_full_name() or agente.user.username
            else:
                nombre = extra_agentes.get(
                    aid, _('Agente #%(id)s') % {'id': aid}
                )
            result.append({
                'agent_id': aid,
                'nombre': nombre,
                'tel_out': merged_row['tel_out'],
                'tel_in': merged_row['tel_in'],
                'wa_out': merged_row['wa_out'],
                'wa_in': merged_row['wa_in'],
                'fbmsn_out': merged_row['fbmsn_out'],
                'fbmsn_in': merged_row['fbmsn_in'],
                'email_out': merged_row['email_out'],
                'email_in': merged_row['email_in'],
            })
        result.sort(key=lambda x: (x['nombre'].lower(), x['agent_id']))
        self.interacciones_por_agente = result

    def _performance_agentes(self, qs_all):
        """
        KPI Performance de agentes: una fila por agente con métricas VOICE y Chat.
        Solo agent_id IS NOT NULL y != -1. Una sola consulta agregada por agente.
        """
        qs = qs_all.filter(agent_id__isnull=False).exclude(agent_id=-1)
        ids_gestion = self._qualification_ids_gestion

        q_voice = (
            Q(channel_type__iexact='VOICE')
            & Q(effective_status__iexact='EXIT_ANSWERED')
            & Q(agent_duration__gt=0)
        )
        q_voice_gestion = q_voice & Q(qualification_id__in=ids_gestion)
        q_voice_transfer = q_voice & Q(has_transfer=True)

        q_chat = (
            (Q(channel_type__iexact='WHATSAPP') | Q(channel_type__iexact='MESSENGER'))
            & Q(effective_status__iexact='EXIT_ANSWERED')
        )
        q_chat_gestion = q_chat & Q(qualification_id__in=ids_gestion)
        q_chat_transfer = q_chat & Q(has_transfer=True)

        rows = list(
            qs.values('agent_id')
            .annotate(
                voice_calls=Count('id', filter=q_voice),
                voice_gestiones=Count('id', filter=q_voice_gestion),
                voice_transfers=Count('id', filter=q_voice_transfer),
                voice_atv_seconds=Avg('agent_duration', filter=q_voice),
                chat_interactions=Count('id', filter=q_chat),
                chat_gestiones=Count('id', filter=q_chat_gestion),
                chat_transfers=Count('id', filter=q_chat_transfer),
                chat_avg_resolution_seconds=Avg('total_duration', filter=q_chat),
            )
        )
        if not rows:
            self.performance_agentes = []
            return

        missing_ids = [
            r['agent_id']
            for r in rows
            if self.agentes_dict.get(r['agent_id']) is None
        ]
        extra_agentes = {}
        extra_agentes_voicebot = {}
        if missing_ids:
            for agente in AgenteProfile.objects.filter(
                pk__in=missing_ids
            ).select_related('user'):
                extra_agentes[agente.pk] = (
                    agente.user.get_full_name() or agente.user.username
                )
                extra_agentes_voicebot[agente.pk] = agente.voicebot

        result = []
        for r in rows:
            aid = r['agent_id']
            agente = self.agentes_dict.get(aid)
            if agente:
                nombre = agente.user.get_full_name() or agente.user.username
                es_voicebot = agente.voicebot
            else:
                nombre = extra_agentes.get(
                    aid, _('Agente #%(id)s') % {'id': aid}
                )
                es_voicebot = extra_agentes_voicebot.get(aid, False)
            if es_voicebot:
                continue

            voice_calls = r['voice_calls'] or 0
            voice_gestiones = r['voice_gestiones'] or 0
            voice_transfers = r['voice_transfers'] or 0
            chat_interactions = r['chat_interactions'] or 0
            chat_gestiones = r['chat_gestiones'] or 0
            chat_transfers = r['chat_transfers'] or 0

            tel_gestiones_pct = (
                (100.0 * voice_gestiones / voice_calls) if voice_calls else None
            )
            tel_transfer_pct = (
                (100.0 * voice_transfers / voice_calls) if voice_calls else None
            )
            tel_atv = float(r['voice_atv_seconds']) if r['voice_atv_seconds'] is not None else None

            chat_gestiones_pct = (
                (100.0 * chat_gestiones / chat_interactions) if chat_interactions else None
            )
            chat_transfer_pct = (
                (100.0 * chat_transfers / chat_interactions) if chat_interactions else None
            )
            chat_avg_resolution = (
                float(r['chat_avg_resolution_seconds'])
                if r['chat_avg_resolution_seconds'] is not None
                else None
            )

            result.append({
                'agent_id': aid,
                'nombre': nombre,
                'tel_gestiones_pct': tel_gestiones_pct,
                'tel_atv': tel_atv,
                'tel_transfer_pct': tel_transfer_pct,
                'chat_gestiones_pct': chat_gestiones_pct,
                'chat_avg_resolution': chat_avg_resolution,
                'chat_transfer_pct': chat_transfer_pct,
            })
        result.sort(key=lambda x: (x['nombre'].lower(), x['agent_id']))
        self.performance_agentes = result

    def _totales_llamadas(self, qs):
        agg = qs.aggregate(
            outbound=Count('id', filter=Q(direction__iexact='OUTBOUND')),
            inbound=Count('id', filter=Q(direction__iexact='INBOUND')),
            sum_wait_answered=Sum(
                'wait_conn_duration',
                filter=Q(
                    direction__iexact='INBOUND',
                    effective_status__iexact='EXIT_ANSWERED',
                ),
            ),
            count_answered=Count(
                'id',
                filter=Q(
                    direction__iexact='INBOUND',
                    effective_status__iexact='EXIT_ANSWERED',
                ),
            ),
            sum_wait_abandon=Sum(
                'wait_conn_duration',
                filter=Q(
                    direction__iexact='INBOUND',
                )
                & (
                    Q(effective_status__iexact='EXIT_ABANDON')
                    | Q(effective_status__iexact='EXIT_TIMEOUT')
                    | Q(effective_status__iexact='EXIT_HANDOFF_ABANDON')
                    | Q(effective_status__iexact='EXIT_HANDOFF_TIMEOUT')
                ),
            ),
            count_abandon=Count(
                'id',
                filter=Q(
                    direction__iexact='INBOUND',
                )
                & (
                    Q(effective_status__iexact='EXIT_ABANDON')
                    | Q(effective_status__iexact='EXIT_TIMEOUT')
                    | Q(effective_status__iexact='EXIT_HANDOFF_ABANDON')
                    | Q(effective_status__iexact='EXIT_HANDOFF_TIMEOUT')
                ),
            ),
        )
        self._llamadas_realizadas = agg['outbound'] or 0
        self._llamadas_recibidas = agg['inbound'] or 0
        if self.campana.es_entrante and (agg['count_answered'] or 0) > 0:
            total = agg['sum_wait_answered'] or 0
            self._tiempo_promedio_espera = float(total) / agg['count_answered']
        else:
            self._tiempo_promedio_espera = None
        if self.campana.es_entrante and (agg['count_abandon'] or 0) > 0:
            total = agg['sum_wait_abandon'] or 0
            self._tiempo_promedio_abandono = float(total) / agg['count_abandon']
        else:
            self._tiempo_promedio_abandono = None

        # Llamadas pendientes (fuera de InteractionsSummary)
        if self.campana.es_preview:
            self._llamadas_pendientes_extra = AgenteEnContacto.objects.filter(
                estado=AgenteEnContacto.ESTADO_INICIAL,
                campana_id=self.campana.pk,
                es_originario=True,
            ).count()
        elif self.campana.es_dialer:
            dialer_service = get_dialer_service()
            self._llamadas_pendientes_extra = dialer_service.obtener_llamadas_pendientes(
                self.campana
            )
        else:
            self._llamadas_pendientes_extra = 0

    def _agent_vs_bot_counts(self, qs):
        """Conteos EXIT_ANSWERED por tipo de atención: solo humano, solo IA, colaboración."""
        q_answered = Q(effective_status__iexact='EXIT_ANSWERED')
        q_bot_zero = Q(bot_duration=0) | Q(bot_duration__isnull=True)
        q_agent_zero = Q(agent_duration=0) | Q(agent_duration__isnull=True)
        agg = qs.aggregate(
            human_only=Count(
                'id',
                filter=q_answered & Q(agent_duration__gt=0) & q_bot_zero,
            ),
            ai_only=Count(
                'id',
                filter=q_answered & Q(bot_duration__gt=0) & q_agent_zero,
            ),
            collab=Count(
                'id',
                filter=q_answered & Q(bot_duration__gt=0) & Q(agent_duration__gt=0),
            ),
        )
        self._llamadas_humano_only = agg['human_only'] or 0
        self._llamadas_ai_only = agg['ai_only'] or 0
        self._llamadas_colaboracion = agg['collab'] or 0

    def _wa_humano_vs_ia_counts(self):
        """
        Conteos de conversaciones WhatsApp atendidas por tipo de agente (Humano/IA).
        Usa ConversacionWhatsapp; colaboración = 0 (una conversación tiene un solo agent).
        """
        qs_wa = (
            ConversacionWhatsapp.objects.filter(
                campana_id=self.campana.pk,
                timestamp__gte=self.fecha_desde,
                timestamp__lte=self.fecha_hasta,
                atendida=True,
                agent_id__isnull=False,
            )
            .exclude(agent_id=-1)
        )
        self._wa_conectadas_humano = qs_wa.filter(agent__voicebot=False).count()
        self._wa_conectadas_ia = qs_wa.filter(agent__voicebot=True).count()
        self._wa_conectadas_colaboracion = 0

    def _whatsapp_recibidos_count(self):
        """
        Conteo de conversaciones WhatsApp inbound de la campaña en el rango de fechas.
        Solo se calcula cuando la campaña tiene la canalidad WhatsApp habilitada.
        """
        if not self.campana.whatsapp_habilitado:
            self._whatsapp_recibidos = None
            return
        self._whatsapp_recibidos = ConversacionWhatsapp.objects.filter(
            campana_id=self.campana.pk,
            saliente=False,
            timestamp__gte=self.fecha_desde,
            timestamp__lte=self.fecha_hasta,
        ).count()

    def _detalle_llamadas(self, qs):
        # Para dialer se usa una sola aggregate(); para el resto, values+annotate por direction/status
        if self.campana.type != Campana.TYPE_DIALER:
            by_status = list(
                qs.values('direction', 'effective_status').annotate(cantidad=Count('id'))
            )
        labels_entrante = (
            _('Recibidas'),
            _('Atendidas'),
            _('Expiradas'),
            _('Abandonadas'),
            _('Abandonadas durante anuncio'),
            _('Manuales'),
            _('Manuales atendidas'),
            _('Manuales no atendidas'),
        )
        labels_dialer = (
            _('Discadas'),
            _('Atendidas'),
            _('Conectadas al agente'),
            _('Perdidas'),
            _('Contestador detectado'),
            _('Manuales'),
            _('Manuales atendidas'),
            _('Manuales no atendidas'),
        )
        labels_manual = (
            _('Discadas'),
            _('Discadas atendidas'),
            _('Discadas no atendidas'),
        )
        labels_preview = (
            _('Discadas'),
            _('Conectadas'),
            _('No conectadas'),
            _('Manuales'),
            _('Manuales atendidas'),
            _('Manuales no atendidas'),
        )

        if self.campana.type == Campana.TYPE_ENTRANTE:
            reporte = OrderedDict((k, 0) for k in labels_entrante)
            for row in by_status:
                d = (row['direction'] or '').upper()
                s = (row['effective_status'] or '').upper()
                c = row['cantidad']
                if d != 'INBOUND':
                    continue
                reporte[_('Recibidas')] += c
                if s == 'EXIT_ANSWERED':
                    reporte[_('Atendidas')] += c
                elif s in ('EXIT_TIMEOUT', 'EXIT_HANDOFF_TIMEOUT'):
                    reporte[_('Expiradas')] += c
                elif s in ('EXIT_ABANDON', 'EXIT_HANDOFF_ABANDON'):
                    reporte[_('Abandonadas')] += c
                elif s == 'ABANDONWEL':
                    reporte[_('Abandonadas durante anuncio')] += c
            # Manuales* = 0 (documentado)
        elif self.campana.type == Campana.TYPE_DIALER:
            # Una sola query agregada: Discadas, Atendidas, Conectadas al agente, Perdidas, Contestador
            q_out = Q(direction__iexact='OUTBOUND')
            q_answered = q_out & Q(effective_status__iexact='EXIT_ANSWERED')
            q_conectadas_agente = q_answered & (
                (Q(agent_id__isnull=False) & ~Q(agent_id=-1)) | Q(agent_duration__gt=0)
            )
            agg = qs.aggregate(
                discadas=Count('id', filter=q_out),
                atendidas=Count('id', filter=q_answered),
                conectadas_agente=Count('id', filter=q_conectadas_agente),
                perdidas=Count(
                    'id',
                    filter=q_out
                    & (
                        Q(effective_status__iexact='EXIT_TIMEOUT')
                        | Q(effective_status__iexact='EXIT_ABANDON')
                        | Q(effective_status__iexact='EXIT_HANDOFF_TIMEOUT')
                        | Q(effective_status__iexact='EXIT_HANDOFF_ABANDON')
                    ),
                ),
                contestador=Count(
                    'id',
                    filter=q_out & (
                        Q(effective_status__iexact='AMD')
                        | Q(effective_status__iexact='EXIT_AMD')
                    ),
                ),
            )
            reporte = OrderedDict((k, 0) for k in labels_dialer)
            reporte[_('Discadas')] = agg['discadas'] or 0
            reporte[_('Atendidas')] = agg['atendidas'] or 0
            reporte[_('Conectadas al agente')] = self._llamadas_humano_only
            reporte[_('Perdidas')] = agg['perdidas'] or 0
            reporte[_('Contestador detectado')] = agg['contestador'] or 0
            # Manuales* = 0 (documentado)
        elif self.campana._es_manual:
            reporte = OrderedDict((k, 0) for k in labels_manual)
            for row in by_status:
                d = (row['direction'] or '').upper()
                s = (row['effective_status'] or '').upper()
                c = row['cantidad']
                if d != 'OUTBOUND':
                    continue
                reporte[_('Discadas')] += c
                if s == 'EXIT_ANSWERED':
                    reporte[_('Discadas atendidas')] += c
                else:
                    reporte[_('Discadas no atendidas')] += c
        else:
            # Preview
            reporte = OrderedDict((k, 0) for k in labels_preview)
            for row in by_status:
                d = (row['direction'] or '').upper()
                s = (row['effective_status'] or '').upper()
                c = row['cantidad']
                if d != 'OUTBOUND':
                    continue
                reporte[_('Discadas')] += c
                if s == 'EXIT_ANSWERED':
                    reporte[_('Conectadas')] += c
                else:
                    reporte[_('No conectadas')] += c

        self.reporte_detalle_llamadas = reporte

    def _no_atendidos(self, qs):
        # Una sola query: OUTBOUND no atendidos (status != EXIT_ANSWERED) por (status, hangup_cause)
        # + INBOUND EXIT_ABANDON y EXIT_TIMEOUT (mismos buckets que outbound, índices 8 y 10).
        filtro_na = (
            (Q(direction__iexact='OUTBOUND') & ~Q(effective_status__iexact='EXIT_ANSWERED'))
            | (
                Q(direction__iexact='INBOUND')
                & (
                    Q(effective_status__iexact='EXIT_ABANDON')
                    | Q(effective_status__iexact='EXIT_TIMEOUT')
                    | Q(effective_status__iexact='EXIT_HANDOFF_ABANDON')
                    | Q(effective_status__iexact='EXIT_HANDOFF_TIMEOUT')
                )
            )
        )
        by_direction_status_hangup = list(
            qs.filter(filtro_na)
            .values('direction', 'effective_status', 'hangup_cause')
            .annotate(cantidad=Count('id'))
        )
        reporte = OrderedDict((label, 0) for label in _NO_ATENDIDO_LABELS)
        total = 0
        for row in by_direction_status_hangup:
            d = (row['direction'] or '').upper()
            c = row['cantidad']
            if d == 'INBOUND':
                s = (row['effective_status'] or '').upper()
                if s in ('EXIT_ABANDON', 'EXIT_HANDOFF_ABANDON'):
                    reporte[_NO_ATENDIDO_LABELS[8]] += c
                elif s in ('EXIT_TIMEOUT', 'EXIT_HANDOFF_TIMEOUT'):
                    reporte[_NO_ATENDIDO_LABELS[10]] += c
            else:
                idx = _no_atendido_index(row['effective_status'], row['hangup_cause'])
                reporte[_NO_ATENDIDO_LABELS[idx]] += c
            total += c
        self.reporte_no_atendidos = reporte
        self._total_no_atendidos = total

    def _calificaciones_y_ventas(self, qs):
        """
        Calcula calificaciones CRM desde CalificacionCliente e HistoricalCalificacionCliente
        (misma lógica que V1 sin omnidialer). No usa InteractionsSummary.qualification_id.
        Criterio temporal: CalificacionCliente por modified__range; entrantes por
        HistoricalCalificacionCliente con history_date__range (inclusivo ambos extremos).
        Se asume fecha_desde/fecha_hasta timezone-aware.

        Entrantes: se deduplican por callid. Se excluyen callid nulo, vacío o solo
        espacios en blanco (Trim(callid)=''), de modo que no cuentan como calificación
        efectiva. El "último por callid" se decide incluyendo todos los history_type;
        después se excluyen las filas con history_type='-' (Deleted). Así create+delete
        en rango cuenta 0 (el último es el delete y se descarta).

        Calificaciones por agente: solo se muestran agentes en self.agentes_dict
        (asignados a la campaña vía cola).

        Llamadas atendidas sin calificación: atendida por humano = EXIT_ANSWERED y
        (agent_duration>0 o agent_id no nulo y != -1). Cualquiera de las dos basta.
        """
        opciones_orden = list(
            self.campana.opciones_calificacion.all().order_by('pk')
        )
        opcion_ids = [op.pk for op in opciones_orden]
        opcion_counts = {}  # opcion_id -> cantidad
        by_agent_opcion = []  # list of {agente_id, opcion_calificacion_id, cantidad}

        if self.campana.es_entrante:
            filtro_entrante = Q(
                opcion_calificacion_id__in=opcion_ids,
                history_date__range=(self.fecha_desde, self.fecha_hasta),
                callid__isnull=False,
            )
            qs_base = (
                HistoricalCalificacionCliente.objects.using('replica')
                .filter(filtro_entrante)
                .exclude(callid='')
                .annotate(_trim_callid=Trim('callid'))
                .exclude(_trim_callid='')
            )
            replica_features = connections['replica'].features
            use_window = getattr(replica_features, 'supports_over_clause', False)
            if use_window:
                base_hist = (
                    qs_base.annotate(
                        rn=Window(
                            expression=RowNumber(),
                            partition_by=[F('callid')],
                            order_by=[F('history_date').desc(), F('history_id').desc()],
                        )
                    )
                    .filter(rn=1)
                )
            else:
                latest_hist_id = qs_base.filter(
                    callid=OuterRef('callid'),
                ).order_by('-history_date', '-history_id').values('history_id')[:1]
                base_hist = qs_base.filter(
                    history_id=Subquery(latest_hist_id)
                )
            base_hist = base_hist.exclude(history_type='-')
            by_opcion = list(
                base_hist.values('opcion_calificacion_id')
                .annotate(cantidad=Count('history_id'))
            )
            for row in by_opcion:
                opcion_counts[row['opcion_calificacion_id']] = (
                    opcion_counts.get(row['opcion_calificacion_id'], 0) + row['cantidad']
                )
            by_agent_opcion = list(
                base_hist.values('agente_id', 'opcion_calificacion_id')
                .annotate(cantidad=Count('history_id'))
            )
        else:
            # No entrantes: solo CalificacionCliente (filtro por opcion_ids evita join)
            base_cal = CalificacionCliente.objects.using('replica').filter(
                opcion_calificacion_id__in=opcion_ids,
                modified__range=(self.fecha_desde, self.fecha_hasta),
            )
            by_opcion = list(
                base_cal.values('opcion_calificacion_id')
                .annotate(cantidad=Count('id'))
            )
            for row in by_opcion:
                opcion_counts[row['opcion_calificacion_id']] = (
                    opcion_counts.get(row['opcion_calificacion_id'], 0) + row['cantidad']
                )
            by_agent_opcion = list(
                base_cal.values('agente_id', 'opcion_calificacion_id')
                .annotate(cantidad=Count('id'))
            )

        # reporte_calificaciones_atendidas: orden de opciones + "Llamadas Atendidas sin calificación"
        reporte_atendidas = OrderedDict()
        for opcion in opciones_orden:
            reporte_atendidas[opcion.nombre] = opcion_counts.get(opcion.pk, 0)

        total_calificados = sum(opcion_counts.values())
        total_ventas = sum(
            opcion_counts.get(opcion.pk, 0)
            for opcion in opciones_orden
            if opcion.es_gestion()
        )

        # Atendidas por humano (VOICE, EXIT_ANSWERED, agent_duration>0 o agent_id válido)
        atendida_por_humano = Q(effective_status__iexact='EXIT_ANSWERED') & (
            Q(agent_duration__gt=0)
            | (Q(agent_id__isnull=False) & ~Q(agent_id=-1))
        )
        atendidas_humano = qs.filter(atendida_por_humano).count()
        self.llamadas_atendidas_sin_calificacion = max(
            0, atendidas_humano - total_calificados
        )
        reporte_atendidas[_('Llamadas Atendidas sin calificación')] = (
            self.llamadas_atendidas_sin_calificacion
        )
        self.reporte_calificaciones_atendidas = reporte_atendidas

        # Por agente: solo agentes con al menos una calificación (y en agentes_dict)
        dict_agentes = {}
        for row in by_agent_opcion:
            aid = row['agente_id']
            opcion_id = row['opcion_calificacion_id']
            c = row['cantidad']
            if aid is None or aid == -1:
                continue
            agente = self.agentes_dict.get(aid)
            if not agente:
                continue
            if aid not in dict_agentes:
                dict_agentes[aid] = {
                    'nombre': agente.user.get_full_name() or agente.user.username,
                    'totales_calificaciones': OrderedDict(
                        (op.nombre, 0) for op in opciones_orden
                    ),
                    'total_calificados': 0,
                    'total_gestionados': 0,
                }
            opcion = self.opciones_calificacion_campana.get(opcion_id)
            if opcion:
                dict_agentes[aid]['totales_calificaciones'][opcion.nombre] = (
                    dict_agentes[aid]['totales_calificaciones'].get(opcion.nombre, 0)
                    + c
                )
            dict_agentes[aid]['total_calificados'] += c
            if opcion and opcion.es_gestion():
                dict_agentes[aid]['total_gestionados'] += c

        self.reporte_calificaciones_agentes_dict = dict_agentes
        self.total_calificados = total_calificados
        self.total_ventas = total_ventas

    def _estadisticas_por_agente(self, qs):
        # Nota: Si el usuario descomentó la validación de es_dialer para usar Inbound, la mantenemos comentada.
        # if not self.campana.es_dialer:
        #     self.estadisticas_llamadas_por_agente = None
        #     return

        # Traemos los campos estrictamente necesarios a memoria
        llamadas = qs.values('agent_id', 'effective_status', 'channel_data')

        result = {}
        for row in llamadas:
            agentes_involucrados = set()

            # 1. Sumamos al agente físico (el último que tuvo la llamada)
            if row['agent_id'] and row['agent_id'] != -1:
                agentes_involucrados.add(row['agent_id'])

            # 2. Abrimos el JSON y sumamos a los agentes previos (los que transfirieron)
            c_data = row['channel_data'] or {}
            segmentos = c_data.get('agent_segments', [])
            for seg in segmentos:
                aid = seg.get('agent_id')
                if aid and aid != -1:
                    agentes_involucrados.add(aid)

            s = (row['effective_status'] or '').upper()

            # 3. Repartimos el crédito a TODOS los que participaron en esta llamada
            for aid in agentes_involucrados:
                if aid not in result:
                    agente = self.agentes_dict.get(aid)
                    if not agente:
                        continue
                    result[aid] = {
                        'agente_id': aid,
                        'nombre': agente.user.get_full_name() or agente.user.username,
                        'ofrecidas': 0,
                        'atendidas': 0,
                        'no_atendidas': 0,
                    }

                result[aid]['ofrecidas'] += 1
                if s == 'EXIT_ANSWERED':
                    result[aid]['atendidas'] += 1
                elif s != 'EXIT_TRANSFERRED_OUT':
                    result[aid]['no_atendidas'] += 1

        self.estadisticas_llamadas_por_agente = result or None

    def calcular_estadisticas_totales(self):
        qs = self._get_base_queryset()
        self._totales_llamadas(qs)
        self._agent_vs_bot_counts(qs)
        self._wa_humano_vs_ia_counts()
        self._whatsapp_recibidos_count()
        self._detalle_llamadas(qs)
        self._no_atendidos(qs)
        self._calificaciones_y_ventas(qs)
        self._estadisticas_por_agente(qs)
        qs_interacciones = self._get_queryset_interacciones_por_agente()
        self._interacciones_por_agente(qs_interacciones)
        self._performance_agentes(qs_interacciones)

    def _calcular_estadisticas(self, campana, fecha_desde, fecha_hasta):
        self.calcular_estadisticas_totales()

        calificaciones_nombre = list(self.reporte_calificaciones_atendidas.keys())
        calificaciones_cantidad = list(self.reporte_calificaciones_atendidas.values())
        total_asignados = sum(self.reporte_calificaciones_atendidas.values())

        # Keys son gettext_lazy; forzar str para serialización/rendering fuera de templates
        resultado_nombre = list(map(str, self.reporte_no_atendidos.keys()))
        resultado_cantidad = list(self.reporte_no_atendidos.values())
        total_no_atendidos = self._total_no_atendidos

        agentes_venta = self.reporte_calificaciones_agentes_dict
        total_calificados = self.total_calificados
        total_ventas = self.total_ventas
        calificaciones = tuple(
            op.nombre for op in campana.opciones_calificacion.all().order_by('pk')
        )

        llamadas_pendientes = self._llamadas_pendientes_extra
        llamadas_realizadas = self._llamadas_realizadas
        llamadas_recibidas = self._llamadas_recibidas if campana.es_entrante else None
        tiempo_promedio_espera = self._tiempo_promedio_espera if campana.es_entrante else None
        tiempo_promedio_abandono = self._tiempo_promedio_abandono if campana.es_entrante else None

        reporte = self.reporte_detalle_llamadas
        cantidad_llamadas = (list(reporte.keys()), list(reporte.values()))

        total_ofrecidas = 0
        total_atendidas = 0
        total_no_atendidas = 0
        if self.estadisticas_llamadas_por_agente:
            for st in self.estadisticas_llamadas_por_agente.values():
                total_ofrecidas += st['ofrecidas']
                total_atendidas += st['atendidas']
                total_no_atendidas += st['no_atendidas']
        else:
            # Sin desglose por agente (Inbound, Manual, Preview): mismos criterios que el detalle,
            # agregados sobre VOICE + effective_status (p. ej. EXIT_TRANSFERRED_OUT en origen).
            qs_voice = self._get_base_queryset()
            if campana.es_entrante:
                q_dir = Q(direction__iexact='INBOUND')
            else:
                q_dir = Q(direction__iexact='OUTBOUND')
            agg_tarjetas = qs_voice.aggregate(
                ofrecidas=Count('id', filter=q_dir),
                atendidas=Count(
                    'id',
                    filter=q_dir & Q(effective_status__iexact='EXIT_ANSWERED'),
                ),
            )
            total_ofrecidas = agg_tarjetas['ofrecidas'] or 0
            total_atendidas = agg_tarjetas['atendidas'] or 0
            total_no_atendidas = self._total_no_atendidos

        return {
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
            'estadisticas_llamadas_por_agente': self.estadisticas_llamadas_por_agente,
            'total_llamadas_ofrecidas': total_ofrecidas,
            'total_llamadas_atendidas': total_atendidas,
            'total_llamadas_no_atendidas': total_no_atendidas,
            'llamadas_conectadas_humano_only': self._llamadas_humano_only,
            'llamadas_conectadas_ai_only': self._llamadas_ai_only,
            'llamadas_conectadas_colaboracion': self._llamadas_colaboracion,
            'wa_conectadas_humano': self._wa_conectadas_humano,
            'wa_conectadas_ia': self._wa_conectadas_ia,
            'wa_conectadas_colaboracion': self._wa_conectadas_colaboracion,
            'whatsapp_recibidos': self._whatsapp_recibidos,
            'interacciones_por_agente': self.interacciones_por_agente,
            'performance_agentes': self.performance_agentes,
        }

    def _crear_serie_con_color(self, campana, cantidad_llamadas):
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

    def general_campana(self):
        estadisticas = self._calcular_estadisticas(
            self.campana, self.fecha_desde, self.fecha_hasta
        )
        if estadisticas:
            logger.info(_("Generando grafico calificaciones de campana por cliente "))

        reporte_campana_dir = os.path.join(settings.MEDIA_ROOT, "reporte_campana")
        os.makedirs(reporte_campana_dir, exist_ok=True)

        barra_campana_calificacion = pygal.Bar(
            show_legend=False, style=LightGreenStyle, width=1000, height=400
        )
        barra_campana_calificacion.title = _('Calificaciones de Clientes Contactados ')
        barra_campana_calificacion.x_labels = estadisticas['calificaciones_nombre']
        barra_campana_calificacion.add('cantidad', estadisticas['calificaciones_cantidad'])
        barra_campana_calificacion.render_to_png(
            os.path.join(
                reporte_campana_dir,
                "barra_campana_calificacion_{}.png".format(self.campana.id),
            )
        )
        barra_campana_calificacion = adicionar_render_unicode(barra_campana_calificacion)

        barra_campana_no_atendido = pygal.Bar(
            show_legend=False,
            style=DefaultStyle(colors=('#b93229',)),
            width=1000,
            height=400,
        )
        barra_campana_no_atendido.title = _('Cantidad de llamadas no atendidos ')
        barra_campana_no_atendido.x_labels = estadisticas['resultado_nombre']
        barra_campana_no_atendido.add('cantidad', estadisticas['resultado_cantidad'])
        barra_campana_no_atendido.render_to_png(
            os.path.join(
                reporte_campana_dir,
                "barra_campana_no_atendido_{}.png".format(self.campana.id),
            )
        )
        barra_campana_no_atendido = adicionar_render_unicode(barra_campana_no_atendido)

        barra_campana_llamadas = pygal.Bar(show_legend=False, width=1000, height=400)
        barra_campana_llamadas.title = _('Detalles de llamadas ')
        barra_campana_llamadas.x_labels = estadisticas['cantidad_llamadas'][0]
        barra_campana_llamadas.add(
            'cantidad',
            self._crear_serie_con_color(self.campana, estadisticas['cantidad_llamadas']),
        )
        barra_campana_llamadas = adicionar_render_unicode(barra_campana_llamadas)

        # Agent vs Bot: Humano, IA, Colaboración (EXIT_ANSWERED)
        labels_agent_vs_bot = (
            _('Llamadas conectadas al agente (Humano)'),
            _('Llamadas conectadas al Agente de IA'),
            _('Llamadas conectadas Colaboración IA + Humano'),
        )
        valores_agent_vs_bot = [
            estadisticas['llamadas_conectadas_humano_only'],
            estadisticas['llamadas_conectadas_ai_only'],
            estadisticas['llamadas_conectadas_colaboracion'],
        ]
        dict_agent_vs_bot_counter = list(zip(labels_agent_vs_bot, valores_agent_vs_bot))
        barra_agent_vs_bot = pygal.Bar(
            show_legend=False,
            width=1000,
            height=400,
            style=DefaultStyle(colors=('#2ecc71', '#3498db', '#e67e22')),
        )
        barra_agent_vs_bot.title = _('Llamadas conectadas: Humano vs IA')
        barra_agent_vs_bot.x_labels = [str(lbl) for lbl in labels_agent_vs_bot]
        barra_agent_vs_bot.add(_('Cantidad'), valores_agent_vs_bot)
        barra_agent_vs_bot.render_to_png(
            os.path.join(
                reporte_campana_dir,
                "barra_agent_vs_bot_{}.png".format(self.campana.id),
            )
        )
        barra_agent_vs_bot = adicionar_render_unicode(barra_agent_vs_bot)

        # WhatsApp conectadas: Humano vs IA (desde ConversacionWhatsapp)
        labels_wa_agent_vs_bot = (
            _('WhatsApp conectadas al Agente Humano'),
            _('WhatsApp conectadas al Agente de IA'),
            _('WhatsApp conectadas Colaboración IA + Humano'),
        )
        valores_wa_agent_vs_bot = [
            estadisticas['wa_conectadas_humano'],
            estadisticas['wa_conectadas_ia'],
            estadisticas['wa_conectadas_colaboracion'],
        ]
        dict_wa_agent_vs_bot_counter = list(
            zip(labels_wa_agent_vs_bot, valores_wa_agent_vs_bot)
        )
        barra_wa_agent_vs_bot = pygal.Bar(
            show_legend=False,
            width=1000,
            height=400,
            style=DefaultStyle(colors=('#2ecc71', '#3498db', '#e67e22')),
        )
        barra_wa_agent_vs_bot.title = _('WhatsApp conectadas: Humano vs IA')
        barra_wa_agent_vs_bot.x_labels = [str(lbl) for lbl in labels_wa_agent_vs_bot]
        barra_wa_agent_vs_bot.add(_('Cantidad'), valores_wa_agent_vs_bot)
        barra_wa_agent_vs_bot.render_to_png(
            os.path.join(
                reporte_campana_dir,
                "barra_wa_agent_vs_bot_{}.png".format(self.campana.id),
            )
        )
        barra_wa_agent_vs_bot = adicionar_render_unicode(barra_wa_agent_vs_bot)

        return {
            'estadisticas': estadisticas,
            'barra_campana_calificacion': barra_campana_calificacion,
            'dict_campana_counter': list(
                zip(
                    estadisticas['calificaciones_nombre'],
                    estadisticas['calificaciones_cantidad'],
                )
            ),
            'total_asignados': estadisticas['total_asignados'],
            'agentes_venta': estadisticas['agentes_venta'],
            'total_calificados': estadisticas['total_calificados'],
            'total_ventas': estadisticas['total_ventas'],
            'barra_campana_no_atendido': barra_campana_no_atendido,
            'dict_no_atendido_counter': list(
                zip(
                    estadisticas['resultado_nombre'],
                    estadisticas['resultado_cantidad'],
                )
            ),
            'total_no_atendidos': estadisticas['total_no_atendidos'],
            'calificaciones': estadisticas['calificaciones'],
            'barra_campana_llamadas': barra_campana_llamadas,
            'dict_llamadas_counter': list(
                zip(
                    estadisticas['cantidad_llamadas'][0],
                    estadisticas['cantidad_llamadas'][1],
                )
            ),
            'estadisticas_llamadas_por_agente': estadisticas.get(
                'estadisticas_llamadas_por_agente'
            ),
            'total_llamadas_ofrecidas': estadisticas.get('total_llamadas_ofrecidas', 0),
            'total_llamadas_atendidas': estadisticas.get('total_llamadas_atendidas', 0),
            'total_llamadas_no_atendidas': estadisticas.get(
                'total_llamadas_no_atendidas', 0
            ),
            'barra_agent_vs_bot': barra_agent_vs_bot,
            'dict_agent_vs_bot_counter': dict_agent_vs_bot_counter,
            'dict_wa_agent_vs_bot_counter': dict_wa_agent_vs_bot_counter,
            'barra_wa_agent_vs_bot': barra_wa_agent_vs_bot,
            'interacciones_por_agente': estadisticas.get('interacciones_por_agente', []),
            'performance_agentes': estadisticas.get('performance_agentes', []),
        }
