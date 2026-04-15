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

from collections import defaultdict
from decimal import Decimal

from datetime import date, datetime, timedelta

from django.core.paginator import Paginator
from django.urls import reverse
from django.db.models import (
    Count, Sum, Avg, Q, F, Value,
    ExpressionWrapper, DurationField, IntegerField,
    Exists, OuterRef,
)
from django.utils import timezone
from django.db.models.functions import (
    Coalesce, Extract, ExtractHour, TruncDate, TruncMonth,
)
from django.utils.dates import MONTHS
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.renderers import JSONRenderer

from ominicontacto_app.models import Campana, Grupo, AgenteProfile, OpcionCalificacion, CalificacionCliente
from ominicontacto_app.utiles import (
    fecha_hora_local,
    fecha_local,
    datetime_hora_minima_dia,
    datetime_hora_maxima_dia,
)
from reportes_app.models import (
    InteractionsSummary,
    InteractionTransfers,
    q_interaction_transfers_campaign_blind_consult,
)
from reportes_app.serializers import CentroContactoKPISerializer
from reportes_app.forms import ReporteCentroContactoForm
from reportes_app.services.whatsapp_tiempos_respuesta import (
    reporte_tiempos_respuesta_whatsapp,
    anotar_frt_y_duracion,
)
from whatsapp_app.models import ConversacionWhatsapp


def _decimal_to_float(value):
    """Convierte Decimal o None a float para el JSON."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _apply_interactions_summary_filters(
        queryset,
        start_date=None,
        end_date=None,
        campaign_scope=None,
        allow_null_campaigns=True,
        allowed_agent_ids=None,
        customer_id=None,
        address_query=None,
        direction_filter=None,
        channel_filter=None,
        hora_desde=None,
        hora_hasta=None,
        duracion_agente_min=None,
        duracion_bot_min=None):
    """Aplica el conjunto común de filtros sobre InteractionsSummary."""
    if direction_filter:
        queryset = queryset.filter(direction__iexact=direction_filter)
    if channel_filter and channel_filter.upper() == 'VOICE':
        queryset = queryset.filter(channel_type__iexact='VOICE')
    if campaign_scope is not None:
        if allow_null_campaigns:
            queryset = queryset.filter(
                Q(campaign_id__in=campaign_scope) | Q(campaign_id__isnull=True)
            )
        else:
            queryset = queryset.filter(campaign_id__in=campaign_scope)
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)
    return queryset


def _obtener_transferencias_entre_campanas_por_campana(
        start_date=None,
        end_date=None,
        selected_campaigns=None,
        visible_campaigns=None,
        allowed_agent_ids=None,
        customer_id=None,
        address_query=None,
        direction_filter=None,
        channel_filter=None,
        hora_desde=None,
        hora_hasta=None,
        duracion_agente_min=None,
        duracion_bot_min=None):
    """
    Cuenta transferencias entre campañas para la agregación por campaña.

    `Transfer Out` agrupa por la campaña de origen de la interacción.
    `Transfer In` agrupa por `destination_campaign_id`.
    Solo cuenta transferencias OK con destination_type CAMPAIGN y transfer_type BLIND o CONSULT.
    """
    source_campaign_scope = visible_campaigns if visible_campaigns is not None else selected_campaigns
    base_queryset = _apply_interactions_summary_filters(
        InteractionsSummary.objects.all(),
        start_date=start_date,
        end_date=end_date,
        campaign_scope=source_campaign_scope,
        allow_null_campaigns=False,
        allowed_agent_ids=allowed_agent_ids,
        customer_id=customer_id,
        address_query=address_query,
        direction_filter=direction_filter,
        channel_filter=channel_filter,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
        duracion_agente_min=duracion_agente_min,
        duracion_bot_min=duracion_bot_min,
    )
    interaction_campaign_pairs = list(base_queryset.values_list('interaction_id', 'campaign_id'))
    if not interaction_campaign_pairs:
        return {}, {}

    selected_campaigns_set = set(selected_campaigns) if selected_campaigns is not None else None
    source_campaign_by_interaction = {
        interaction_id: campaign_id
        for interaction_id, campaign_id in interaction_campaign_pairs
        if campaign_id is not None
    }
    transfers_queryset = InteractionTransfers.objects.filter(
        interaction_id__in=[interaction_id for interaction_id, _ in interaction_campaign_pairs],
    ).filter(q_interaction_transfers_campaign_blind_consult())

    transfer_in_counts = defaultdict(int)
    transfer_out_counts = defaultdict(int)
    for interaction_id, destination_campaign_id in transfers_queryset.values_list(
            'interaction_id', 'destination_campaign_id'):
        source_campaign_id = source_campaign_by_interaction.get(interaction_id)
        if (
            source_campaign_id is not None and
            (selected_campaigns_set is None or source_campaign_id in selected_campaigns_set)
        ):
            transfer_out_counts[source_campaign_id] += 1
        if (
            destination_campaign_id is not None and
            (selected_campaigns_set is None or destination_campaign_id in selected_campaigns_set)
        ):
            transfer_in_counts[destination_campaign_id] += 1

    return dict(transfer_in_counts), dict(transfer_out_counts)


def _obtener_metricas_inbound_transferidas_por_campana(
        start_date=None,
        end_date=None,
        selected_campaigns=None,
        allowed_agent_ids=None,
        customer_id=None,
        address_query=None,
        direction_filter=None,
        channel_filter=None,
        hora_desde=None,
        hora_hasta=None,
        duracion_agente_min=None,
        duracion_bot_min=None):
    """
    Cuenta estados inbound para campañas destino cuando la interacción llegó por transferencia.

    Usa el status final de InteractionsSummary para exponer en la campaña destino
    métricas como Respondidas, Expiradas y Abandonadas.
    Solo considera transferencias OK con destino CAMPAIGN y mecánica BLIND o CONSULT
    (mismo criterio que Transfer In/Out y que el campo transferred del reporte).
    Si campaign_id del resumen coincide con el destino de la transferencia, no suma
    (evita duplicar la agregación principal). Si el resumen sigue en la campaña origen
    y el status es EXIT_ANSWERED, la fila nativa de origen ya cuenta la respondida;
    en destino solo incrementa answered cuando hay evidencia de atención en destino
    (talk_time_after > 0 o segmento de agente post-transfer, con tolerancia de
    timestamps frente a created_at de la transferencia).
    """
    base_queryset = _apply_interactions_summary_filters(
        InteractionsSummary.objects.all(),
        start_date=start_date,
        end_date=end_date,
        campaign_scope=None,
        allow_null_campaigns=True,
        allowed_agent_ids=allowed_agent_ids,
        customer_id=customer_id,
        address_query=address_query,
        direction_filter=direction_filter,
        channel_filter=channel_filter,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
        duracion_agente_min=duracion_agente_min,
        duracion_bot_min=duracion_bot_min,
    )
    interaction_summary_rows = list(
        base_queryset.values_list('interaction_id', 'campaign_id', 'status', 'channel_data'),
    )
    if not interaction_summary_rows:
        return {}

    selected_campaigns_set = set(selected_campaigns) if selected_campaigns is not None else None
    status_by_interaction = {}
    summary_campaign_by_interaction = {}
    channel_data_by_interaction = {}
    for interaction_id, campaign_id, status, channel_data in interaction_summary_rows:
        status_by_interaction[interaction_id] = (status or '').strip().upper()
        summary_campaign_by_interaction[interaction_id] = campaign_id
        channel_data_by_interaction[interaction_id] = channel_data

    transfer_queryset = InteractionTransfers.objects.filter(
        interaction_id__in=list(status_by_interaction.keys()),
    ).filter(q_interaction_transfers_campaign_blind_consult())

    # Desfase típico entre created_at del registro de transferencia y start_ts del
    # segmento del agente en destino (ms); sin tolerancia se infiere abandono falso.
    _POST_TRANSFER_SEGMENT_TOLERANCE = timedelta(seconds=2)

    def _numeric_talk_time_after(val):
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _normalize_transfer_dt(transfer_created_at):
        if transfer_created_at is None:
            return None
        transfer_dt = transfer_created_at
        if timezone.is_naive(transfer_dt):
            transfer_dt = timezone.make_aware(
                transfer_dt, timezone.get_current_timezone(),
            )
        return transfer_dt

    def _segment_post_transfer_agent_attendance(interaction_id, transfer_created_at):
        """
        True si hay evidencia de atención por agente en destino tras la transferencia
        (mismo criterio que evita inferir abandono por desfase de timestamps).
        """
        transfer_dt = _normalize_transfer_dt(transfer_created_at)
        if transfer_dt is None:
            return False

        channel_data = channel_data_by_interaction.get(interaction_id)
        segments = _parse_agent_segments(channel_data)
        tol = _POST_TRANSFER_SEGMENT_TOLERANCE
        for seg in segments:
            agent_id = seg.get('agent_id') if isinstance(seg, dict) else None
            try:
                if agent_id is None or int(agent_id) == -1:
                    continue
            except (TypeError, ValueError):
                continue

            start_ts = _parse_iso_datetime_for_segment(seg.get('start_ts'))
            if start_ts is None:
                continue
            if timezone.is_naive(start_ts):
                start_ts = timezone.make_aware(
                    start_ts, timezone.get_current_timezone(),
                )

            if start_ts >= transfer_dt - tol:
                return True

            end_ts = _parse_iso_datetime_for_segment(seg.get('end_ts'))
            if end_ts is not None:
                if timezone.is_naive(end_ts):
                    end_ts = timezone.make_aware(
                        end_ts, timezone.get_current_timezone(),
                    )
                if end_ts > transfer_dt:
                    try:
                        td = seg.get('talk_duration')
                        if td is not None and float(td) > 0:
                            return True
                    except (TypeError, ValueError):
                        if (end_ts - start_ts).total_seconds() > 0:
                            return True
        return False

    def _inferred_abandon_exit_answered_destino(
            status, interaction_id, transfer_created_at, transfer_talk_time_after):
        """
        Abandono inferido en cola de campaña destino con status global EXIT_ANSWERED.
        No infiere si falta talk_time_after (dato ausente) o hay atención post-transfer.
        """
        if status != 'EXIT_ANSWERED':
            return False
        ntt = _numeric_talk_time_after(transfer_talk_time_after)
        if ntt is not None and ntt > 0:
            return False
        if _segment_post_transfer_agent_attendance(
                interaction_id, transfer_created_at):
            return False
        if ntt is None:
            return False
        return True

    metrics_by_campaign = defaultdict(lambda: {
        'received': 0,
        'answered': 0,
        'unanswered': 0,
        'expired': 0,
        'abandoned': 0,
    })
    for interaction_id, destination_campaign_id, transfer_created_at, transfer_talk_time_after in (
            transfer_queryset.values_list(
                'interaction_id',
                'destination_campaign_id',
                'created_at',
                'talk_time_after',
            )):
        if (
            selected_campaigns_set is not None and
            destination_campaign_id not in selected_campaigns_set
        ):
            continue
        status = status_by_interaction.get(interaction_id)
        if status is None:
            continue
        summary_campaign_id = summary_campaign_by_interaction.get(interaction_id)
        if summary_campaign_id == destination_campaign_id:
            continue
        row = metrics_by_campaign[destination_campaign_id]
        row['received'] += 1
        inferred_abandon_in_destination = _inferred_abandon_exit_answered_destino(
            status,
            interaction_id,
            transfer_created_at,
            transfer_talk_time_after,
        )
        ntt = _numeric_talk_time_after(transfer_talk_time_after)
        destino_atendida_exit_answered = status == 'EXIT_ANSWERED' and (
            (ntt is not None and ntt > 0) or
            _segment_post_transfer_agent_attendance(
                interaction_id, transfer_created_at,
            )
        )
        if destino_atendida_exit_answered:
            row['answered'] += 1
        if status != 'EXIT_ANSWERED' or inferred_abandon_in_destination:
            row['unanswered'] += 1
        if status in ('EXIT_TIMEOUT', 'EXIT_HANDOFF_TIMEOUT'):
            row['expired'] += 1
        if (
            status in ('EXIT_ABANDON', 'EXIT_HANDOFF_ABANDON', 'EXIT_ABANDON_WEL') or
            inferred_abandon_in_destination
        ):
            row['abandoned'] += 1

    return dict(metrics_by_campaign)


# Colores para el gráfico Donut Market Share Omnicanal (Chart.js)
OMNICHANNEL_CHART_COLORS = {
    'voz': '#3B82F6',
    'whatsapp': '#22C55E',
    'facebook': '#8B5CF6',
    'email': '#F97316',
}


def get_omnichannel_share_data(start_date=None, end_date=None, duracion_agente_min=None,
                              duracion_bot_min=None):
    """
    Calcula la distribución de interacciones por canal (Voz, WhatsApp, Facebook, Email)
    en un rango de fechas para el gráfico Donut (Market Share Omnicanal).
    Retorna un diccionario con total_volume, chart_data (listo para Chart.js) y shares (porcentajes).
    Si start_date o end_date son None, se usa el día actual (hoy) en timezone del servidor.
    - duracion_agente_min: si se indica (entero > 0), solo cuenta voz con agent_duration >= ese valor.
    - duracion_bot_min: si se indica (entero > 0), solo cuenta voz con bot_duration >= ese valor.
    """
    hoy = fecha_local(timezone.now())
    if start_date is None:
        start_date = hoy
    if end_date is None:
        end_date = hoy
    # Normalizar a inicio/fin de día si son date (no datetime)
    if isinstance(start_date, datetime):
        desde = start_date
    else:
        desde = datetime_hora_minima_dia(start_date)
    if isinstance(end_date, datetime):
        hasta = end_date
    else:
        hasta = datetime_hora_maxima_dia(end_date)

    count_voz = InteractionsSummary.objects.filter(
        channel_type='VOICE',
        start_time__gte=desde,
        start_time__lte=hasta,
    )
    if duracion_agente_min is not None:
        count_voz = count_voz.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        count_voz = count_voz.filter(bot_duration__gte=duracion_bot_min)
    count_voz = count_voz.count()
    count_whatsapp = ConversacionWhatsapp.objects.conversaciones_entrantes(
        desde, hasta
    ).count()
    count_facebook = InteractionsSummary.objects.filter(
        channel_type__in=['FBMSN', 'FACEBOOK_MSN'],
        start_time__gte=desde,
        start_time__lte=hasta,
    ).count()
    count_email = InteractionsSummary.objects.filter(
        channel_type='EMAIL',
        start_time__gte=desde,
        start_time__lte=hasta,
    ).count()

    total_volume = count_voz + count_whatsapp + count_facebook + count_email
    if total_volume > 0:
        pct_voz = count_voz / total_volume * 100
        pct_whatsapp = count_whatsapp / total_volume * 100
        pct_facebook = count_facebook / total_volume * 100
        pct_email = count_email / total_volume * 100
    else:
        pct_voz = pct_whatsapp = pct_facebook = pct_email = 0.0

    return {
        'total_volume': total_volume,
        'chart_data': {
            'labels': ['Voz', 'WhatsApp', 'Facebook', 'Email'],
            'datasets': [{
                'data': [count_voz, count_whatsapp, count_facebook, count_email],
                'backgroundColor': [
                    OMNICHANNEL_CHART_COLORS['voz'],
                    OMNICHANNEL_CHART_COLORS['whatsapp'],
                    OMNICHANNEL_CHART_COLORS['facebook'],
                    OMNICHANNEL_CHART_COLORS['email'],
                ],
            }],
        },
        'shares': {
            'voz': '{:.1f}%'.format(pct_voz),
            'whatsapp': '{:.1f}%'.format(pct_whatsapp),
            'facebook': '{:.1f}%'.format(pct_facebook),
            'email': '{:.1f}%'.format(pct_email),
        },
    }


def obtener_kpis_centro_contacto(campaign_id=None, start_date=None, end_date=None,
                                allowed_campaigns=None, allowed_agent_ids=None,
                                customer_id=None, address_query=None,
                                hora_desde=None, hora_hasta=None, duracion_agente_min=None,
                                duracion_bot_min=None):
    """
    Calcula los KPIs de centro de contacto para una campaña (o conjunto) y rango de fechas.
    Retorna un diccionario con contact_rate_pct, conversion_rate_pct, ..., totals.
    - campaign_id: si se indica, filtra por esa campaña.
    - allowed_campaigns: si campaign_id es None y se indica, filtra por campaign_id__in.
    - Si ambos son None, no filtra por campaña (métricas globales).
    - allowed_agent_ids: si se indica, filtra por esos agentes y SIEMPRE incluye
      interacciones sin agente (agent_id NULL o -1).
    - customer_id: si se indica, filtra por customer_id exacto.
    - address_query: si se indica, filtra por source_address/destination_address (icontains).
    start_date y end_date pueden ser datetime o None.
    """
    queryset = InteractionsSummary.objects.all()
    if campaign_id is not None:
        queryset = queryset.filter(campaign_id=campaign_id)
    elif allowed_campaigns is not None:
        queryset = queryset.filter(campaign_id__in=allowed_campaigns)
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)

    Q_outbound = Q(direction__iexact='OUTBOUND')
    Q_inbound = Q(direction__iexact='INBOUND')
    Q_answered = Q(status__iexact='EXIT_ANSWERED')
    # Abandonos / no atendidas en cola (incl. post-handoff voicebot)
    Q_abandoned = Q(
        status__in=[
            'EXIT_ABANDON',
            'EXIT_TIMEOUT',
            'EXIT_HANDOFF_ABANDON',
            'EXIT_HANDOFF_TIMEOUT',
        ]
    )
    Q_agent_gt0 = Q(agent_duration__gt=0)
    Q_agent_gt10 = Q(agent_duration__gt=10)
    Q_inbound_answered = Q_inbound & Q_answered
    Q_inbound_abandoned_gt5 = Q_inbound & Q_abandoned & Q(wait_conn_duration__gt=5)
    Q_inbound_timeout = Q_inbound & Q(
        status__in=['EXIT_TIMEOUT', 'EXIT_HANDOFF_TIMEOUT']
    )  # Entrantes expiradas
    Q_bot_only = Q(bot_duration__gt=0) & (Q(agent_duration__isnull=True) | Q(agent_duration=0))

    agg = queryset.aggregate(
        total=Count('id'),
        total_outbound=Count('id', filter=Q_outbound),
        outbound_answered=Count('id', filter=Q_outbound & Q_answered),
        total_inbound=Count('id', filter=Q_inbound),
        inbound_answered=Count('id', filter=Q_inbound_answered),
        inbound_abandoned_gt5=Count('id', filter=Q_inbound_abandoned_gt5),
        inbound_timeout=Count('id', filter=Q_inbound_timeout),
        attended_by_human=Count('id', filter=Q_agent_gt0),
        sales=Count('id', filter=Q(is_sale=True)),
        answered_agent_gt10=Count('id', filter=Q_answered & Q_agent_gt10),
        transferred=Count('id', filter=Q(is_transferred=True)),
        bot_only=Count('id', filter=Q_bot_only),
        count_agent_gt0=Count('id', filter=Q_agent_gt0),
        count_asa=Count('id', filter=Q_inbound_answered),
        sum_agent_duration=Sum('agent_duration', filter=Q_agent_gt0),
        sum_wait_conn_duration_asa=Sum('wait_conn_duration', filter=Q_inbound_answered),
        sum_bot_duration=Sum(Coalesce(F('bot_duration'), Value(Decimal('0')))),
    )

    total = agg['total'] or 0
    total_outbound = agg['total_outbound'] or 0
    outbound_answered = agg['outbound_answered'] or 0
    total_inbound = agg['total_inbound'] or 0
    inbound_abandoned_gt5 = agg['inbound_abandoned_gt5'] or 0
    attended_by_human = agg['attended_by_human'] or 0
    sales = agg['sales'] or 0
    answered_agent_gt10 = agg['answered_agent_gt10'] or 0
    transferred = agg['transferred'] or 0
    bot_only_count = agg['bot_only'] or 0
    count_agent_gt0 = agg['count_agent_gt0'] or 0
    count_asa = agg['count_asa'] or 0
    sum_agent_duration = agg['sum_agent_duration']
    sum_wait_conn_duration_asa = agg['sum_wait_conn_duration_asa']
    sum_bot_duration = agg['sum_bot_duration'] or Decimal('0')

    contact_rate_pct = (
        (float(outbound_answered) / total_outbound * 100) if total_outbound else None
    )
    conversion_rate_pct = (
        (float(sales) / attended_by_human * 100) if attended_by_human else None
    )
    rpc_pct = (
        (float(answered_agent_gt10) / total * 100) if total else None
    )
    aht = (
        _decimal_to_float(sum_agent_duration) / count_agent_gt0 if count_agent_gt0 else None
    )
    asa = (
        _decimal_to_float(sum_wait_conn_duration_asa) / count_asa if count_asa else None
    )
    abandon_rate_pct = (
        (float(inbound_abandoned_gt5) / total_inbound * 100) if total_inbound else None
    )
    inbound_timeout_count = agg['inbound_timeout'] or 0
    expire_rate_pct = (
        (float(inbound_timeout_count) / total_inbound * 100) if total_inbound else None
    )
    transfer_rate_pct = (
        (float(transferred) / attended_by_human * 100) if attended_by_human else None
    )
    bot_containment_pct = (
        (float(bot_only_count) / total * 100) if total else None
    )
    bot_hours = float(sum_bot_duration) / 3600.0

    totals = {
        'total': total,
        'total_outbound': total_outbound,
        'outbound_answered': outbound_answered,
        'total_inbound': total_inbound,
        'inbound_answered': agg['inbound_answered'] or 0,
        'inbound_abandoned_gt5': inbound_abandoned_gt5,
        'inbound_timeout': agg['inbound_timeout'] or 0,
        'attended_by_human': attended_by_human,
        'sales': sales,
        'answered_agent_gt10': answered_agent_gt10,
        'transferred': transferred,
        'bot_only': bot_only_count,
        'count_agent_gt0': count_agent_gt0,
        'count_asa': count_asa,
        'sum_agent_duration': _decimal_to_float(sum_agent_duration) if sum_agent_duration else 0,
        'sum_wait_conn_duration_asa': _decimal_to_float(sum_wait_conn_duration_asa) if sum_wait_conn_duration_asa else 0,
        'sum_bot_duration': _decimal_to_float(sum_bot_duration),
    }

    return {
        'contact_rate_pct': contact_rate_pct,
        'conversion_rate_pct': conversion_rate_pct,
        'rpc_pct': rpc_pct,
        'aht': aht,
        'asa': asa,
        'abandon_rate_pct': abandon_rate_pct,
        'expire_rate_pct': expire_rate_pct,
        'transfer_rate_pct': transfer_rate_pct,
        'bot_containment_pct': bot_containment_pct,
        'bot_hours': bot_hours,
        'totals': totals,
    }


def obtener_llamadas_por_campana(start_date=None, end_date=None,
                                 allowed_campaigns=None, allowed_agent_ids=None,
                                 customer_id=None, address_query=None,
                                 direction_filter=None,
                                 channel_filter=None,
                                 visible_campaigns=None,
                                 hora_desde=None, hora_hasta=None,
                                 duracion_agente_min=None, duracion_bot_min=None):
    """
    Agrupa interacciones por campaign_id con los mismos filtros que
    obtener_kpis_centro_contacto. Retorna lista de dicts con métricas por campaña:
    campaign_id, campaign_name, received, answered, unanswered, expired, abandoned,
    transferred, avg_wait_seconds, avg_talk_seconds, pct_answered, pct_unanswered,
    pct_expired, pct_abandoned, pct_transferred.
    Para campañas destino, también suma estados finales de interacciones que llegaron
    por transferencia recibida (destination_campaign_id).
    - direction_filter: si es 'INBOUND' o 'OUTBOUND', filtra por esa dirección; si None, no filtra.
    - channel_filter: si es 'VOICE', filtra por channel_type VOICE (solo llamadas de voz).
    - expired: EXIT_TIMEOUT y EXIT_HANDOFF_TIMEOUT; abandoned: EXIT_ABANDON y EXIT_HANDOFF_ABANDON.
    - Interacciones con transferencia OK hacia otra campaña (CAMPAIGN, BLIND/CONSULT; destination
      distinta del campaign_id de la fila) no cuentan en expired/abandoned/unanswered; cuentan
      como answered si EXIT_ANSWERED o si is_transferred y el xfer (el estado final puede ser
      distinto de EXIT_ANSWERED, p. ej. EXIT_TIMEOUT con agent_duration 0 en el resumen). Siguen en
      received y en transfer_out_count vía _obtener_transferencias_entre_campanas_por_campana.
    - transferred y pct_transferred: suma transfer_in_count + transfer_out_count (mismo criterio;
      no usa is_transferred del resumen).
    """
    queryset = _apply_interactions_summary_filters(
        InteractionsSummary.objects.all(),
        start_date=start_date,
        end_date=end_date,
        campaign_scope=allowed_campaigns,
        allow_null_campaigns=True,
        allowed_agent_ids=allowed_agent_ids,
        customer_id=customer_id,
        address_query=address_query,
        direction_filter=direction_filter,
        channel_filter=channel_filter,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
        duracion_agente_min=duracion_agente_min,
        duracion_bot_min=duracion_bot_min,
    )

    xfer_out_other_campaign = Exists(
        InteractionTransfers.objects.filter(
            interaction_id=OuterRef('interaction_id'),
        )
        .filter(q_interaction_transfers_campaign_blind_consult())
        .exclude(destination_campaign_id=OuterRef('campaign_id'))
    )
    queryset = queryset.annotate(_xfer_out_other_campaign=xfer_out_other_campaign)

    Q_xfer_out = Q(_xfer_out_other_campaign=True)
    Q_answered = Q(status__iexact='EXIT_ANSWERED') | (
        Q_xfer_out & Q(is_transferred=True)
    )
    Q_expired = Q(status__in=['EXIT_TIMEOUT', 'EXIT_HANDOFF_TIMEOUT']) & ~Q_xfer_out
    Q_abandoned = Q(status__in=['EXIT_ABANDON', 'EXIT_HANDOFF_ABANDON']) & ~Q_xfer_out

    rows = list(
        queryset
        .values('campaign_id')
        .annotate(
            received=Count('id'),
            answered=Count('id', filter=Q_answered),
            unanswered=Count('id', filter=(~Q(status__iexact='EXIT_ANSWERED')) & ~Q_xfer_out),
            expired=Count('id', filter=Q_expired),
            abandoned=Count('id', filter=Q_abandoned),
            avg_wait=Avg('wait_conn_duration', filter=Q_answered),
            avg_talk=Avg('agent_duration', filter=Q_answered),
        )
        .order_by('-received')
    )
    transfer_in_counts, transfer_out_counts = _obtener_transferencias_entre_campanas_por_campana(
        start_date=start_date,
        end_date=end_date,
        selected_campaigns=allowed_campaigns,
        visible_campaigns=visible_campaigns,
        allowed_agent_ids=allowed_agent_ids,
        customer_id=customer_id,
        address_query=address_query,
        direction_filter=direction_filter,
        channel_filter=channel_filter,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
        duracion_agente_min=duracion_agente_min,
        duracion_bot_min=duracion_bot_min,
    )
    transferred_in_metrics = _obtener_metricas_inbound_transferidas_por_campana(
        start_date=start_date,
        end_date=end_date,
        selected_campaigns=allowed_campaigns,
        allowed_agent_ids=allowed_agent_ids,
        customer_id=customer_id,
        address_query=address_query,
        direction_filter=direction_filter,
        channel_filter=channel_filter,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
        duracion_agente_min=duracion_agente_min,
        duracion_bot_min=duracion_bot_min,
    )

    campaign_ids = {r['campaign_id'] for r in rows if r['campaign_id'] is not None}
    campaign_ids.update(transfer_in_counts.keys())
    campaign_ids.update(transfer_out_counts.keys())
    campaign_ids.update(transferred_in_metrics.keys())
    names_map = {}
    if campaign_ids:
        names_map = dict(
            Campana.objects.filter(pk__in=campaign_ids).values_list('id', 'nombre')
        )

    result_by_campaign = {}
    for r in rows:
        cid = r['campaign_id']
        transfer_metrics = transferred_in_metrics.get(cid, {})
        received = r['received'] or 0
        effective_received = received + transfer_metrics.get('received', 0)
        answered = (r['answered'] or 0) + transfer_metrics.get('answered', 0)
        unanswered = (r['unanswered'] or 0) + transfer_metrics.get('unanswered', 0)
        expired = (r['expired'] or 0) + transfer_metrics.get('expired', 0)
        abandoned = (r['abandoned'] or 0) + transfer_metrics.get('abandoned', 0)
        if cid is not None:
            transferred = (
                transfer_in_counts.get(cid, 0) + transfer_out_counts.get(cid, 0)
            )
        else:
            transferred = 0
        avg_wait = r['avg_wait']
        avg_talk = r['avg_talk']

        if cid is None:
            campaign_name = _('Sin campaña')
        else:
            campaign_name = names_map.get(cid) or str(cid)

        pct_answered = (100.0 * answered / effective_received) if effective_received else 0.0
        pct_unanswered = (100.0 * unanswered / effective_received) if effective_received else 0.0
        pct_expired = (100.0 * expired / effective_received) if effective_received else 0.0
        pct_abandoned = (100.0 * abandoned / effective_received) if effective_received else 0.0
        pct_transferred = (100.0 * transferred / effective_received) if effective_received else 0.0

        result_by_campaign[cid] = {
            'campaign_id': cid,
            'campaign_name': campaign_name,
            'received': received,
            'effective_received': effective_received,
            'answered': answered,
            'unanswered': unanswered,
            'expired': expired,
            'abandoned': abandoned,
            'transferred': transferred,
            'avg_wait_seconds': _decimal_to_float(avg_wait) if avg_wait is not None else None,
            'avg_talk_seconds': _decimal_to_float(avg_talk) if avg_talk is not None else None,
            'pct_answered': round(pct_answered, 2),
            'pct_unanswered': round(pct_unanswered, 2),
            'pct_expired': round(pct_expired, 2),
            'pct_abandoned': round(pct_abandoned, 2),
            'pct_transferred': round(pct_transferred, 2),
            'transfer_in_count': transfer_in_counts.get(cid, 0),
            'transfer_out_count': transfer_out_counts.get(cid, 0),
        }

    all_transfer_campaign_ids = (
        set(transfer_in_counts.keys()) |
        set(transfer_out_counts.keys()) |
        set(transferred_in_metrics.keys())
    )
    for cid in sorted(all_transfer_campaign_ids):
        if cid in result_by_campaign:
            continue
        transfer_metrics = transferred_in_metrics.get(cid, {})
        received = 0
        effective_received = transfer_metrics.get('received', 0)
        answered = transfer_metrics.get('answered', 0)
        unanswered = transfer_metrics.get('unanswered', 0)
        expired = transfer_metrics.get('expired', 0)
        abandoned = transfer_metrics.get('abandoned', 0)
        transferred = (
            transfer_in_counts.get(cid, 0) + transfer_out_counts.get(cid, 0)
        )
        result_by_campaign[cid] = {
            'campaign_id': cid,
            'campaign_name': names_map.get(cid) or str(cid),
            'received': received,
            'effective_received': effective_received,
            'answered': answered,
            'unanswered': unanswered,
            'expired': expired,
            'abandoned': abandoned,
            'transferred': transferred,
            'avg_wait_seconds': None,
            'avg_talk_seconds': None,
            'pct_answered': round((100.0 * answered / effective_received), 2) if effective_received else 0.0,
            'pct_unanswered': round((100.0 * unanswered / effective_received), 2) if effective_received else 0.0,
            'pct_expired': round((100.0 * expired / effective_received), 2) if effective_received else 0.0,
            'pct_abandoned': round((100.0 * abandoned / effective_received), 2) if effective_received else 0.0,
            'pct_transferred': round(
                (100.0 * transferred / effective_received), 2,
            ) if effective_received else 0.0,
            'transfer_in_count': transfer_in_counts.get(cid, 0),
            'transfer_out_count': transfer_out_counts.get(cid, 0),
        }
    result = list(result_by_campaign.values())
    result.sort(key=lambda row: (-row['received'], row['campaign_name']))
    return result


def obtener_llamadas_salientes_por_campana(start_date=None, end_date=None,
                                           allowed_campaigns=None, allowed_agent_ids=None,
                                           customer_id=None, address_query=None,
                                           hora_desde=None, hora_hasta=None,
                                           duracion_agente_min=None, duracion_bot_min=None):
    """
    KPIs de llamadas salientes (OUTBOUND, VOICE) por campaña para el reporte Egresos/Voz/Campañas.
    Retorna lista de dicts con una fila por campaña: campaign_id, campaign_name, sent (enviadas),
    conectadas (EXIT_ANSWERED), canceladas (EXIT_CANCEL), no_atiende (EXIT_NOANSWER), ocupado
    (EXIT_BUSY), contestador (EXIT_AMD), shortcall (EXIT_SHORTCALL), congestion (EXIT_CONGESTION),
    otro_error (resto), transferred, avg_wait_seconds, avg_talk_seconds, pct_conectadas,
    pct_no_conectadas.
    """
    queryset = InteractionsSummary.objects.filter(
        direction__iexact='OUTBOUND',
        channel_type__iexact='VOICE',
    )
    if allowed_campaigns is not None:
        queryset = queryset.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)

    Q_answered = Q(status__iexact='EXIT_ANSWERED')
    rows = (
        queryset
        .values('campaign_id')
        .annotate(
            sent=Count('id'),
            conectadas=Count('id', filter=Q_answered),
            canceladas=Count('id', filter=Q(status__iexact='CANCEL')),
            no_atiende=Count('id', filter=Q(status__iexact='NOANSWER')),
            ocupado=Count('id', filter=Q(status__iexact='BUSY')),
            contestador=Count('id', filter=Q(status__iexact='EXIT_AMD')),
            shortcall=Count('id', filter=Q(status__iexact='EXIT_SHORTCALL')),
            congestion=Count('id', filter=Q(status__iexact='CONGESTION')),
            transferred=Count('id', filter=Q(is_transferred=True)),
            avg_wait=Avg('wait_conn_duration', filter=Q_answered),
            avg_talk=Avg('agent_duration', filter=Q_answered),
        )
        .order_by('-sent')
    )

    campaign_ids = [r['campaign_id'] for r in rows if r['campaign_id'] is not None]
    names_map = {}
    if campaign_ids:
        names_map = dict(
            Campana.objects.filter(pk__in=campaign_ids).values_list('id', 'nombre')
        )

    result = []
    for r in rows:
        cid = r['campaign_id']
        sent = r['sent'] or 0
        conectadas = r['conectadas'] or 0
        canceladas = r['canceladas'] or 0
        no_atiende = r['no_atiende'] or 0
        ocupado = r['ocupado'] or 0
        contestador = r['contestador'] or 0
        shortcall = r['shortcall'] or 0
        congestion = r['congestion'] or 0
        transferred = r['transferred'] or 0
        otro_error = max(
            0,
            sent - conectadas - canceladas - no_atiende - ocupado - contestador - shortcall - congestion
        )
        avg_wait = r['avg_wait']
        avg_talk = r['avg_talk']

        if cid is None:
            campaign_name = _('Sin campaña')
        else:
            campaign_name = names_map.get(cid) or str(cid)

        pct_conectadas = (100.0 * conectadas / sent) if sent else 0.0
        pct_no_conectadas = (100.0 * (sent - conectadas) / sent) if sent else 0.0

        result.append({
            'campaign_id': cid,
            'campaign_name': campaign_name,
            'sent': sent,
            'conectadas': conectadas,
            'canceladas': canceladas,
            'no_atiende': no_atiende,
            'ocupado': ocupado,
            'contestador': contestador,
            'shortcall': shortcall,
            'congestion': congestion,
            'otro_error': otro_error,
            'transferred': transferred,
            'avg_wait_seconds': _decimal_to_float(avg_wait) if avg_wait is not None else None,
            'avg_talk_seconds': _decimal_to_float(avg_talk) if avg_talk is not None else None,
            'pct_conectadas': round(pct_conectadas, 2),
            'pct_no_conectadas': round(pct_no_conectadas, 2),
        })
    return result


def _queryset_llamadas_salientes_voice(start_date=None, end_date=None,
                                       allowed_campaigns=None, allowed_agent_ids=None,
                                       customer_id=None, address_query=None,
                                       hora_desde=None, hora_hasta=None,
                                       duracion_agente_min=None, duracion_bot_min=None):
    """Base queryset OUTBOUND + VOICE con filtros opcionales (reutilizado por salientes por hora/día/mes)."""
    queryset = InteractionsSummary.objects.filter(
        direction__iexact='OUTBOUND',
        channel_type__iexact='VOICE',
    )
    if allowed_campaigns is not None:
        queryset = queryset.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)
    return queryset


def obtener_llamadas_salientes_por_hora(start_date=None, end_date=None,
                                        allowed_campaigns=None, allowed_agent_ids=None,
                                        customer_id=None, address_query=None,
                                        hora_desde=None, hora_hasta=None,
                                        duracion_agente_min=None, duracion_bot_min=None):
    """
    Llamadas salientes (OUTBOUND, VOICE) agregadas por hora del día.
    Retorna lista de 24 dicts con hour, hour_label, sent, conectadas, canceladas,
    no_atiende, ocupado, contestador, shortcall, congestion, otro_error, transferred,
    avg_wait_seconds, avg_talk_seconds, pct_conectadas, pct_no_conectadas.
    """
    queryset = _queryset_llamadas_salientes_voice(
        start_date=start_date, end_date=end_date,
        allowed_campaigns=allowed_campaigns, allowed_agent_ids=allowed_agent_ids,
        customer_id=customer_id, address_query=address_query,
        hora_desde=hora_desde, hora_hasta=hora_hasta,
        duracion_agente_min=duracion_agente_min,
        duracion_bot_min=duracion_bot_min,
    )
    Q_answered = Q(status__iexact='EXIT_ANSWERED')
    rows = (
        queryset
        .annotate(hour=ExtractHour('start_time'))
        .values('hour')
        .annotate(
            sent=Count('id'),
            conectadas=Count('id', filter=Q_answered),
            canceladas=Count('id', filter=Q(status__iexact='EXIT_CANCEL')),
            no_atiende=Count('id', filter=Q(status__iexact='EXIT_NOANSWER')),
            ocupado=Count('id', filter=Q(status__iexact='EXIT_BUSY')),
            contestador=Count('id', filter=Q(status__iexact='EXIT_AMD')),
            shortcall=Count('id', filter=Q(status__iexact='EXIT_SHORTCALL')),
            congestion=Count('id', filter=Q(status__iexact='EXIT_CONGESTION')),
            transferred=Count('id', filter=Q(is_transferred=True)),
            avg_wait=Avg('wait_conn_duration', filter=Q_answered),
            avg_talk=Avg('agent_duration', filter=Q_answered),
        )
        .order_by('hour')
    )
    data_by_hour = {}
    for r in rows:
        h = r['hour']
        if h is None:
            continue
        h = int(h) % 24
        sent = r['sent'] or 0
        conectadas = r['conectadas'] or 0
        canceladas = r['canceladas'] or 0
        no_atiende = r['no_atiende'] or 0
        ocupado = r['ocupado'] or 0
        contestador = r['contestador'] or 0
        shortcall = r['shortcall'] or 0
        congestion = r['congestion'] or 0
        transferred = r['transferred'] or 0
        otro_error = max(
            0,
            sent - conectadas - canceladas - no_atiende - ocupado - contestador - shortcall - congestion
        )
        avg_wait = r['avg_wait']
        avg_talk = r['avg_talk']
        pct_conectadas = (100.0 * conectadas / sent) if sent else 0.0
        pct_no_conectadas = (100.0 * (sent - conectadas) / sent) if sent else 0.0
        data_by_hour[h] = {
            'sent': sent,
            'conectadas': conectadas,
            'canceladas': canceladas,
            'no_atiende': no_atiende,
            'ocupado': ocupado,
            'contestador': contestador,
            'shortcall': shortcall,
            'congestion': congestion,
            'otro_error': otro_error,
            'transferred': transferred,
            'avg_wait_seconds': _decimal_to_float(avg_wait) if avg_wait is not None else None,
            'avg_talk_seconds': _decimal_to_float(avg_talk) if avg_talk is not None else None,
            'pct_conectadas': round(pct_conectadas, 2),
            'pct_no_conectadas': round(pct_no_conectadas, 2),
        }
    result = []
    for h in range(24):
        hour_label = '{0:02d}:00'.format(h)
        if h in data_by_hour:
            row = data_by_hour[h].copy()
            row['hour'] = h
            row['hour_label'] = hour_label
        else:
            row = {
                'hour': h,
                'hour_label': hour_label,
                'sent': 0,
                'conectadas': 0,
                'canceladas': 0,
                'no_atiende': 0,
                'ocupado': 0,
                'contestador': 0,
                'shortcall': 0,
                'congestion': 0,
                'otro_error': 0,
                'transferred': 0,
                'avg_wait_seconds': None,
                'avg_talk_seconds': None,
                'pct_conectadas': 0.0,
                'pct_no_conectadas': 0.0,
            }
        result.append(row)
    return result


def obtener_llamadas_salientes_por_dia(start_date=None, end_date=None,
                                       allowed_campaigns=None, allowed_agent_ids=None,
                                       customer_id=None, address_query=None,
                                       hora_desde=None, hora_hasta=None,
                                       duracion_agente_min=None, duracion_bot_min=None):
    """
    Llamadas salientes (OUTBOUND, VOICE) agregadas por día.
    Retorna lista de dicts (una fila por día en el rango) con date, date_label, sent,
    conectadas, canceladas, no_atiende, ocupado, contestador, shortcall, congestion,
    otro_error, transferred, avg_wait_seconds, avg_talk_seconds, pct_conectadas, pct_no_conectadas.
    """
    from datetime import timedelta
    queryset = _queryset_llamadas_salientes_voice(
        start_date=start_date, end_date=end_date,
        allowed_campaigns=allowed_campaigns, allowed_agent_ids=allowed_agent_ids,
        customer_id=customer_id, address_query=address_query,
        hora_desde=hora_desde, hora_hasta=hora_hasta,
        duracion_agente_min=duracion_agente_min,
        duracion_bot_min=duracion_bot_min,
    )
    Q_answered = Q(status__iexact='EXIT_ANSWERED')
    rows = (
        queryset
        .annotate(day=TruncDate('start_time'))
        .values('day')
        .annotate(
            sent=Count('id'),
            conectadas=Count('id', filter=Q_answered),
            canceladas=Count('id', filter=Q(status__iexact='EXIT_CANCEL')),
            no_atiende=Count('id', filter=Q(status__iexact='EXIT_NOANSWER')),
            ocupado=Count('id', filter=Q(status__iexact='EXIT_BUSY')),
            contestador=Count('id', filter=Q(status__iexact='EXIT_AMD')),
            shortcall=Count('id', filter=Q(status__iexact='EXIT_SHORTCALL')),
            congestion=Count('id', filter=Q(status__iexact='EXIT_CONGESTION')),
            transferred=Count('id', filter=Q(is_transferred=True)),
            avg_wait=Avg('wait_conn_duration', filter=Q_answered),
            avg_talk=Avg('agent_duration', filter=Q_answered),
        )
        .order_by('day')
    )
    data_by_day = {}
    for r in rows:
        day = r['day']
        if day is None:
            continue
        sent = r['sent'] or 0
        conectadas = r['conectadas'] or 0
        canceladas = r['canceladas'] or 0
        no_atiende = r['no_atiende'] or 0
        ocupado = r['ocupado'] or 0
        contestador = r['contestador'] or 0
        shortcall = r['shortcall'] or 0
        congestion = r['congestion'] or 0
        transferred = r['transferred'] or 0
        otro_error = max(
            0,
            sent - conectadas - canceladas - no_atiende - ocupado - contestador - shortcall - congestion
        )
        avg_wait = r['avg_wait']
        avg_talk = r['avg_talk']
        pct_conectadas = (100.0 * conectadas / sent) if sent else 0.0
        pct_no_conectadas = (100.0 * (sent - conectadas) / sent) if sent else 0.0
        data_by_day[day] = {
            'date': day,
            'date_label': day.strftime('%d/%m'),
            'sent': sent,
            'conectadas': conectadas,
            'canceladas': canceladas,
            'no_atiende': no_atiende,
            'ocupado': ocupado,
            'contestador': contestador,
            'shortcall': shortcall,
            'congestion': congestion,
            'otro_error': otro_error,
            'transferred': transferred,
            'avg_wait_seconds': _decimal_to_float(avg_wait) if avg_wait is not None else None,
            'avg_talk_seconds': _decimal_to_float(avg_talk) if avg_talk is not None else None,
            'pct_conectadas': round(pct_conectadas, 2),
            'pct_no_conectadas': round(pct_no_conectadas, 2),
        }
    result = []
    if start_date and end_date:
        start_d = start_date.date() if hasattr(start_date, 'date') else start_date
        end_d = end_date.date() if hasattr(end_date, 'date') else end_date
        d = start_d
        while d <= end_d:
            if d in data_by_day:
                result.append(data_by_day[d].copy())
            else:
                result.append({
                    'date': d,
                    'date_label': d.strftime('%d/%m'),
                    'sent': 0,
                    'conectadas': 0,
                    'canceladas': 0,
                    'no_atiende': 0,
                    'ocupado': 0,
                    'contestador': 0,
                    'shortcall': 0,
                    'congestion': 0,
                    'otro_error': 0,
                    'transferred': 0,
                    'avg_wait_seconds': None,
                    'avg_talk_seconds': None,
                    'pct_conectadas': 0.0,
                    'pct_no_conectadas': 0.0,
                })
            d += timedelta(days=1)
    else:
        for day in sorted(data_by_day.keys()):
            result.append(data_by_day[day].copy())
    return result


def obtener_llamadas_salientes_por_mes(start_date=None, end_date=None,
                                       allowed_campaigns=None, allowed_agent_ids=None,
                                       customer_id=None, address_query=None,
                                       hora_desde=None, hora_hasta=None,
                                       duracion_agente_min=None, duracion_bot_min=None):
    """
    Llamadas salientes (OUTBOUND, VOICE) agregadas por mes.
    Retorna lista de dicts (una fila por mes) con month, month_label, sent, conectadas,
    canceladas, no_atiende, ocupado, contestador, shortcall, congestion, otro_error,
    transferred, avg_wait_seconds, avg_talk_seconds, pct_conectadas, pct_no_conectadas.
    """
    from datetime import date
    queryset = _queryset_llamadas_salientes_voice(
        start_date=start_date, end_date=end_date,
        allowed_campaigns=allowed_campaigns, allowed_agent_ids=allowed_agent_ids,
        customer_id=customer_id, address_query=address_query,
        hora_desde=hora_desde, hora_hasta=hora_hasta,
        duracion_agente_min=duracion_agente_min,
        duracion_bot_min=duracion_bot_min,
    )
    Q_answered = Q(status__iexact='EXIT_ANSWERED')
    rows = (
        queryset
        .annotate(month=TruncMonth('start_time'))
        .values('month')
        .annotate(
            sent=Count('id'),
            conectadas=Count('id', filter=Q_answered),
            canceladas=Count('id', filter=Q(status__iexact='EXIT_CANCEL')),
            no_atiende=Count('id', filter=Q(status__iexact='EXIT_NOANSWER')),
            ocupado=Count('id', filter=Q(status__iexact='EXIT_BUSY')),
            contestador=Count('id', filter=Q(status__iexact='EXIT_AMD')),
            shortcall=Count('id', filter=Q(status__iexact='EXIT_SHORTCALL')),
            congestion=Count('id', filter=Q(status__iexact='EXIT_CONGESTION')),
            transferred=Count('id', filter=Q(is_transferred=True)),
            avg_wait=Avg('wait_conn_duration', filter=Q_answered),
            avg_talk=Avg('agent_duration', filter=Q_answered),
        )
        .order_by('month')
    )
    data_by_month = {}
    for r in rows:
        month_date = r['month']
        if month_date is None:
            continue
        sent = r['sent'] or 0
        conectadas = r['conectadas'] or 0
        canceladas = r['canceladas'] or 0
        no_atiende = r['no_atiende'] or 0
        ocupado = r['ocupado'] or 0
        contestador = r['contestador'] or 0
        shortcall = r['shortcall'] or 0
        congestion = r['congestion'] or 0
        transferred = r['transferred'] or 0
        otro_error = max(
            0,
            sent - conectadas - canceladas - no_atiende - ocupado - contestador - shortcall - congestion
        )
        avg_wait = r['avg_wait']
        avg_talk = r['avg_talk']
        pct_conectadas = (100.0 * conectadas / sent) if sent else 0.0
        pct_no_conectadas = (100.0 * (sent - conectadas) / sent) if sent else 0.0
        month_label = MONTHS[month_date.month] if 1 <= month_date.month <= 12 else month_date.strftime('%B')
        data_by_month[month_date] = {
            'month': month_date,
            'month_label': month_label,
            'sent': sent,
            'conectadas': conectadas,
            'canceladas': canceladas,
            'no_atiende': no_atiende,
            'ocupado': ocupado,
            'contestador': contestador,
            'shortcall': shortcall,
            'congestion': congestion,
            'otro_error': otro_error,
            'transferred': transferred,
            'avg_wait_seconds': _decimal_to_float(avg_wait) if avg_wait is not None else None,
            'avg_talk_seconds': _decimal_to_float(avg_talk) if avg_talk is not None else None,
            'pct_conectadas': round(pct_conectadas, 2),
            'pct_no_conectadas': round(pct_no_conectadas, 2),
        }
    result = []
    if start_date and end_date:
        start_d = start_date.date() if hasattr(start_date, 'date') else start_date
        end_d = end_date.date() if hasattr(end_date, 'date') else end_date
        y, m = start_d.year, start_d.month
        end_y, end_m = end_d.year, end_d.month
        while (y, m) <= (end_y, end_m):
            first = date(y, m, 1)
            if first in data_by_month:
                result.append(data_by_month[first].copy())
            else:
                result.append({
                    'month': first,
                    'month_label': MONTHS[m] if 1 <= m <= 12 else first.strftime('%B'),
                    'sent': 0,
                    'conectadas': 0,
                    'canceladas': 0,
                    'no_atiende': 0,
                    'ocupado': 0,
                    'contestador': 0,
                    'shortcall': 0,
                    'congestion': 0,
                    'otro_error': 0,
                    'transferred': 0,
                    'avg_wait_seconds': None,
                    'avg_talk_seconds': None,
                    'pct_conectadas': 0.0,
                    'pct_no_conectadas': 0.0,
                })
            if m == 12:
                y, m = y + 1, 1
            else:
                m += 1
    else:
        for month_date in sorted(data_by_month.keys()):
            result.append(data_by_month[month_date].copy())
    return result


def obtener_whatsapp_mensajes_por_campana(start_date=None, end_date=None,
                                          allowed_campaigns=None, allowed_agent_ids=None,
                                          address_query=None, hora_desde=None, hora_hasta=None):
    """
    Agrupa conversaciones WhatsApp entrantes por campaña para el reporte centro de contacto.
    Retorna lista de dicts con: nombre_campana, recibidos, respondidos, no_respondidos,
    avg_frt_segundos, avg_duracion_segundos, pct_respondidos, pct_no_respondidos.
    """
    if start_date is None or end_date is None:
        return []
    qs = ConversacionWhatsapp.objects.filter(saliente=False)
    qs = qs.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs = qs.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs = qs.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs = qs.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs = qs.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs = qs.filter(timestamp__time__lte=hora_hasta)

    # Conteos por campaña
    rows = list(
        qs.values('campana_id')
        .annotate(
            recibidos=Count('id'),
            respondidos=Count('id', filter=Q(atendida=True)),
        )
        .order_by('campana_id')
    )
    if not rows:
        return []

    campaign_ids = [r['campana_id'] for r in rows if r['campana_id'] is not None]
    names_map = {}
    if campaign_ids:
        names_map = dict(
            Campana.objects.filter(pk__in=campaign_ids).values_list('id', 'nombre')
        )

    # FRT promedio por campaña (desde reporte_tiempos_respuesta_whatsapp)
    qs_frt = reporte_tiempos_respuesta_whatsapp(start_date, end_date, sla_segundos=120)
    qs_frt = qs_frt.filter(frt_segundos__isnull=False)
    if allowed_campaigns is not None:
        qs_frt = qs_frt.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_frt = qs_frt.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_frt = qs_frt.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_frt = qs_frt.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_frt = qs_frt.filter(timestamp__time__lte=hora_hasta)
    frt_por_campana = dict(
        qs_frt.values('campana_id').annotate(avg_frt=Avg('frt_segundos')).values_list(
            'campana_id', 'avg_frt'
        )
    )

    # Duración promedio (date_last_interaction - timestamp) por campaña, solo atendidas
    qs_dura = ConversacionWhatsapp.objects.filter(
        saliente=False, atendida=True, date_last_interaction__isnull=False
    )
    qs_dura = qs_dura.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_dura = qs_dura.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_dura = qs_dura.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_dura = qs_dura.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_dura = qs_dura.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_dura = qs_dura.filter(timestamp__time__lte=hora_hasta)
    qs_dura = qs_dura.annotate(
        _duracion=ExpressionWrapper(
            F('date_last_interaction') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        duracion_segundos=ExpressionWrapper(
            Extract(F('_duracion'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    duracion_por_campana = dict(
        qs_dura.values('campana_id')
        .annotate(avg_duracion=Avg('duracion_segundos'))
        .values_list('campana_id', 'avg_duracion')
    )

    result = []
    for r in rows:
        cid = r['campana_id']
        recibidos = r['recibidos'] or 0
        respondidos = r['respondidos'] or 0
        no_respondidos = recibidos - respondidos
        nombre_campana = _('Sin campaña') if cid is None else names_map.get(cid) or str(cid)
        avg_frt = _decimal_to_float(frt_por_campana.get(cid))
        avg_duracion = _decimal_to_float(duracion_por_campana.get(cid))
        pct_respondidos = round(100.0 * respondidos / recibidos, 1) if recibidos else None
        pct_no_respondidos = round(100.0 * no_respondidos / recibidos, 1) if recibidos else None
        result.append({
            'nombre_campana': nombre_campana,
            'recibidos': recibidos,
            'respondidos': respondidos,
            'no_respondidos': no_respondidos,
            'avg_frt_segundos': avg_frt,
            'avg_duracion_segundos': avg_duracion,
            'pct_respondidos': pct_respondidos,
            'pct_no_respondidos': pct_no_respondidos,
        })
    result.sort(key=lambda x: x['recibidos'], reverse=True)
    return result


def obtener_whatsapp_egresos_mensajes_por_campana(start_date=None, end_date=None,
                                                    allowed_campaigns=None, allowed_agent_ids=None,
                                                    address_query=None, hora_desde=None, hora_hasta=None):
    """
    Agrupa conversaciones WhatsApp salientes (egresos) por campaña para el reporte centro de contacto.
    Retorna lista de dicts con: nombre_campana, enviados, respondidos, no_respondidos,
    avg_frt_segundos (tiempo espera hasta primera respuesta del cliente), avg_duracion_segundos,
    pct_respondidos, pct_no_respondidos.
    """
    if start_date is None or end_date is None:
        return []
    qs = ConversacionWhatsapp.objects.filter(saliente=True)
    qs = qs.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs = qs.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs = qs.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs = qs.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs = qs.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs = qs.filter(timestamp__time__lte=hora_hasta)

    # Conteos por campaña
    rows = list(
        qs.values('campana_id')
        .annotate(
            enviados=Count('id'),
            respondidos=Count('id', filter=Q(atendida=True)),
        )
        .order_by('campana_id')
    )
    if not rows:
        return []

    campaign_ids = [r['campana_id'] for r in rows if r['campana_id'] is not None]
    names_map = {}
    if campaign_ids:
        names_map = dict(
            Campana.objects.filter(pk__in=campaign_ids).values_list('id', 'nombre')
        )

    # T Espera prom. (egresos): tiempo hasta primera respuesta del cliente = timestamp_primer_mensaje_cliente - timestamp
    qs_espera = reporte_tiempos_respuesta_whatsapp(start_date, end_date, sla_segundos=120)
    qs_espera = qs_espera.filter(saliente=True)
    qs_espera = qs_espera.filter(timestamp_primer_mensaje_cliente__isnull=False)
    if allowed_campaigns is not None:
        qs_espera = qs_espera.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_espera = qs_espera.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_espera = qs_espera.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_espera = qs_espera.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_espera = qs_espera.filter(timestamp__time__lte=hora_hasta)
    qs_espera = qs_espera.annotate(
        _espera_delta=ExpressionWrapper(
            F('timestamp_primer_mensaje_cliente') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        espera_segundos=ExpressionWrapper(
            Extract(F('_espera_delta'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    espera_por_campana = dict(
        qs_espera.values('campana_id')
        .annotate(avg_espera=Avg('espera_segundos'))
        .values_list('campana_id', 'avg_espera')
    )

    # Duración promedio (date_last_interaction - timestamp) por campaña, solo atendidas salientes
    qs_dura = ConversacionWhatsapp.objects.filter(
        saliente=True, atendida=True, date_last_interaction__isnull=False
    )
    qs_dura = qs_dura.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_dura = qs_dura.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_dura = qs_dura.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_dura = qs_dura.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_dura = qs_dura.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_dura = qs_dura.filter(timestamp__time__lte=hora_hasta)
    qs_dura = qs_dura.annotate(
        _duracion=ExpressionWrapper(
            F('date_last_interaction') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        duracion_segundos=ExpressionWrapper(
            Extract(F('_duracion'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    duracion_por_campana = dict(
        qs_dura.values('campana_id')
        .annotate(avg_duracion=Avg('duracion_segundos'))
        .values_list('campana_id', 'avg_duracion')
    )

    result = []
    for r in rows:
        cid = r['campana_id']
        enviados = r['enviados'] or 0
        respondidos = r['respondidos'] or 0
        no_respondidos = enviados - respondidos
        nombre_campana = _('Sin campaña') if cid is None else names_map.get(cid) or str(cid)
        avg_frt = _decimal_to_float(espera_por_campana.get(cid))
        avg_duracion = _decimal_to_float(duracion_por_campana.get(cid))
        pct_respondidos = round(100.0 * respondidos / enviados, 1) if enviados else None
        pct_no_respondidos = round(100.0 * no_respondidos / enviados, 1) if enviados else None
        result.append({
            'nombre_campana': nombre_campana,
            'enviados': enviados,
            'respondidos': respondidos,
            'no_respondidos': no_respondidos,
            'avg_frt_segundos': avg_frt,
            'avg_duracion_segundos': avg_duracion,
            'pct_respondidos': pct_respondidos,
            'pct_no_respondidos': pct_no_respondidos,
        })
    result.sort(key=lambda x: x['enviados'], reverse=True)
    return result


def obtener_whatsapp_egresos_mensajes_por_hora(start_date=None, end_date=None,
                                                allowed_campaigns=None, allowed_agent_ids=None,
                                                address_query=None, hora_desde=None, hora_hasta=None):
    """
    Agrupa conversaciones WhatsApp salientes (egresos) por hora del día (0-23) para el reporte
    centro de contacto. Sin discriminar por campaña. Retorna (lista de 24 dicts, dict_totals) con:
    hour_label, enviados, respondidos, no_respondidos, avg_frt_segundos, avg_duracion_segundos,
    pct_respondidos, pct_no_respondidos.
    """
    if start_date is None or end_date is None:
        return [], None
    qs = ConversacionWhatsapp.objects.filter(saliente=True)
    qs = qs.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs = qs.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs = qs.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs = qs.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs = qs.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs = qs.filter(timestamp__time__lte=hora_hasta)

    rows = list(
        qs.annotate(hour=ExtractHour('timestamp'))
        .values('hour')
        .annotate(
            enviados=Count('id'),
            respondidos=Count('id', filter=Q(atendida=True)),
        )
        .order_by('hour')
    )
    data_by_hour = {}
    for r in rows:
        h = r['hour']
        if h is None:
            continue
        h = int(h) % 24
        enviados = r['enviados'] or 0
        respondidos = r['respondidos'] or 0
        no_respondidos = enviados - respondidos
        pct_respondidos = round(100.0 * respondidos / enviados, 1) if enviados else None
        pct_no_respondidos = round(100.0 * no_respondidos / enviados, 1) if enviados else None
        data_by_hour[h] = {
            'enviados': enviados,
            'respondidos': respondidos,
            'no_respondidos': no_respondidos,
            'pct_respondidos': pct_respondidos,
            'pct_no_respondidos': pct_no_respondidos,
            'avg_frt_segundos': None,
            'avg_duracion_segundos': None,
        }

    # T Espera prom. (egresos): tiempo hasta primera respuesta del cliente, por hora
    qs_espera = reporte_tiempos_respuesta_whatsapp(start_date, end_date, sla_segundos=120)
    qs_espera = qs_espera.filter(saliente=True)
    qs_espera = qs_espera.filter(timestamp_primer_mensaje_cliente__isnull=False)
    if allowed_campaigns is not None:
        qs_espera = qs_espera.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_espera = qs_espera.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_espera = qs_espera.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_espera = qs_espera.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_espera = qs_espera.filter(timestamp__time__lte=hora_hasta)
    qs_espera = qs_espera.annotate(
        _espera_delta=ExpressionWrapper(
            F('timestamp_primer_mensaje_cliente') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        espera_segundos=ExpressionWrapper(
            Extract(F('_espera_delta'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    espera_por_hora = dict(
        qs_espera.annotate(hour=ExtractHour('timestamp'))
        .values('hour')
        .annotate(avg_espera=Avg('espera_segundos'))
        .values_list('hour', 'avg_espera')
    )
    for h, avg_espera in espera_por_hora.items():
        h = int(h) % 24 if h is not None else 0
        if h in data_by_hour:
            data_by_hour[h]['avg_frt_segundos'] = _decimal_to_float(avg_espera)

    # Duración promedio por hora (atendidas salientes con date_last_interaction)
    qs_dura = ConversacionWhatsapp.objects.filter(
        saliente=True, atendida=True, date_last_interaction__isnull=False
    )
    qs_dura = qs_dura.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_dura = qs_dura.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_dura = qs_dura.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_dura = qs_dura.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_dura = qs_dura.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_dura = qs_dura.filter(timestamp__time__lte=hora_hasta)
    qs_dura = qs_dura.annotate(
        hour=ExtractHour('timestamp'),
        _duracion=ExpressionWrapper(
            F('date_last_interaction') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        duracion_segundos=ExpressionWrapper(
            Extract(F('_duracion'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    duracion_por_hora = dict(
        qs_dura.values('hour')
        .annotate(avg_duracion=Avg('duracion_segundos'))
        .values_list('hour', 'avg_duracion')
    )
    for h, avg_duracion in duracion_por_hora.items():
        h = int(h) % 24 if h is not None else 0
        if h in data_by_hour:
            data_by_hour[h]['avg_duracion_segundos'] = _decimal_to_float(avg_duracion)

    result = []
    for h in range(24):
        hour_label = '{0:02d}:00'.format(h)
        if h in data_by_hour:
            row = data_by_hour[h].copy()
            row['hour'] = h
            row['hour_label'] = hour_label
        else:
            row = {
                'hour': h,
                'hour_label': hour_label,
                'enviados': 0,
                'respondidos': 0,
                'no_respondidos': 0,
                'avg_frt_segundos': None,
                'avg_duracion_segundos': None,
                'pct_respondidos': None,
                'pct_no_respondidos': None,
            }
        result.append(row)

    total_enviados = sum(r['enviados'] for r in result)
    total_respondidos = sum(r['respondidos'] for r in result)
    total_no_respondidos = total_enviados - total_respondidos
    totals = None
    if total_enviados > 0:
        sum_frt = sum(
            (r['avg_frt_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_frt_segundos'] is not None
        )
        count_frt = sum(r['respondidos'] for r in result if r['avg_frt_segundos'] is not None)
        sum_dura = sum(
            (r['avg_duracion_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_duracion_segundos'] is not None
        )
        count_dura = sum(
            r['respondidos'] for r in result if r['avg_duracion_segundos'] is not None
        )
        totals = {
            'enviados': total_enviados,
            'respondidos': total_respondidos,
            'no_respondidos': total_no_respondidos,
            'avg_frt_segundos': round(sum_frt / count_frt, 1) if count_frt else None,
            'avg_duracion_segundos': round(sum_dura / count_dura, 1) if count_dura else None,
            'pct_respondidos': round(100.0 * total_respondidos / total_enviados, 1),
            'pct_no_respondidos': round(100.0 * total_no_respondidos / total_enviados, 1),
        }
    return result, totals


def obtener_whatsapp_egresos_mensajes_por_dia(start_date=None, end_date=None,
                                               allowed_campaigns=None, allowed_agent_ids=None,
                                               address_query=None, hora_desde=None, hora_hasta=None):
    """
    Agrupa conversaciones WhatsApp salientes (egresos) por día (fecha) para el reporte centro de
    contacto. Sin discriminar por campaña. Retorna (lista de dicts por día, dict_totals) con:
    fecha, fecha_label, enviados, respondidos, no_respondidos, avg_frt_segundos, avg_duracion_segundos,
    pct_respondidos, pct_no_respondidos.
    """
    if start_date is None or end_date is None:
        return [], None
    start = start_date.date() if hasattr(start_date, 'date') else start_date
    end = end_date.date() if hasattr(end_date, 'date') else end_date
    if start > end:
        return [], None

    qs = ConversacionWhatsapp.objects.filter(saliente=True)
    qs = qs.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs = qs.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs = qs.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs = qs.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs = qs.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs = qs.filter(timestamp__time__lte=hora_hasta)

    rows = list(
        qs.annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(
            enviados=Count('id'),
            respondidos=Count('id', filter=Q(atendida=True)),
        )
        .order_by('day')
    )
    data_by_day = {}
    for r in rows:
        d = r['day']
        if d is None:
            continue
        if hasattr(d, 'date'):
            d = d.date() if hasattr(d, 'date') else d
        enviados = r['enviados'] or 0
        respondidos = r['respondidos'] or 0
        no_respondidos = enviados - respondidos
        pct_respondidos = round(100.0 * respondidos / enviados, 1) if enviados else None
        pct_no_respondidos = round(100.0 * no_respondidos / enviados, 1) if enviados else None
        data_by_day[d] = {
            'enviados': enviados,
            'respondidos': respondidos,
            'no_respondidos': no_respondidos,
            'pct_respondidos': pct_respondidos,
            'pct_no_respondidos': pct_no_respondidos,
            'avg_frt_segundos': None,
            'avg_duracion_segundos': None,
        }

    # T Espera prom. (egresos): tiempo hasta primera respuesta del cliente, por día
    qs_espera = reporte_tiempos_respuesta_whatsapp(start_date, end_date, sla_segundos=120)
    qs_espera = qs_espera.filter(saliente=True)
    qs_espera = qs_espera.filter(timestamp_primer_mensaje_cliente__isnull=False)
    if allowed_campaigns is not None:
        qs_espera = qs_espera.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_espera = qs_espera.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_espera = qs_espera.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_espera = qs_espera.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_espera = qs_espera.filter(timestamp__time__lte=hora_hasta)
    qs_espera = qs_espera.annotate(
        _espera_delta=ExpressionWrapper(
            F('timestamp_primer_mensaje_cliente') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        espera_segundos=ExpressionWrapper(
            Extract(F('_espera_delta'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    espera_por_dia = dict(
        qs_espera.annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(avg_espera=Avg('espera_segundos'))
        .values_list('day', 'avg_espera')
    )
    for d, avg_espera in espera_por_dia.items():
        if d is not None:
            d_key = d.date() if hasattr(d, 'date') else d
            if d_key in data_by_day:
                data_by_day[d_key]['avg_frt_segundos'] = _decimal_to_float(avg_espera)

    # Duración promedio por día (atendidas salientes con date_last_interaction)
    qs_dura = ConversacionWhatsapp.objects.filter(
        saliente=True, atendida=True, date_last_interaction__isnull=False
    )
    qs_dura = qs_dura.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_dura = qs_dura.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_dura = qs_dura.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_dura = qs_dura.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_dura = qs_dura.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_dura = qs_dura.filter(timestamp__time__lte=hora_hasta)
    qs_dura = qs_dura.annotate(
        day=TruncDate('timestamp'),
        _duracion=ExpressionWrapper(
            F('date_last_interaction') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        duracion_segundos=ExpressionWrapper(
            Extract(F('_duracion'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    duracion_por_dia = dict(
        qs_dura.values('day')
        .annotate(avg_duracion=Avg('duracion_segundos'))
        .values_list('day', 'avg_duracion')
    )
    for d, avg_duracion in duracion_por_dia.items():
        if d is not None:
            d_key = d.date() if hasattr(d, 'date') else d
            if d_key in data_by_day:
                data_by_day[d_key]['avg_duracion_segundos'] = _decimal_to_float(avg_duracion)

    result = []
    current = start
    while current <= end:
        if current in data_by_day:
            row = data_by_day[current].copy()
            row['fecha'] = current
            row['fecha_label'] = current.strftime('%d/%m/%Y')
        else:
            row = {
                'fecha': current,
                'fecha_label': current.strftime('%d/%m/%Y'),
                'enviados': 0,
                'respondidos': 0,
                'no_respondidos': 0,
                'avg_frt_segundos': None,
                'avg_duracion_segundos': None,
                'pct_respondidos': None,
                'pct_no_respondidos': None,
            }
        result.append(row)
        current += timedelta(days=1)

    total_enviados = sum(r['enviados'] for r in result)
    total_respondidos = sum(r['respondidos'] for r in result)
    total_no_respondidos = total_enviados - total_respondidos
    totals = None
    if total_enviados > 0:
        sum_frt = sum(
            (r['avg_frt_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_frt_segundos'] is not None
        )
        count_frt = sum(r['respondidos'] for r in result if r['avg_frt_segundos'] is not None)
        sum_dura = sum(
            (r['avg_duracion_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_duracion_segundos'] is not None
        )
        count_dura = sum(
            r['respondidos'] for r in result if r['avg_duracion_segundos'] is not None
        )
        totals = {
            'enviados': total_enviados,
            'respondidos': total_respondidos,
            'no_respondidos': total_no_respondidos,
            'avg_frt_segundos': round(sum_frt / count_frt, 1) if count_frt else None,
            'avg_duracion_segundos': round(sum_dura / count_dura, 1) if count_dura else None,
            'pct_respondidos': round(100.0 * total_respondidos / total_enviados, 1),
            'pct_no_respondidos': round(100.0 * total_no_respondidos / total_enviados, 1),
        }
    return result, totals


def obtener_whatsapp_egresos_mensajes_por_mes(start_date=None, end_date=None,
                                               allowed_campaigns=None, allowed_agent_ids=None,
                                               address_query=None, hora_desde=None, hora_hasta=None):
    """
    Agrupa conversaciones WhatsApp salientes (egresos) por mes para el reporte centro de
    contacto. Sin discriminar por campaña. Retorna (lista de dicts por mes, dict_totals) con:
    mes, mes_label, enviados, respondidos, no_respondidos, avg_frt_segundos, avg_duracion_segundos,
    pct_respondidos, pct_no_respondidos.
    """
    if start_date is None or end_date is None:
        return [], None
    start = start_date.date() if hasattr(start_date, 'date') else start_date
    end = end_date.date() if hasattr(end_date, 'date') else end_date
    if start > end:
        return [], None

    qs = ConversacionWhatsapp.objects.filter(saliente=True)
    qs = qs.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs = qs.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs = qs.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs = qs.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs = qs.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs = qs.filter(timestamp__time__lte=hora_hasta)

    rows = list(
        qs.annotate(month=TruncMonth('timestamp'))
        .values('month')
        .annotate(
            enviados=Count('id'),
            respondidos=Count('id', filter=Q(atendida=True)),
        )
        .order_by('month')
    )
    data_by_month = {}
    for r in rows:
        m = r['month']
        if m is None:
            continue
        if hasattr(m, 'date'):
            m_date = m.date() if hasattr(m, 'date') else m
        else:
            m_date = m
        enviados = r['enviados'] or 0
        respondidos = r['respondidos'] or 0
        no_respondidos = enviados - respondidos
        pct_respondidos = round(100.0 * respondidos / enviados, 1) if enviados else None
        pct_no_respondidos = round(100.0 * no_respondidos / enviados, 1) if enviados else None
        month_key = (m_date.year, m_date.month)
        data_by_month[month_key] = {
            'enviados': enviados,
            'respondidos': respondidos,
            'no_respondidos': no_respondidos,
            'pct_respondidos': pct_respondidos,
            'pct_no_respondidos': pct_no_respondidos,
            'avg_frt_segundos': None,
            'avg_duracion_segundos': None,
        }

    # T Espera prom. (egresos): tiempo hasta primera respuesta del cliente, por mes
    qs_espera = reporte_tiempos_respuesta_whatsapp(start_date, end_date, sla_segundos=120)
    qs_espera = qs_espera.filter(saliente=True)
    qs_espera = qs_espera.filter(timestamp_primer_mensaje_cliente__isnull=False)
    if allowed_campaigns is not None:
        qs_espera = qs_espera.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_espera = qs_espera.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_espera = qs_espera.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_espera = qs_espera.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_espera = qs_espera.filter(timestamp__time__lte=hora_hasta)
    qs_espera = qs_espera.annotate(
        _espera_delta=ExpressionWrapper(
            F('timestamp_primer_mensaje_cliente') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        espera_segundos=ExpressionWrapper(
            Extract(F('_espera_delta'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    espera_por_mes = list(
        qs_espera.annotate(month=TruncMonth('timestamp'))
        .values('month')
        .annotate(avg_espera=Avg('espera_segundos'))
        .values_list('month', 'avg_espera')
    )
    for m, avg_espera in espera_por_mes:
        if m is not None:
            m_date = m.date() if hasattr(m, 'date') else m
            month_key = (m_date.year, m_date.month)
            if month_key in data_by_month:
                data_by_month[month_key]['avg_frt_segundos'] = _decimal_to_float(avg_espera)

    # Duración promedio por mes (atendidas salientes con date_last_interaction)
    qs_dura = ConversacionWhatsapp.objects.filter(
        saliente=True, atendida=True, date_last_interaction__isnull=False
    )
    qs_dura = qs_dura.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_dura = qs_dura.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_dura = qs_dura.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_dura = qs_dura.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_dura = qs_dura.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_dura = qs_dura.filter(timestamp__time__lte=hora_hasta)
    qs_dura = qs_dura.annotate(
        month=TruncMonth('timestamp'),
        _duracion=ExpressionWrapper(
            F('date_last_interaction') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        duracion_segundos=ExpressionWrapper(
            Extract(F('_duracion'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    duracion_por_mes = list(
        qs_dura.values('month')
        .annotate(avg_duracion=Avg('duracion_segundos'))
        .values_list('month', 'avg_duracion')
    )
    for m, avg_duracion in duracion_por_mes:
        if m is not None:
            m_date = m.date() if hasattr(m, 'date') else m
            month_key = (m_date.year, m_date.month)
            if month_key in data_by_month:
                data_by_month[month_key]['avg_duracion_segundos'] = _decimal_to_float(avg_duracion)

    # Ordenar meses entre start y end
    result = []
    year, month = start.year, start.month
    end_y, end_m = end.year, end.month
    while (year, month) <= (end_y, end_m):
        month_key = (year, month)
        first_day = date(year, month, 1)
        if month_key in data_by_month:
            row = data_by_month[month_key].copy()
            row['mes'] = first_day
            row['mes_label'] = first_day.strftime('%m/%Y')
        else:
            row = {
                'mes': first_day,
                'mes_label': first_day.strftime('%m/%Y'),
                'enviados': 0,
                'respondidos': 0,
                'no_respondidos': 0,
                'avg_frt_segundos': None,
                'avg_duracion_segundos': None,
                'pct_respondidos': None,
                'pct_no_respondidos': None,
            }
        result.append(row)
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1

    total_enviados = sum(r['enviados'] for r in result)
    total_respondidos = sum(r['respondidos'] for r in result)
    total_no_respondidos = total_enviados - total_respondidos
    totals = None
    if total_enviados > 0:
        sum_frt = sum(
            (r['avg_frt_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_frt_segundos'] is not None
        )
        count_frt = sum(r['respondidos'] for r in result if r['avg_frt_segundos'] is not None)
        sum_dura = sum(
            (r['avg_duracion_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_duracion_segundos'] is not None
        )
        count_dura = sum(
            r['respondidos'] for r in result if r['avg_duracion_segundos'] is not None
        )
        totals = {
            'enviados': total_enviados,
            'respondidos': total_respondidos,
            'no_respondidos': total_no_respondidos,
            'avg_frt_segundos': round(sum_frt / count_frt, 1) if count_frt else None,
            'avg_duracion_segundos': round(sum_dura / count_dura, 1) if count_dura else None,
            'pct_respondidos': round(100.0 * total_respondidos / total_enviados, 1),
            'pct_no_respondidos': round(100.0 * total_no_respondidos / total_enviados, 1),
        }
    return result, totals


def obtener_whatsapp_mensajes_por_hora(start_date=None, end_date=None,
                                       allowed_campaigns=None, allowed_agent_ids=None,
                                       address_query=None, hora_desde=None, hora_hasta=None):
    """
    Agrupa conversaciones WhatsApp entrantes por hora del día (0-23) para el reporte centro de contacto.
    Retorna (lista de 24 dicts, dict_totals) con: hour_label, recibidos, respondidos, no_respondidos,
    avg_frt_segundos, avg_duracion_segundos, pct_respondidas, pct_no_respondidos.
    """
    if start_date is None or end_date is None:
        return [], None
    qs = ConversacionWhatsapp.objects.filter(saliente=False)
    qs = qs.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs = qs.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs = qs.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs = qs.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs = qs.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs = qs.filter(timestamp__time__lte=hora_hasta)

    rows = list(
        qs.annotate(hour=ExtractHour('timestamp'))
        .values('hour')
        .annotate(
            recibidos=Count('id'),
            respondidos=Count('id', filter=Q(atendida=True)),
        )
        .order_by('hour')
    )
    data_by_hour = {}
    for r in rows:
        h = r['hour']
        if h is None:
            continue
        h = int(h) % 24
        recibidos = r['recibidos'] or 0
        respondidos = r['respondidos'] or 0
        no_respondidos = recibidos - respondidos
        pct_respondidas = round(100.0 * respondidos / recibidos, 1) if recibidos else None
        pct_no_respondidos = round(100.0 * no_respondidos / recibidos, 1) if recibidos else None
        data_by_hour[h] = {
            'recibidos': recibidos,
            'respondidos': respondidos,
            'no_respondidos': no_respondidos,
            'pct_respondidas': pct_respondidas,
            'pct_no_respondidos': pct_no_respondidos,
            'avg_frt_segundos': None,
            'avg_duracion_segundos': None,
        }

    # FRT promedio por hora
    qs_frt = reporte_tiempos_respuesta_whatsapp(start_date, end_date, sla_segundos=120)
    qs_frt = qs_frt.filter(frt_segundos__isnull=False)
    if allowed_campaigns is not None:
        qs_frt = qs_frt.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_frt = qs_frt.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_frt = qs_frt.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_frt = qs_frt.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_frt = qs_frt.filter(timestamp__time__lte=hora_hasta)
    frt_por_hora = dict(
        qs_frt.annotate(hour=ExtractHour('timestamp'))
        .values('hour')
        .annotate(avg_frt=Avg('frt_segundos'))
        .values_list('hour', 'avg_frt')
    )
    for h, avg_frt in frt_por_hora.items():
        h = int(h) % 24 if h is not None else 0
        if h in data_by_hour:
            data_by_hour[h]['avg_frt_segundos'] = _decimal_to_float(avg_frt)

    # Duración promedio por hora (atendidas con date_last_interaction)
    qs_dura = ConversacionWhatsapp.objects.filter(
        saliente=False, atendida=True, date_last_interaction__isnull=False
    )
    qs_dura = qs_dura.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_dura = qs_dura.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_dura = qs_dura.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_dura = qs_dura.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_dura = qs_dura.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_dura = qs_dura.filter(timestamp__time__lte=hora_hasta)
    qs_dura = qs_dura.annotate(
        hour=ExtractHour('timestamp'),
        _duracion=ExpressionWrapper(
            F('date_last_interaction') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        duracion_segundos=ExpressionWrapper(
            Extract(F('_duracion'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    duracion_por_hora = dict(
        qs_dura.values('hour')
        .annotate(avg_duracion=Avg('duracion_segundos'))
        .values_list('hour', 'avg_duracion')
    )
    for h, avg_duracion in duracion_por_hora.items():
        h = int(h) % 24 if h is not None else 0
        if h in data_by_hour:
            data_by_hour[h]['avg_duracion_segundos'] = _decimal_to_float(avg_duracion)

    result = []
    for h in range(24):
        hour_label = '{0:02d}:00'.format(h)
        if h in data_by_hour:
            row = data_by_hour[h].copy()
            row['hour'] = h
            row['hour_label'] = hour_label
        else:
            row = {
                'hour': h,
                'hour_label': hour_label,
                'recibidos': 0,
                'respondidos': 0,
                'no_respondidos': 0,
                'avg_frt_segundos': None,
                'avg_duracion_segundos': None,
                'pct_respondidas': None,
                'pct_no_respondidos': None,
            }
        result.append(row)

    # Totals
    total_recibidos = sum(r['recibidos'] for r in result)
    total_respondidos = sum(r['respondidos'] for r in result)
    total_no_respondidos = total_recibidos - total_respondidos
    totals = None
    if total_recibidos > 0:
        # Weighted avg FRT and duration (by respondidos per hour)
        sum_frt = sum(
            (r['avg_frt_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_frt_segundos'] is not None
        )
        count_frt = sum(r['respondidos'] for r in result if r['avg_frt_segundos'] is not None)
        sum_dura = sum(
            (r['avg_duracion_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_duracion_segundos'] is not None
        )
        count_dura = sum(r['respondidos'] for r in result if r['avg_duracion_segundos'] is not None)
        totals = {
            'recibidos': total_recibidos,
            'respondidos': total_respondidos,
            'no_respondidos': total_no_respondidos,
            'avg_frt_segundos': round(sum_frt / count_frt, 1) if count_frt else None,
            'avg_duracion_segundos': round(sum_dura / count_dura, 1) if count_dura else None,
            'pct_respondidas': round(100.0 * total_respondidos / total_recibidos, 1),
            'pct_no_respondidos': round(100.0 * total_no_respondidos / total_recibidos, 1),
        }
    return result, totals


def obtener_whatsapp_mensajes_por_dia(start_date=None, end_date=None,
                                      allowed_campaigns=None, allowed_agent_ids=None,
                                      address_query=None, hora_desde=None, hora_hasta=None):
    """
    Agrupa conversaciones WhatsApp entrantes por día (fecha) para el reporte centro de contacto.
    Sin discriminar por campaña. Retorna (lista de dicts por día, dict_totals) con: fecha,
    fecha_label, recibidos, respondidos, no_respondidos, avg_frt_segundos, avg_duracion_segundos,
    pct_respondidas, pct_no_respondidos. Similar a obtener_whatsapp_mensajes_por_hora pero por fecha.
    """
    if start_date is None or end_date is None:
        return [], None
    start = start_date.date() if hasattr(start_date, 'date') else start_date
    end = end_date.date() if hasattr(end_date, 'date') else end_date
    if start > end:
        return [], None

    qs = ConversacionWhatsapp.objects.filter(saliente=False)
    qs = qs.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs = qs.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs = qs.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs = qs.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs = qs.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs = qs.filter(timestamp__time__lte=hora_hasta)

    rows = list(
        qs.annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(
            recibidos=Count('id'),
            respondidos=Count('id', filter=Q(atendida=True)),
        )
        .order_by('day')
    )
    data_by_day = {}
    for r in rows:
        d = r['day']
        if d is None:
            continue
        if hasattr(d, 'date'):
            d = d.date() if hasattr(d, 'date') else d
        recibidos = r['recibidos'] or 0
        respondidos = r['respondidos'] or 0
        no_respondidos = recibidos - respondidos
        pct_respondidas = round(100.0 * respondidos / recibidos, 1) if recibidos else None
        pct_no_respondidos = round(100.0 * no_respondidos / recibidos, 1) if recibidos else None
        data_by_day[d] = {
            'recibidos': recibidos,
            'respondidos': respondidos,
            'no_respondidos': no_respondidos,
            'pct_respondidas': pct_respondidas,
            'pct_no_respondidos': pct_no_respondidos,
            'avg_frt_segundos': None,
            'avg_duracion_segundos': None,
        }

    # FRT promedio por día
    qs_frt = reporte_tiempos_respuesta_whatsapp(start_date, end_date, sla_segundos=120)
    qs_frt = qs_frt.filter(frt_segundos__isnull=False)
    if allowed_campaigns is not None:
        qs_frt = qs_frt.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_frt = qs_frt.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_frt = qs_frt.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_frt = qs_frt.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_frt = qs_frt.filter(timestamp__time__lte=hora_hasta)
    frt_por_dia = dict(
        qs_frt.annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(avg_frt=Avg('frt_segundos'))
        .values_list('day', 'avg_frt')
    )
    for d, avg_frt in frt_por_dia.items():
        if d is not None:
            d_key = d.date() if hasattr(d, 'date') else d
            if d_key in data_by_day:
                data_by_day[d_key]['avg_frt_segundos'] = _decimal_to_float(avg_frt)

    # Duración promedio por día (atendidas con date_last_interaction)
    qs_dura = ConversacionWhatsapp.objects.filter(
        saliente=False, atendida=True, date_last_interaction__isnull=False
    )
    qs_dura = qs_dura.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_dura = qs_dura.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_dura = qs_dura.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_dura = qs_dura.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_dura = qs_dura.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_dura = qs_dura.filter(timestamp__time__lte=hora_hasta)
    qs_dura = qs_dura.annotate(
        day=TruncDate('timestamp'),
        _duracion=ExpressionWrapper(
            F('date_last_interaction') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        duracion_segundos=ExpressionWrapper(
            Extract(F('_duracion'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    duracion_por_dia = dict(
        qs_dura.values('day')
        .annotate(avg_duracion=Avg('duracion_segundos'))
        .values_list('day', 'avg_duracion')
    )
    for d, avg_duracion in duracion_por_dia.items():
        if d is not None:
            d_key = d.date() if hasattr(d, 'date') else d
            if d_key in data_by_day:
                data_by_day[d_key]['avg_duracion_segundos'] = _decimal_to_float(avg_duracion)

    result = []
    current = start
    while current <= end:
        if current in data_by_day:
            row = data_by_day[current].copy()
            row['fecha'] = current
            row['fecha_label'] = current.strftime('%d/%m/%Y')
        else:
            row = {
                'fecha': current,
                'fecha_label': current.strftime('%d/%m/%Y'),
                'recibidos': 0,
                'respondidos': 0,
                'no_respondidos': 0,
                'avg_frt_segundos': None,
                'avg_duracion_segundos': None,
                'pct_respondidas': None,
                'pct_no_respondidos': None,
            }
        result.append(row)
        current += timedelta(days=1)

    total_recibidos = sum(r['recibidos'] for r in result)
    total_respondidos = sum(r['respondidos'] for r in result)
    total_no_respondidos = total_recibidos - total_respondidos
    totals = None
    if total_recibidos > 0:
        sum_frt = sum(
            (r['avg_frt_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_frt_segundos'] is not None
        )
        count_frt = sum(r['respondidos'] for r in result if r['avg_frt_segundos'] is not None)
        sum_dura = sum(
            (r['avg_duracion_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_duracion_segundos'] is not None
        )
        count_dura = sum(r['respondidos'] for r in result if r['avg_duracion_segundos'] is not None)
        totals = {
            'recibidos': total_recibidos,
            'respondidos': total_respondidos,
            'no_respondidos': total_no_respondidos,
            'avg_frt_segundos': round(sum_frt / count_frt, 1) if count_frt else None,
            'avg_duracion_segundos': round(sum_dura / count_dura, 1) if count_dura else None,
            'pct_respondidas': round(100.0 * total_respondidos / total_recibidos, 1),
            'pct_no_respondidos': round(100.0 * total_no_respondidos / total_recibidos, 1),
        }
    return result, totals


def obtener_whatsapp_mensajes_por_mes(start_date=None, end_date=None,
                                      allowed_campaigns=None, allowed_agent_ids=None,
                                      address_query=None, hora_desde=None, hora_hasta=None):
    """
    Agrupa conversaciones WhatsApp entrantes por mes para el reporte centro de contacto.
    Sin discriminar por campaña. Retorna (lista de dicts por mes, dict_totals) con: mes,
    mes_label, recibidos, respondidos, no_respondidos, avg_frt_segundos, avg_duracion_segundos,
    pct_respondidas, pct_no_respondidos. Similar a obtener_whatsapp_mensajes_por_dia pero por mes.
    """
    if start_date is None or end_date is None:
        return [], None
    start = start_date.date() if hasattr(start_date, 'date') else start_date
    end = end_date.date() if hasattr(end_date, 'date') else end_date
    if start > end:
        return [], None

    qs = ConversacionWhatsapp.objects.filter(saliente=False)
    qs = qs.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs = qs.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs = qs.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs = qs.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs = qs.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs = qs.filter(timestamp__time__lte=hora_hasta)

    rows = list(
        qs.annotate(month=TruncMonth('timestamp'))
        .values('month')
        .annotate(
            recibidos=Count('id'),
            respondidos=Count('id', filter=Q(atendida=True)),
        )
        .order_by('month')
    )
    data_by_month = {}
    for r in rows:
        m = r['month']
        if m is None:
            continue
        if hasattr(m, 'date'):
            m_date = m.date() if hasattr(m, 'date') else m
        else:
            m_date = m
        recibidos = r['recibidos'] or 0
        respondidos = r['respondidos'] or 0
        no_respondidos = recibidos - respondidos
        pct_respondidas = round(100.0 * respondidos / recibidos, 1) if recibidos else None
        pct_no_respondidos = round(100.0 * no_respondidos / recibidos, 1) if recibidos else None
        month_key = (m_date.year, m_date.month)
        data_by_month[month_key] = {
            'recibidos': recibidos,
            'respondidos': respondidos,
            'no_respondidos': no_respondidos,
            'pct_respondidas': pct_respondidas,
            'pct_no_respondidos': pct_no_respondidos,
            'avg_frt_segundos': None,
            'avg_duracion_segundos': None,
        }

    # FRT promedio por mes
    qs_frt = reporte_tiempos_respuesta_whatsapp(start_date, end_date, sla_segundos=120)
    qs_frt = qs_frt.filter(frt_segundos__isnull=False)
    if allowed_campaigns is not None:
        qs_frt = qs_frt.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_frt = qs_frt.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_frt = qs_frt.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_frt = qs_frt.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_frt = qs_frt.filter(timestamp__time__lte=hora_hasta)
    frt_por_mes = list(
        qs_frt.annotate(month=TruncMonth('timestamp'))
        .values('month')
        .annotate(avg_frt=Avg('frt_segundos'))
        .values_list('month', 'avg_frt')
    )
    for m, avg_frt in frt_por_mes:
        if m is not None:
            m_date = m.date() if hasattr(m, 'date') else m
            month_key = (m_date.year, m_date.month)
            if month_key in data_by_month:
                data_by_month[month_key]['avg_frt_segundos'] = _decimal_to_float(avg_frt)

    # Duración promedio por mes (atendidas con date_last_interaction)
    qs_dura = ConversacionWhatsapp.objects.filter(
        saliente=False, atendida=True, date_last_interaction__isnull=False
    )
    qs_dura = qs_dura.filter(timestamp__gte=start_date, timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_dura = qs_dura.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_dura = qs_dura.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_dura = qs_dura.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_dura = qs_dura.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_dura = qs_dura.filter(timestamp__time__lte=hora_hasta)
    qs_dura = qs_dura.annotate(
        month=TruncMonth('timestamp'),
        _duracion=ExpressionWrapper(
            F('date_last_interaction') - F('timestamp'),
            output_field=DurationField(),
        ),
    ).annotate(
        duracion_segundos=ExpressionWrapper(
            Extract(F('_duracion'), lookup_name='epoch'),
            output_field=IntegerField(),
        ),
    )
    duracion_por_mes = list(
        qs_dura.values('month')
        .annotate(avg_duracion=Avg('duracion_segundos'))
        .values_list('month', 'avg_duracion')
    )
    for m, avg_duracion in duracion_por_mes:
        if m is not None:
            m_date = m.date() if hasattr(m, 'date') else m
            month_key = (m_date.year, m_date.month)
            if month_key in data_by_month:
                data_by_month[month_key]['avg_duracion_segundos'] = _decimal_to_float(avg_duracion)

    # Ordenar meses entre start y end
    result = []
    year, month = start.year, start.month
    end_y, end_m = end.year, end.month
    while (year, month) <= (end_y, end_m):
        month_key = (year, month)
        first_day = date(year, month, 1)
        if month_key in data_by_month:
            row = data_by_month[month_key].copy()
            row['mes'] = first_day
            row['mes_label'] = first_day.strftime('%m/%Y')
        else:
            row = {
                'mes': first_day,
                'mes_label': first_day.strftime('%m/%Y'),
                'recibidos': 0,
                'respondidos': 0,
                'no_respondidos': 0,
                'avg_frt_segundos': None,
                'avg_duracion_segundos': None,
                'pct_respondidas': None,
                'pct_no_respondidos': None,
            }
        result.append(row)
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1

    total_recibidos = sum(r['recibidos'] for r in result)
    total_respondidos = sum(r['respondidos'] for r in result)
    total_no_respondidos = total_recibidos - total_respondidos
    totals = None
    if total_recibidos > 0:
        sum_frt = sum(
            (r['avg_frt_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_frt_segundos'] is not None
        )
        count_frt = sum(r['respondidos'] for r in result if r['avg_frt_segundos'] is not None)
        sum_dura = sum(
            (r['avg_duracion_segundos'] or 0) * r['respondidos']
            for r in result if r['avg_duracion_segundos'] is not None
        )
        count_dura = sum(r['respondidos'] for r in result if r['avg_duracion_segundos'] is not None)
        totals = {
            'recibidos': total_recibidos,
            'respondidos': total_respondidos,
            'no_respondidos': total_no_respondidos,
            'avg_frt_segundos': round(sum_frt / count_frt, 1) if count_frt else None,
            'avg_duracion_segundos': round(sum_dura / count_dura, 1) if count_dura else None,
            'pct_respondidas': round(100.0 * total_respondidos / total_recibidos, 1),
            'pct_no_respondidos': round(100.0 * total_no_respondidos / total_recibidos, 1),
        }
    return result, totals


def obtener_canalidades_por_campana(start_date=None, end_date=None,
                                    allowed_campaigns=None, allowed_agent_ids=None,
                                    customer_id=None, address_query=None,
                                    direction_filter='INBOUND',
                                    hora_desde=None, hora_hasta=None,
                                    duracion_agente_min=None, duracion_bot_min=None):
    """
    Agrupa interacciones por campaign_id con métricas por canal (Voz, WhatsApp,
    Facebook). direction_filter: 'INBOUND' o 'OUTBOUND'. Retorna lista de dicts con una fila
    por campaña: campaign_id, campaign_name, y por cada canal: received, pct_atendidas,
    pct_no_atendidas. Atendido = status EXIT_ANSWERED; no atendido = resto.
    """
    queryset = InteractionsSummary.objects.filter(direction__iexact=direction_filter)
    if allowed_campaigns is not None:
        queryset = queryset.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)

    Q_voice = Q(channel_type__iexact='VOICE')
    Q_wa = Q(channel_type__iexact='WA') | Q(channel_type__iexact='WHATSAPP')
    Q_fb = Q(channel_type__iexact='FBMSN') | Q(channel_type__iexact='FACEBOOK_MSN')
    Q_answered = Q(status__iexact='EXIT_ANSWERED')

    rows = (
        queryset
        .values('campaign_id')
        .annotate(
            voice_received=Count('id', filter=Q_voice),
            voice_answered=Count('id', filter=Q_voice & Q_answered),
            wa_received=Count('id', filter=Q_wa),
            wa_answered=Count('id', filter=Q_wa & Q_answered),
            fb_received=Count('id', filter=Q_fb),
            fb_answered=Count('id', filter=Q_fb & Q_answered),
        )
        .order_by('campaign_id')
    )

    # WhatsApp: datos desde ConversacionWhatsapp (campo atendida) para Ingresos y Egresos
    saliente_wa = direction_filter.upper() == 'OUTBOUND'
    qs_wa = ConversacionWhatsapp.objects.filter(saliente=saliente_wa)
    if start_date:
        qs_wa = qs_wa.filter(timestamp__gte=start_date)
    if end_date:
        qs_wa = qs_wa.filter(timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_wa = qs_wa.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_wa = qs_wa.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_wa = qs_wa.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_wa = qs_wa.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_wa = qs_wa.filter(timestamp__time__lte=hora_hasta)

    wa_rows = qs_wa.values('campana_id').annotate(
        wa_received=Count('id'),
        wa_atendidas=Count('id', filter=Q(atendida=True)),
    ).order_by('campana_id')

    wa_por_campana = {}
    for r in wa_rows:
        cid = r['campana_id']
        rec = r['wa_received'] or 0
        at = r['wa_atendidas'] or 0
        pct_a = round(100.0 * at / rec, 2) if rec else 0.0
        pct_na = round(100.0 * (rec - at) / rec, 2) if rec else 0.0
        wa_por_campana[cid] = {
            'received': rec,
            'atendidas': at,
            'pct_atendidas': pct_a,
            'pct_no_atendidas': pct_na,
        }

    wa_default = {'received': 0, 'atendidas': 0, 'pct_atendidas': 0.0, 'pct_no_atendidas': 0.0}
    tot_wa_r = sum(d['received'] for d in wa_por_campana.values())
    tot_wa_a = sum(d['atendidas'] for d in wa_por_campana.values())

    total_any = sum(
        (r['voice_received'] or 0) + (r['wa_received'] or 0) + (r['fb_received'] or 0)
        for r in rows
    )
    if total_any == 0:
        return [], None

    campaign_ids = [r['campaign_id'] for r in rows if r['campaign_id'] is not None]
    names_map = {}
    if campaign_ids:
        names_map = dict(
            Campana.objects.filter(pk__in=campaign_ids).values_list('id', 'nombre')
        )

    result = []
    tot_v_r = tot_v_a = tot_fb_r = tot_fb_a = 0
    for r in rows:
        cid = r['campaign_id']
        if cid is None:
            campaign_name = _('Sin campaña')
        else:
            campaign_name = names_map.get(cid) or str(cid)

        def _pcts(received, answered):
            rec = received or 0
            ans = answered or 0
            no_ans = rec - ans
            pct_a = round(100.0 * ans / rec, 2) if rec else 0.0
            pct_na = round(100.0 * no_ans / rec, 2) if rec else 0.0
            return rec, pct_a, pct_na

        v_rec, v_pct_a, v_pct_na = _pcts(r['voice_received'], r['voice_answered'])
        wa_data = wa_por_campana.get(cid, wa_default)
        w_rec = wa_data['received']
        w_pct_a = wa_data['pct_atendidas']
        w_pct_na = wa_data['pct_no_atendidas']
        f_rec, f_pct_a, f_pct_na = _pcts(r['fb_received'], r['fb_answered'])

        tot_v_r += v_rec
        tot_v_a += (r['voice_answered'] or 0)
        tot_fb_r += f_rec
        tot_fb_a += (r['fb_answered'] or 0)

        result.append({
            'campaign_id': cid,
            'campaign_name': campaign_name,
            'llamadas_received': v_rec,
            'llamadas_pct_atendidas': v_pct_a,
            'llamadas_pct_no_atendidas': v_pct_na,
            'whatsapp_received': w_rec,
            'whatsapp_pct_atendidas': w_pct_a,
            'whatsapp_pct_no_atendidas': w_pct_na,
            'facebook_received': f_rec,
            'facebook_pct_atendidas': f_pct_a,
            'facebook_pct_no_atendidas': f_pct_na,
        })

    # Ordenar por total de recibidos (cualquier canal) descendente
    result.sort(key=lambda x: (
        x['llamadas_received'] + x['whatsapp_received'] + x['facebook_received']
    ), reverse=True)

    def _totals_pct(rec, ans):
        no_ans = rec - ans
        pct_a = round(100.0 * ans / rec, 2) if rec else 0.0
        pct_na = round(100.0 * no_ans / rec, 2) if rec else 0.0
        return pct_a, pct_na

    v_pct_a, v_pct_na = _totals_pct(tot_v_r, tot_v_a)
    w_pct_a, w_pct_na = _totals_pct(tot_wa_r, tot_wa_a)
    f_pct_a, f_pct_na = _totals_pct(tot_fb_r, tot_fb_a)

    canalidades_totals = {
        'llamadas_received': tot_v_r,
        'llamadas_pct_atendidas': v_pct_a,
        'llamadas_pct_no_atendidas': v_pct_na,
        'whatsapp_received': tot_wa_r,
        'whatsapp_pct_atendidas': w_pct_a,
        'whatsapp_pct_no_atendidas': w_pct_na,
        'facebook_received': tot_fb_r,
        'facebook_pct_atendidas': f_pct_a,
        'facebook_pct_no_atendidas': f_pct_na,
    }

    return result, canalidades_totals


def obtener_canalidades_por_hora(start_date=None, end_date=None,
                                 allowed_campaigns=None, allowed_agent_ids=None,
                                 customer_id=None, address_query=None,
                                 direction_filter='INBOUND',
                                 hora_desde=None, hora_hasta=None,
                                 duracion_agente_min=None, duracion_bot_min=None):
    """
    Agrupa interacciones por hora del día (0-23) por canal (Voz, WhatsApp, Facebook)
    sin diferenciar campañas. Mismos criterios que obtener_canalidades_por_campana:
    Voz/Facebook desde InteractionsSummary (atendido=EXIT_ANSWERED), WhatsApp desde
    ConversacionWhatsapp (atendida=True). Retorna (lista de dicts por hora, dict totals).
    """
    Q_voice = Q(channel_type__iexact='VOICE')
    Q_fb = Q(channel_type__iexact='FBMSN') | Q(channel_type__iexact='FACEBOOK_MSN')
    Q_answered = Q(status__iexact='EXIT_ANSWERED')

    # Voz: InteractionsSummary por hora
    qs_voice = InteractionsSummary.objects.filter(
        direction__iexact=direction_filter
    ).filter(Q_voice)
    if allowed_campaigns is not None:
        qs_voice = qs_voice.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        qs_voice = qs_voice.filter(start_time__gte=start_date)
    if end_date:
        qs_voice = qs_voice.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        qs_voice = qs_voice.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        qs_voice = qs_voice.filter(customer_id=customer_id)
    if address_query:
        qs_voice = qs_voice.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        qs_voice = qs_voice.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_voice = qs_voice.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        qs_voice = qs_voice.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        qs_voice = qs_voice.filter(bot_duration__gte=duracion_bot_min)

    voice_rows = list(
        qs_voice.annotate(hour=ExtractHour('start_time'))
        .values('hour')
        .annotate(
            voice_received=Count('id'),
            voice_answered=Count('id', filter=Q_answered),
        )
        .order_by('hour')
    )
    voice_by_hour = {}
    for r in voice_rows:
        h = r['hour']
        if h is not None:
            h = int(h) % 24
            voice_by_hour[h] = {
                'received': r['voice_received'] or 0,
                'answered': r['voice_answered'] or 0,
            }

    # WhatsApp: ConversacionWhatsapp por hora
    saliente_wa = direction_filter.upper() == 'OUTBOUND'
    qs_wa = ConversacionWhatsapp.objects.filter(saliente=saliente_wa)
    if start_date:
        qs_wa = qs_wa.filter(timestamp__gte=start_date)
    if end_date:
        qs_wa = qs_wa.filter(timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_wa = qs_wa.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_wa = qs_wa.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_wa = qs_wa.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_wa = qs_wa.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_wa = qs_wa.filter(timestamp__time__lte=hora_hasta)

    wa_rows = list(
        qs_wa.annotate(hour=ExtractHour('timestamp'))
        .values('hour')
        .annotate(
            wa_received=Count('id'),
            wa_atendidas=Count('id', filter=Q(atendida=True)),
        )
        .order_by('hour')
    )
    wa_by_hour = {}
    for r in wa_rows:
        h = r['hour']
        if h is not None:
            h = int(h) % 24
            rec = r['wa_received'] or 0
            at = r['wa_atendidas'] or 0
            wa_by_hour[h] = {
                'received': rec,
                'atendidas': at,
                'pct_atendidas': round(100.0 * at / rec, 2) if rec else 0.0,
                'pct_no_atendidas': round(100.0 * (rec - at) / rec, 2) if rec else 0.0,
            }

    # Facebook: InteractionsSummary por hora
    qs_fb = InteractionsSummary.objects.filter(
        direction__iexact=direction_filter
    ).filter(Q_fb)
    if allowed_campaigns is not None:
        qs_fb = qs_fb.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        qs_fb = qs_fb.filter(start_time__gte=start_date)
    if end_date:
        qs_fb = qs_fb.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        qs_fb = qs_fb.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        qs_fb = qs_fb.filter(customer_id=customer_id)
    if address_query:
        qs_fb = qs_fb.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        qs_fb = qs_fb.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_fb = qs_fb.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        qs_fb = qs_fb.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        qs_fb = qs_fb.filter(bot_duration__gte=duracion_bot_min)

    fb_rows = list(
        qs_fb.annotate(hour=ExtractHour('start_time'))
        .values('hour')
        .annotate(
            fb_received=Count('id'),
            fb_answered=Count('id', filter=Q_answered),
        )
        .order_by('hour')
    )
    fb_by_hour = {}
    for r in fb_rows:
        h = r['hour']
        if h is not None:
            h = int(h) % 24
            rec = r['fb_received'] or 0
            ans = r['fb_answered'] or 0
            fb_by_hour[h] = {
                'received': rec,
                'answered': ans,
                'pct_atendidas': round(100.0 * ans / rec, 2) if rec else 0.0,
                'pct_no_atendidas': round(100.0 * (rec - ans) / rec, 2) if rec else 0.0,
            }

    def _pcts(received, answered):
        rec = received or 0
        ans = answered or 0
        no_ans = rec - ans
        pct_a = round(100.0 * ans / rec, 2) if rec else 0.0
        pct_na = round(100.0 * no_ans / rec, 2) if rec else 0.0
        return pct_a, pct_na

    result = []
    for h in range(24):
        hour_label = '{0:02d}:00'.format(h)
        v = voice_by_hour.get(h, {'received': 0, 'answered': 0})
        w = wa_by_hour.get(h, {
            'received': 0, 'atendidas': 0, 'pct_atendidas': 0.0, 'pct_no_atendidas': 0.0
        })
        f = fb_by_hour.get(h, {
            'received': 0, 'answered': 0, 'pct_atendidas': 0.0, 'pct_no_atendidas': 0.0
        })
        v_pct_a, v_pct_na = _pcts(v['received'], v['answered'])
        result.append({
            'hour': h,
            'hour_label': hour_label,
            'llamadas_received': v['received'],
            'llamadas_pct_atendidas': v_pct_a,
            'llamadas_pct_no_atendidas': v_pct_na,
            'whatsapp_received': w['received'],
            'whatsapp_pct_atendidas': w['pct_atendidas'],
            'whatsapp_pct_no_atendidas': w['pct_no_atendidas'],
            'facebook_received': f['received'],
            'facebook_pct_atendidas': f['pct_atendidas'],
            'facebook_pct_no_atendidas': f['pct_no_atendidas'],
        })

    # Filtrar por rango horario si viene definido
    if hora_desde is not None and hora_hasta is not None:
        hour_begin = hora_desde.hour
        hour_end = hora_hasta.hour
        if hour_begin <= hour_end:
            result = [r for r in result if hour_begin <= r['hour'] <= hour_end]
        else:
            result = [
                r for r in result
                if r['hour'] >= hour_begin or r['hour'] <= hour_end
            ]
            result.sort(key=lambda r: (r['hour'] + 24) if r['hour'] < hour_begin else r['hour'])

    if not result:
        return [], None

    # Totales exactos sobre las filas visibles (desde los datos por hora)
    tot_v_r = sum(
        voice_by_hour.get(r['hour'], {}).get('received', 0) for r in result
    )
    tot_v_a = sum(
        voice_by_hour.get(r['hour'], {}).get('answered', 0) for r in result
    )
    tot_wa_r = sum(
        wa_by_hour.get(r['hour'], {}).get('received', 0) for r in result
    )
    tot_wa_a = sum(
        wa_by_hour.get(r['hour'], {}).get('atendidas', 0) for r in result
    )
    tot_fb_r = sum(
        fb_by_hour.get(r['hour'], {}).get('received', 0) for r in result
    )
    tot_fb_a = sum(
        fb_by_hour.get(r['hour'], {}).get('answered', 0) for r in result
    )

    def _totals_pct(rec, ans):
        no_ans = rec - ans
        pct_a = round(100.0 * ans / rec, 2) if rec else 0.0
        pct_na = round(100.0 * no_ans / rec, 2) if rec else 0.0
        return pct_a, pct_na

    v_pct_a, v_pct_na = _totals_pct(tot_v_r, tot_v_a)
    w_pct_a, w_pct_na = _totals_pct(tot_wa_r, tot_wa_a)
    f_pct_a, f_pct_na = _totals_pct(tot_fb_r, tot_fb_a)

    canalidades_por_hora_totals = {
        'llamadas_received': tot_v_r,
        'llamadas_pct_atendidas': v_pct_a,
        'llamadas_pct_no_atendidas': v_pct_na,
        'whatsapp_received': tot_wa_r,
        'whatsapp_pct_atendidas': w_pct_a,
        'whatsapp_pct_no_atendidas': w_pct_na,
        'facebook_received': tot_fb_r,
        'facebook_pct_atendidas': f_pct_a,
        'facebook_pct_no_atendidas': f_pct_na,
    }
    return result, canalidades_por_hora_totals


def obtener_canalidades_por_dia(start_date=None, end_date=None,
                                allowed_campaigns=None, allowed_agent_ids=None,
                                customer_id=None, address_query=None,
                                direction_filter='INBOUND',
                                hora_desde=None, hora_hasta=None,
                                duracion_agente_min=None, duracion_bot_min=None):
    """
    Agrupa interacciones por día (fecha) por canal (Voz, WhatsApp, Facebook)
    sin diferenciar campañas. Mismos criterios que obtener_canalidades_por_campana:
    Voz/Facebook desde InteractionsSummary (atendido=EXIT_ANSWERED), WhatsApp desde
    ConversacionWhatsapp (atendida=True). Retorna (lista de dicts por día, dict totals).
    """
    Q_voice = Q(channel_type__iexact='VOICE')
    Q_fb = Q(channel_type__iexact='FBMSN') | Q(channel_type__iexact='FACEBOOK_MSN')
    Q_answered = Q(status__iexact='EXIT_ANSWERED')

    # Voz: InteractionsSummary por día
    qs_voice = InteractionsSummary.objects.filter(
        direction__iexact=direction_filter
    ).filter(Q_voice)
    if allowed_campaigns is not None:
        qs_voice = qs_voice.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        qs_voice = qs_voice.filter(start_time__gte=start_date)
    if end_date:
        qs_voice = qs_voice.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        qs_voice = qs_voice.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        qs_voice = qs_voice.filter(customer_id=customer_id)
    if address_query:
        qs_voice = qs_voice.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        qs_voice = qs_voice.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_voice = qs_voice.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        qs_voice = qs_voice.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        qs_voice = qs_voice.filter(bot_duration__gte=duracion_bot_min)

    voice_rows = list(
        qs_voice.annotate(day=TruncDate('start_time'))
        .values('day')
        .annotate(
            voice_received=Count('id'),
            voice_answered=Count('id', filter=Q_answered),
        )
        .order_by('day')
    )
    voice_by_day = {}
    for r in voice_rows:
        d = r['day']
        if d is not None:
            if isinstance(d, datetime):
                d = d.date()
            voice_by_day[d] = {
                'received': r['voice_received'] or 0,
                'answered': r['voice_answered'] or 0,
            }

    # WhatsApp: ConversacionWhatsapp por día
    saliente_wa = direction_filter.upper() == 'OUTBOUND'
    qs_wa = ConversacionWhatsapp.objects.filter(saliente=saliente_wa)
    if start_date:
        qs_wa = qs_wa.filter(timestamp__gte=start_date)
    if end_date:
        qs_wa = qs_wa.filter(timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_wa = qs_wa.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_wa = qs_wa.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_wa = qs_wa.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_wa = qs_wa.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_wa = qs_wa.filter(timestamp__time__lte=hora_hasta)

    wa_rows = list(
        qs_wa.annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(
            wa_received=Count('id'),
            wa_atendidas=Count('id', filter=Q(atendida=True)),
        )
        .order_by('day')
    )
    wa_by_day = {}
    for r in wa_rows:
        d = r['day']
        if d is not None:
            if isinstance(d, datetime):
                d = d.date()
            rec = r['wa_received'] or 0
            at = r['wa_atendidas'] or 0
            wa_by_day[d] = {
                'received': rec,
                'atendidas': at,
                'pct_atendidas': round(100.0 * at / rec, 2) if rec else 0.0,
                'pct_no_atendidas': round(100.0 * (rec - at) / rec, 2) if rec else 0.0,
            }

    # Facebook: InteractionsSummary por día
    qs_fb = InteractionsSummary.objects.filter(
        direction__iexact=direction_filter
    ).filter(Q_fb)
    if allowed_campaigns is not None:
        qs_fb = qs_fb.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        qs_fb = qs_fb.filter(start_time__gte=start_date)
    if end_date:
        qs_fb = qs_fb.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        qs_fb = qs_fb.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        qs_fb = qs_fb.filter(customer_id=customer_id)
    if address_query:
        qs_fb = qs_fb.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        qs_fb = qs_fb.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_fb = qs_fb.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        qs_fb = qs_fb.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        qs_fb = qs_fb.filter(bot_duration__gte=duracion_bot_min)

    fb_rows = list(
        qs_fb.annotate(day=TruncDate('start_time'))
        .values('day')
        .annotate(
            fb_received=Count('id'),
            fb_answered=Count('id', filter=Q_answered),
        )
        .order_by('day')
    )
    fb_by_day = {}
    for r in fb_rows:
        d = r['day']
        if d is not None:
            if isinstance(d, datetime):
                d = d.date()
            rec = r['fb_received'] or 0
            ans = r['fb_answered'] or 0
            fb_by_day[d] = {
                'received': rec,
                'answered': ans,
                'pct_atendidas': round(100.0 * ans / rec, 2) if rec else 0.0,
                'pct_no_atendidas': round(100.0 * (rec - ans) / rec, 2) if rec else 0.0,
            }

    def _pcts(received, answered):
        rec = received or 0
        ans = answered or 0
        no_ans = rec - ans
        pct_a = round(100.0 * ans / rec, 2) if rec else 0.0
        pct_na = round(100.0 * no_ans / rec, 2) if rec else 0.0
        return pct_a, pct_na

    # Una fila por cada día en el rango [start_date.date(), end_date.date()]
    result = []
    if start_date and end_date:
        start_d = start_date.date() if hasattr(start_date, 'date') else start_date
        end_d = end_date.date() if hasattr(end_date, 'date') else end_date
        d = start_d
        while d <= end_d:
            v = voice_by_day.get(d, {'received': 0, 'answered': 0})
            w = wa_by_day.get(d, {
                'received': 0, 'atendidas': 0, 'pct_atendidas': 0.0, 'pct_no_atendidas': 0.0
            })
            f = fb_by_day.get(d, {
                'received': 0, 'answered': 0, 'pct_atendidas': 0.0, 'pct_no_atendidas': 0.0
            })
            v_pct_a, v_pct_na = _pcts(v['received'], v['answered'])
            result.append({
                'date': d,
                'date_label': d.strftime('%d/%m/%Y'),
                'llamadas_received': v['received'],
                'llamadas_pct_atendidas': v_pct_a,
                'llamadas_pct_no_atendidas': v_pct_na,
                'whatsapp_received': w['received'],
                'whatsapp_pct_atendidas': w['pct_atendidas'],
                'whatsapp_pct_no_atendidas': w['pct_no_atendidas'],
                'facebook_received': f['received'],
                'facebook_pct_atendidas': f['pct_atendidas'],
                'facebook_pct_no_atendidas': f['pct_no_atendidas'],
            })
            d += timedelta(days=1)
    else:
        all_days = sorted(set(voice_by_day.keys()) | set(wa_by_day.keys()) | set(fb_by_day.keys()))
        for day in all_days:
            v = voice_by_day.get(day, {'received': 0, 'answered': 0})
            w = wa_by_day.get(day, {
                'received': 0, 'atendidas': 0, 'pct_atendidas': 0.0, 'pct_no_atendidas': 0.0
            })
            f = fb_by_day.get(day, {
                'received': 0, 'answered': 0, 'pct_atendidas': 0.0, 'pct_no_atendidas': 0.0
            })
            v_pct_a, v_pct_na = _pcts(v['received'], v['answered'])
            result.append({
                'date': day,
                'date_label': day.strftime('%d/%m/%Y'),
                'llamadas_received': v['received'],
                'llamadas_pct_atendidas': v_pct_a,
                'llamadas_pct_no_atendidas': v_pct_na,
                'whatsapp_received': w['received'],
                'whatsapp_pct_atendidas': w['pct_atendidas'],
                'whatsapp_pct_no_atendidas': w['pct_no_atendidas'],
                'facebook_received': f['received'],
                'facebook_pct_atendidas': f['pct_atendidas'],
                'facebook_pct_no_atendidas': f['pct_no_atendidas'],
            })

    if not result:
        return [], None

    tot_v_r = sum(r['llamadas_received'] for r in result)
    tot_v_a = sum(
        voice_by_day.get(r['date'], {}).get('answered', 0) for r in result
    )
    tot_wa_r = sum(r['whatsapp_received'] for r in result)
    tot_wa_a = sum(
        wa_by_day.get(r['date'], {}).get('atendidas', 0) for r in result
    )
    tot_fb_r = sum(r['facebook_received'] for r in result)
    tot_fb_a = sum(
        fb_by_day.get(r['date'], {}).get('answered', 0) for r in result
    )

    def _totals_pct(rec, ans):
        no_ans = rec - ans
        pct_a = round(100.0 * ans / rec, 2) if rec else 0.0
        pct_na = round(100.0 * no_ans / rec, 2) if rec else 0.0
        return pct_a, pct_na

    v_pct_a, v_pct_na = _totals_pct(tot_v_r, tot_v_a)
    w_pct_a, w_pct_na = _totals_pct(tot_wa_r, tot_wa_a)
    f_pct_a, f_pct_na = _totals_pct(tot_fb_r, tot_fb_a)

    canalidades_por_dia_totals = {
        'llamadas_received': tot_v_r,
        'llamadas_pct_atendidas': v_pct_a,
        'llamadas_pct_no_atendidas': v_pct_na,
        'whatsapp_received': tot_wa_r,
        'whatsapp_pct_atendidas': w_pct_a,
        'whatsapp_pct_no_atendidas': w_pct_na,
        'facebook_received': tot_fb_r,
        'facebook_pct_atendidas': f_pct_a,
        'facebook_pct_no_atendidas': f_pct_na,
    }

    return result, canalidades_por_dia_totals


def _month_key(d):
    """Convierte fecha/datetime a (year, month) para usar como clave."""
    if d is None:
        return None
    if hasattr(d, 'date'):
        d = d.date()
    return (d.year, d.month)


def _next_month(year, month):
    """Devuelve (year, month) del mes siguiente."""
    if month == 12:
        return (year + 1, 1)
    return (year, month + 1)


def obtener_canalidades_por_mes(start_date=None, end_date=None,
                               allowed_campaigns=None, allowed_agent_ids=None,
                               customer_id=None, address_query=None,
                               direction_filter='INBOUND',
                               hora_desde=None, hora_hasta=None,
                               duracion_agente_min=None, duracion_bot_min=None):
    """
    Agrupa interacciones por mes por canal (Voz, WhatsApp, Facebook)
    sin diferenciar campañas. Mismos criterios que obtener_canalidades_por_dia:
    Voz/Facebook desde InteractionsSummary (atendido=EXIT_ANSWERED), WhatsApp desde
    ConversacionWhatsapp (atendida=True). Retorna (lista de dicts por mes, dict totals).
    """
    Q_voice = Q(channel_type__iexact='VOICE')
    Q_fb = Q(channel_type__iexact='FBMSN') | Q(channel_type__iexact='FACEBOOK_MSN')
    Q_answered = Q(status__iexact='EXIT_ANSWERED')

    # Voz: InteractionsSummary por mes
    qs_voice = InteractionsSummary.objects.filter(
        direction__iexact=direction_filter
    ).filter(Q_voice)
    if allowed_campaigns is not None:
        qs_voice = qs_voice.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        qs_voice = qs_voice.filter(start_time__gte=start_date)
    if end_date:
        qs_voice = qs_voice.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        qs_voice = qs_voice.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        qs_voice = qs_voice.filter(customer_id=customer_id)
    if address_query:
        qs_voice = qs_voice.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        qs_voice = qs_voice.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_voice = qs_voice.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        qs_voice = qs_voice.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        qs_voice = qs_voice.filter(bot_duration__gte=duracion_bot_min)

    voice_rows = list(
        qs_voice.annotate(month=TruncMonth('start_time'))
        .values('month')
        .annotate(
            voice_received=Count('id'),
            voice_answered=Count('id', filter=Q_answered),
        )
        .order_by('month')
    )
    voice_by_month = {}
    for r in voice_rows:
        m = r['month']
        key = _month_key(m)
        if key is not None:
            voice_by_month[key] = {
                'received': r['voice_received'] or 0,
                'answered': r['voice_answered'] or 0,
            }

    # WhatsApp: ConversacionWhatsapp por mes
    saliente_wa = direction_filter.upper() == 'OUTBOUND'
    qs_wa = ConversacionWhatsapp.objects.filter(saliente=saliente_wa)
    if start_date:
        qs_wa = qs_wa.filter(timestamp__gte=start_date)
    if end_date:
        qs_wa = qs_wa.filter(timestamp__lte=end_date)
    if allowed_campaigns is not None:
        qs_wa = qs_wa.filter(
            Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
        )
    if allowed_agent_ids is not None:
        qs_wa = qs_wa.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True)
        )
    if address_query:
        qs_wa = qs_wa.filter(destination__icontains=address_query)
    if hora_desde is not None:
        qs_wa = qs_wa.filter(timestamp__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_wa = qs_wa.filter(timestamp__time__lte=hora_hasta)

    wa_rows = list(
        qs_wa.annotate(month=TruncMonth('timestamp'))
        .values('month')
        .annotate(
            wa_received=Count('id'),
            wa_atendidas=Count('id', filter=Q(atendida=True)),
        )
        .order_by('month')
    )
    wa_by_month = {}
    for r in wa_rows:
        key = _month_key(r['month'])
        if key is not None:
            rec = r['wa_received'] or 0
            at = r['wa_atendidas'] or 0
            wa_by_month[key] = {
                'received': rec,
                'atendidas': at,
                'pct_atendidas': round(100.0 * at / rec, 2) if rec else 0.0,
                'pct_no_atendidas': round(100.0 * (rec - at) / rec, 2) if rec else 0.0,
            }

    # Facebook: InteractionsSummary por mes
    qs_fb = InteractionsSummary.objects.filter(
        direction__iexact=direction_filter
    ).filter(Q_fb)
    if allowed_campaigns is not None:
        qs_fb = qs_fb.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        qs_fb = qs_fb.filter(start_time__gte=start_date)
    if end_date:
        qs_fb = qs_fb.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        qs_fb = qs_fb.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        qs_fb = qs_fb.filter(customer_id=customer_id)
    if address_query:
        qs_fb = qs_fb.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        qs_fb = qs_fb.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        qs_fb = qs_fb.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        qs_fb = qs_fb.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        qs_fb = qs_fb.filter(bot_duration__gte=duracion_bot_min)

    fb_rows = list(
        qs_fb.annotate(month=TruncMonth('start_time'))
        .values('month')
        .annotate(
            fb_received=Count('id'),
            fb_answered=Count('id', filter=Q_answered),
        )
        .order_by('month')
    )
    fb_by_month = {}
    for r in fb_rows:
        key = _month_key(r['month'])
        if key is not None:
            rec = r['fb_received'] or 0
            ans = r['fb_answered'] or 0
            fb_by_month[key] = {
                'received': rec,
                'answered': ans,
                'pct_atendidas': round(100.0 * ans / rec, 2) if rec else 0.0,
                'pct_no_atendidas': round(100.0 * (rec - ans) / rec, 2) if rec else 0.0,
            }

    def _pcts(received, answered):
        rec = received or 0
        ans = answered or 0
        no_ans = rec - ans
        pct_a = round(100.0 * ans / rec, 2) if rec else 0.0
        pct_na = round(100.0 * no_ans / rec, 2) if rec else 0.0
        return pct_a, pct_na

    result = []
    if start_date and end_date:
        start_d = start_date.date() if hasattr(start_date, 'date') else start_date
        end_d = end_date.date() if hasattr(end_date, 'date') else end_date
        y, m = start_d.year, start_d.month
        end_y, end_m = end_d.year, end_d.month
        while (y, m) <= (end_y, end_m):
            key = (y, m)
            v = voice_by_month.get(key, {'received': 0, 'answered': 0})
            w = wa_by_month.get(key, {
                'received': 0, 'atendidas': 0, 'pct_atendidas': 0.0, 'pct_no_atendidas': 0.0
            })
            f = fb_by_month.get(key, {
                'received': 0, 'answered': 0, 'pct_atendidas': 0.0, 'pct_no_atendidas': 0.0
            })
            v_pct_a, v_pct_na = _pcts(v['received'], v['answered'])
            month_label = '{:02d}/{}'.format(m, y)
            result.append({
                'month': date(y, m, 1),
                'month_label': month_label,
                'llamadas_received': v['received'],
                'llamadas_pct_atendidas': v_pct_a,
                'llamadas_pct_no_atendidas': v_pct_na,
                'whatsapp_received': w['received'],
                'whatsapp_pct_atendidas': w['pct_atendidas'],
                'whatsapp_pct_no_atendidas': w['pct_no_atendidas'],
                'facebook_received': f['received'],
                'facebook_pct_atendidas': f['pct_atendidas'],
                'facebook_pct_no_atendidas': f['pct_no_atendidas'],
            })
            y, m = _next_month(y, m)

    if not result:
        return [], None

    tot_v_r = sum(r['llamadas_received'] for r in result)
    tot_v_a = sum(
        voice_by_month.get((r['month'].year, r['month'].month), {}).get('answered', 0)
        for r in result
    )
    tot_wa_r = sum(r['whatsapp_received'] for r in result)
    tot_wa_a = sum(
        wa_by_month.get((r['month'].year, r['month'].month), {}).get('atendidas', 0)
        for r in result
    )
    tot_fb_r = sum(r['facebook_received'] for r in result)
    tot_fb_a = sum(
        fb_by_month.get((r['month'].year, r['month'].month), {}).get('answered', 0)
        for r in result
    )

    def _totals_pct(rec, ans):
        no_ans = rec - ans
        pct_a = round(100.0 * ans / rec, 2) if rec else 0.0
        pct_na = round(100.0 * no_ans / rec, 2) if rec else 0.0
        return pct_a, pct_na

    v_pct_a, v_pct_na = _totals_pct(tot_v_r, tot_v_a)
    w_pct_a, w_pct_na = _totals_pct(tot_wa_r, tot_wa_a)
    f_pct_a, f_pct_na = _totals_pct(tot_fb_r, tot_fb_a)

    canalidades_por_mes_totals = {
        'llamadas_received': tot_v_r,
        'llamadas_pct_atendidas': v_pct_a,
        'llamadas_pct_no_atendidas': v_pct_na,
        'whatsapp_received': tot_wa_r,
        'whatsapp_pct_atendidas': w_pct_a,
        'whatsapp_pct_no_atendidas': w_pct_na,
        'facebook_received': tot_fb_r,
        'facebook_pct_atendidas': f_pct_a,
        'facebook_pct_no_atendidas': f_pct_na,
    }

    return result, canalidades_por_mes_totals


def obtener_llamadas_por_hora(start_date=None, end_date=None,
                              allowed_campaigns=None, allowed_agent_ids=None,
                              customer_id=None, address_query=None,
                              direction_filter=None,
                              hora_desde=None, hora_hasta=None,
                              duracion_agente_min=None, duracion_bot_min=None):
    """
    Agrupa interacciones por hora del día (0-23) con los mismos filtros que
    obtener_llamadas_por_campana. Retorna lista de 24 dicts (una fila por hora)
    con hour_label, received, answered, unanswered, abandoned, transferred,
    avg_wait_seconds, avg_talk_seconds, pct_answered, pct_unanswered,
    pct_abandoned, pct_transferred.
    """
    queryset = InteractionsSummary.objects.all()
    if direction_filter:
        queryset = queryset.filter(direction__iexact=direction_filter)
    if allowed_campaigns is not None:
        queryset = queryset.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)

    Q_answered = Q(status__iexact='EXIT_ANSWERED')
    Q_abandoned = Q(
        status__in=[
            'EXIT_ABANDON',
            'EXIT_TIMEOUT',
            'EXIT_HANDOFF_ABANDON',
            'EXIT_HANDOFF_TIMEOUT',
        ]
    )

    rows = (
        queryset
        .annotate(hour=ExtractHour('start_time'))
        .values('hour')
        .annotate(
            received=Count('id'),
            answered=Count('id', filter=Q_answered),
            unanswered=Count('id', filter=~Q_answered),
            abandoned=Count('id', filter=Q_abandoned),
            transferred=Count('id', filter=Q(is_transferred=True)),
            avg_wait=Avg('wait_conn_duration', filter=Q_answered),
            avg_talk=Avg('agent_duration', filter=Q_answered),
        )
        .order_by('hour')
    )

    data_by_hour = {}
    for r in rows:
        h = r['hour']
        if h is None:
            continue
        h = int(h) % 24
        received = r['received'] or 0
        answered = r['answered'] or 0
        unanswered = r['unanswered'] or 0
        abandoned = r['abandoned'] or 0
        transferred = r['transferred'] or 0
        avg_wait = r['avg_wait']
        avg_talk = r['avg_talk']
        pct_answered = (100.0 * answered / received) if received else 0.0
        pct_unanswered = (100.0 * unanswered / received) if received else 0.0
        pct_abandoned = (100.0 * abandoned / received) if received else 0.0
        pct_transferred = (100.0 * transferred / received) if received else 0.0
        data_by_hour[h] = {
            'received': received,
            'answered': answered,
            'unanswered': unanswered,
            'abandoned': abandoned,
            'transferred': transferred,
            'avg_wait_seconds': _decimal_to_float(avg_wait) if avg_wait is not None else None,
            'avg_talk_seconds': _decimal_to_float(avg_talk) if avg_talk is not None else None,
            'pct_answered': round(pct_answered, 2),
            'pct_unanswered': round(pct_unanswered, 2),
            'pct_abandoned': round(pct_abandoned, 2),
            'pct_transferred': round(pct_transferred, 2),
        }

    result = []
    for h in range(24):
        hour_label = '{0:02d}:00'.format(h)
        if h in data_by_hour:
            row = data_by_hour[h].copy()
            row['hour'] = h
            row['hour_label'] = hour_label
        else:
            row = {
                'hour': h,
                'hour_label': hour_label,
                'received': 0,
                'answered': 0,
                'unanswered': 0,
                'abandoned': 0,
                'transferred': 0,
                'avg_wait_seconds': None,
                'avg_talk_seconds': None,
                'pct_answered': 0.0,
                'pct_unanswered': 0.0,
                'pct_abandoned': 0.0,
                'pct_transferred': 0.0,
            }
        result.append(row)
    return result


def obtener_llamadas_por_dia(start_date=None, end_date=None,
                             allowed_campaigns=None, allowed_agent_ids=None,
                             customer_id=None, address_query=None,
                             direction_filter=None,
                             hora_desde=None, hora_hasta=None,
                             duracion_agente_min=None, duracion_bot_min=None):
    """
    Agrupa interacciones por día (fecha) con los mismos filtros que
    obtener_llamadas_por_campana. Retorna lista de dicts (una fila por día)
    con date, date_label, received, answered, unanswered, abandoned, transferred,
    avg_wait_seconds, avg_talk_seconds, pct_*.
    """
    queryset = InteractionsSummary.objects.all()
    if direction_filter:
        queryset = queryset.filter(direction__iexact=direction_filter)
    if allowed_campaigns is not None:
        queryset = queryset.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)

    Q_answered = Q(status__iexact='EXIT_ANSWERED')
    Q_abandoned = Q(
        status__in=[
            'EXIT_ABANDON',
            'EXIT_TIMEOUT',
            'EXIT_HANDOFF_ABANDON',
            'EXIT_HANDOFF_TIMEOUT',
        ]
    )

    rows = (
        queryset
        .annotate(day=TruncDate('start_time'))
        .values('day')
        .annotate(
            received=Count('id'),
            answered=Count('id', filter=Q_answered),
            unanswered=Count('id', filter=~Q_answered),
            abandoned=Count('id', filter=Q_abandoned),
            transferred=Count('id', filter=Q(is_transferred=True)),
            avg_wait=Avg('wait_conn_duration', filter=Q_answered),
            avg_talk=Avg('agent_duration', filter=Q_answered),
        )
        .order_by('day')
    )

    data_by_day = {}
    for r in rows:
        day = r['day']
        if day is None:
            continue
        received = r['received'] or 0
        answered = r['answered'] or 0
        unanswered = r['unanswered'] or 0
        abandoned = r['abandoned'] or 0
        transferred = r['transferred'] or 0
        avg_wait = r['avg_wait']
        avg_talk = r['avg_talk']
        pct_answered = (100.0 * answered / received) if received else 0.0
        pct_unanswered = (100.0 * unanswered / received) if received else 0.0
        pct_abandoned = (100.0 * abandoned / received) if received else 0.0
        pct_transferred = (100.0 * transferred / received) if received else 0.0
        data_by_day[day] = {
            'date': day,
            'date_label': day.strftime('%d/%m'),
            'received': received,
            'answered': answered,
            'unanswered': unanswered,
            'abandoned': abandoned,
            'transferred': transferred,
            'avg_wait_seconds': _decimal_to_float(avg_wait) if avg_wait is not None else None,
            'avg_talk_seconds': _decimal_to_float(avg_talk) if avg_talk is not None else None,
            'pct_answered': round(pct_answered, 2),
            'pct_unanswered': round(pct_unanswered, 2),
            'pct_abandoned': round(pct_abandoned, 2),
            'pct_transferred': round(pct_transferred, 2),
        }

    # Una fila por cada día en el rango [start_date.date(), end_date.date()]
    result = []
    if start_date and end_date:
        from datetime import timedelta
        start_d = start_date.date() if hasattr(start_date, 'date') else start_date
        end_d = end_date.date() if hasattr(end_date, 'date') else end_date
        d = start_d
        while d <= end_d:
            if d in data_by_day:
                result.append(data_by_day[d].copy())
            else:
                result.append({
                    'date': d,
                    'date_label': d.strftime('%d/%m'),
                    'received': 0,
                    'answered': 0,
                    'unanswered': 0,
                    'abandoned': 0,
                    'transferred': 0,
                    'avg_wait_seconds': None,
                    'avg_talk_seconds': None,
                    'pct_answered': 0.0,
                    'pct_unanswered': 0.0,
                    'pct_abandoned': 0.0,
                    'pct_transferred': 0.0,
                })
            d += timedelta(days=1)
    else:
        for day in sorted(data_by_day.keys()):
            result.append(data_by_day[day].copy())
    return result


def obtener_llamadas_por_mes(start_date=None, end_date=None,
                              allowed_campaigns=None, allowed_agent_ids=None,
                              customer_id=None, address_query=None,
                              direction_filter=None,
                              hora_desde=None, hora_hasta=None,
                              duracion_agente_min=None, duracion_bot_min=None):
    """
    Agrupa interacciones por mes con los mismos filtros que obtener_llamadas_por_dia.
    Retorna lista de dicts (una fila por mes) con month, month_label (nombre traducido),
    received, answered, unanswered, abandoned, transferred, avg_wait_seconds, avg_talk_seconds, pct_*.
    """
    from datetime import date
    queryset = InteractionsSummary.objects.all()
    if direction_filter:
        queryset = queryset.filter(direction__iexact=direction_filter)
    if allowed_campaigns is not None:
        queryset = queryset.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)

    Q_answered = Q(status__iexact='EXIT_ANSWERED')
    Q_abandoned = Q(
        status__in=[
            'EXIT_ABANDON',
            'EXIT_TIMEOUT',
            'EXIT_HANDOFF_ABANDON',
            'EXIT_HANDOFF_TIMEOUT',
        ]
    )

    rows = (
        queryset
        .annotate(month=TruncMonth('start_time'))
        .values('month')
        .annotate(
            received=Count('id'),
            answered=Count('id', filter=Q_answered),
            unanswered=Count('id', filter=~Q_answered),
            abandoned=Count('id', filter=Q_abandoned),
            transferred=Count('id', filter=Q(is_transferred=True)),
            avg_wait=Avg('wait_conn_duration', filter=Q_answered),
            avg_talk=Avg('agent_duration', filter=Q_answered),
        )
        .order_by('month')
    )

    data_by_month = {}
    for r in rows:
        month_date = r['month']
        if month_date is None:
            continue
        received = r['received'] or 0
        answered = r['answered'] or 0
        unanswered = r['unanswered'] or 0
        abandoned = r['abandoned'] or 0
        transferred = r['transferred'] or 0
        avg_wait = r['avg_wait']
        avg_talk = r['avg_talk']
        pct_answered = (100.0 * answered / received) if received else 0.0
        pct_unanswered = (100.0 * unanswered / received) if received else 0.0
        pct_abandoned = (100.0 * abandoned / received) if received else 0.0
        pct_transferred = (100.0 * transferred / received) if received else 0.0
        month_label = MONTHS[month_date.month] if 1 <= month_date.month <= 12 else month_date.strftime('%B')
        data_by_month[month_date] = {
            'month': month_date,
            'month_label': month_label,
            'received': received,
            'answered': answered,
            'unanswered': unanswered,
            'abandoned': abandoned,
            'transferred': transferred,
            'avg_wait_seconds': _decimal_to_float(avg_wait) if avg_wait is not None else None,
            'avg_talk_seconds': _decimal_to_float(avg_talk) if avg_talk is not None else None,
            'pct_answered': round(pct_answered, 2),
            'pct_unanswered': round(pct_unanswered, 2),
            'pct_abandoned': round(pct_abandoned, 2),
            'pct_transferred': round(pct_transferred, 2),
        }

    result = []
    if start_date and end_date:
        start_d = start_date.date() if hasattr(start_date, 'date') else start_date
        end_d = end_date.date() if hasattr(end_date, 'date') else end_date
        y, m = start_d.year, start_d.month
        end_y, end_m = end_d.year, end_d.month
        while (y, m) <= (end_y, end_m):
            first = date(y, m, 1)
            if first in data_by_month:
                result.append(data_by_month[first].copy())
            else:
                result.append({
                    'month': first,
                    'month_label': MONTHS[m] if 1 <= m <= 12 else first.strftime('%B'),
                    'received': 0,
                    'answered': 0,
                    'unanswered': 0,
                    'abandoned': 0,
                    'transferred': 0,
                    'avg_wait_seconds': None,
                    'avg_talk_seconds': None,
                    'pct_answered': 0.0,
                    'pct_unanswered': 0.0,
                    'pct_abandoned': 0.0,
                    'pct_transferred': 0.0,
                })
            if m == 12:
                y, m = y + 1, 1
            else:
                m += 1
    else:
        for month_date in sorted(data_by_month.keys()):
            result.append(data_by_month[month_date].copy())
    return result


# Listados Centro de contacto (voz): "atendidas" incluye contestación por agente
# y cierres tras handoff desde voicebot (espera a humano).
Q_LISTADO_LLAMADAS_ATENDIDAS_CC = (
    Q(status__iexact='EXIT_ANSWERED')
    | Q(status__iexact='EXIT_HANDOFF_ABANDON')
    | Q(status__iexact='EXIT_HANDOFF_TIMEOUT')
)


def obtener_listado_llamadas_atendidas(start_date=None, end_date=None,
                                       allowed_campaigns=None, allowed_agent_ids=None,
                                       customer_id=None, address_query=None,
                                       direction_filter='INBOUND',
                                       hora_desde=None, hora_hasta=None,
                                       duracion_agente_min=None, duracion_bot_min=None,
                                       page=1, page_size=100):
    """
    Listado paginado de llamadas atendidas (voz): EXIT_ANSWERED y cierres post-handoff
    EXIT_HANDOFF_ABANDON / EXIT_HANDOFF_TIMEOUT.
    direction_filter: 'INBOUND' o 'OUTBOUND'. Mismos filtros que obtener_llamadas_por_campana.
    Retorna un Page de Django con object_list siendo lista de dicts con columnas para la tabla
    (fecha_hora, id_contacto, telefono, id_campana, nombre_campana, id_agente, nombre_agente,
    username_agente, grupo_agente, is_transferred, tiempo_espera, duracion_agente, duracion_bot,
    quien_corto, id_calificacion, nombre_calificacion, nombre_subcalificacion, url_grabacion).
    id_calificacion y nombre_calificacion provienen de CalificacionCliente (por callid=interaction_id).
    """
    queryset = InteractionsSummary.objects.filter(
        direction__iexact=direction_filter,
        channel_type__iexact='VOICE',
    ).filter(Q_LISTADO_LLAMADAS_ATENDIDAS_CC)

    if allowed_campaigns is not None:
        queryset = queryset.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)

    queryset = queryset.order_by('-start_time')
    paginator = Paginator(queryset, page_size)
    try:
        page_obj = paginator.page(page)
    except Exception:
        page_obj = paginator.page(1)

    campaign_ids = set()
    agent_ids = set()
    for obj in page_obj.object_list:
        if obj.campaign_id is not None:
            campaign_ids.add(obj.campaign_id)
        if obj.agent_id is not None and obj.agent_id != -1:
            agent_ids.add(obj.agent_id)

    campana_names = {}
    if campaign_ids:
        campana_names = dict(
            Campana.objects.filter(pk__in=campaign_ids).values_list('id', 'nombre')
        )

    agent_info = {}
    if agent_ids:
        for ap in AgenteProfile.objects.filter(
            pk__in=agent_ids
        ).select_related('user', 'grupo'):
            nombre = (ap.user.get_full_name() or ap.user.username) if ap.user else ''
            username = ap.user.username if ap.user else ''
            grupo_nombre = ap.grupo.nombre if ap.grupo else ''
            agent_info[ap.id] = {
                'nombre': nombre,
                'username': username,
                'grupo': grupo_nombre,
            }

    interaction_ids = [obj.interaction_id for obj in page_obj.object_list]
    calificacion_por_callid = {}
    if interaction_ids:
        for cal in CalificacionCliente.objects.filter(
            callid__in=interaction_ids,
        ).select_related('opcion_calificacion').order_by('-id'):
            if cal.callid not in calificacion_por_callid:
                calificacion_por_callid[cal.callid] = {
                    'id': cal.id,
                    'nombre': cal.opcion_calificacion.nombre if cal.opcion_calificacion else '—',
                }

    rows = []
    for obj in page_obj.object_list:
        ag_info = agent_info.get(obj.agent_id) if obj.agent_id else None
        if ag_info is None and obj.agent_id is not None and obj.agent_id != -1:
            ag_info = {'nombre': '', 'username': str(obj.agent_id), 'grupo': ''}
        elif ag_info is None:
            ag_info = {'nombre': '—', 'username': '—', 'grupo': '—'}

        nombre_campana = campana_names.get(obj.campaign_id) if obj.campaign_id else '—'
        if obj.campaign_id and nombre_campana is None:
            nombre_campana = str(obj.campaign_id)

        cal_data = calificacion_por_callid.get(obj.interaction_id)
        if cal_data:
            id_calificacion = cal_data['id']
            nombre_calificacion = cal_data['nombre']
        else:
            id_calificacion = None
            nombre_calificacion = '—'

        subcalificacion = '—'
        if obj.channel_data and isinstance(obj.channel_data, dict):
            subcalificacion = obj.channel_data.get('subcalificacion') or obj.channel_data.get('subcalificacion_nombre') or '—'

        url_grabacion = obj.url_archivo_grabacion_url_encoded if obj.end_time else ''

        wait_sec = _decimal_to_float(obj.wait_conn_duration) if obj.wait_conn_duration is not None else None
        agent_sec = _decimal_to_float(obj.agent_duration) if obj.agent_duration is not None else None
        bot_sec = _decimal_to_float(obj.bot_duration) if obj.bot_duration is not None else None

        rows.append({
            'fecha_hora': obj.start_time,
            'interaction_id': obj.interaction_id,
            'id_contacto': obj.customer_id,
            'telefono': obj.source_address or obj.destination_address or '—',
            'id_campana': obj.campaign_id,
            'nombre_campana': nombre_campana,
            'id_agente': obj.agent_id,
            'nombre_agente': ag_info['nombre'],
            'username_agente': ag_info['username'],
            'grupo_agente': ag_info['grupo'],
            'is_transferred': obj.is_transferred,
            'tiempo_espera': wait_sec,
            'duracion_agente': agent_sec,
            'duracion_bot': bot_sec,
            'quien_corto': obj.hangup_cause or '—',
            'id_calificacion': id_calificacion,
            'nombre_calificacion': nombre_calificacion,
            'nombre_subcalificacion': subcalificacion,
            'url_grabacion': url_grabacion or '',
        })

    page_obj.object_list = rows
    return page_obj


def obtener_listado_llamadas_no_atendidas(start_date=None, end_date=None,
                                          allowed_campaigns=None, allowed_agent_ids=None,
                                          customer_id=None, address_query=None,
                                          direction_filter='INBOUND',
                                          hora_desde=None, hora_hasta=None,
                                          duracion_agente_min=None, duracion_bot_min=None,
                                          page=1, page_size=100):
    """
    Listado paginado de llamadas no atendidas (voz): excluye EXIT_ANSWERED y cierres
    post-handoff EXIT_HANDOFF_ABANDON / EXIT_HANDOFF_TIMEOUT (mismo criterio que listado atendidas).
    direction_filter: 'INBOUND' o 'OUTBOUND'. Mismos filtros que obtener_listado_llamadas_atendidas.
    Retorna un Page con object_list de dicts con: fecha_hora, id_contacto, telefono,
    id_campana, nombre_campana, tiempo_espera, status.
    """
    queryset = InteractionsSummary.objects.filter(
        direction__iexact=direction_filter,
        channel_type__iexact='VOICE',
    ).exclude(Q_LISTADO_LLAMADAS_ATENDIDAS_CC)

    if allowed_campaigns is not None:
        queryset = queryset.filter(
            Q(campaign_id__in=allowed_campaigns) | Q(campaign_id__isnull=True)
        )
    if start_date:
        queryset = queryset.filter(start_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(start_time__lte=end_date)
    if allowed_agent_ids is not None:
        queryset = queryset.filter(
            Q(agent_id__in=allowed_agent_ids) | Q(agent_id__isnull=True) | Q(agent_id=-1)
        )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if address_query:
        queryset = queryset.filter(
            Q(source_address__icontains=address_query) |
            Q(destination_address__icontains=address_query)
        )
    if hora_desde is not None:
        queryset = queryset.filter(start_time__time__gte=hora_desde)
    if hora_hasta is not None:
        queryset = queryset.filter(start_time__time__lte=hora_hasta)
    if duracion_agente_min is not None:
        queryset = queryset.filter(agent_duration__gte=duracion_agente_min)
    if duracion_bot_min is not None:
        queryset = queryset.filter(bot_duration__gte=duracion_bot_min)

    queryset = queryset.order_by('-start_time')
    paginator = Paginator(queryset, page_size)
    try:
        page_obj = paginator.page(page)
    except Exception:
        page_obj = paginator.page(1)

    campaign_ids = set(obj.campaign_id for obj in page_obj.object_list if obj.campaign_id is not None)
    campana_names = {}
    if campaign_ids:
        campana_names = dict(
            Campana.objects.filter(pk__in=campaign_ids).values_list('id', 'nombre')
        )

    rows = []
    for obj in page_obj.object_list:
        nombre_campana = campana_names.get(obj.campaign_id) if obj.campaign_id else '—'
        if obj.campaign_id and nombre_campana is None:
            nombre_campana = str(obj.campaign_id)
        wait_sec = _decimal_to_float(obj.wait_conn_duration) if obj.wait_conn_duration is not None else None
        rows.append({
            'fecha_hora': obj.start_time,
            'id_contacto': obj.customer_id,
            'telefono': obj.source_address or obj.destination_address or '—',
            'id_campana': obj.campaign_id,
            'nombre_campana': nombre_campana,
            'tiempo_espera': wait_sec,
            'status': obj.status or '—',
        })

    page_obj.object_list = rows
    return page_obj


class ReporteCentroContactoFormView(FormView):
    """
    Vista con formulario (combo de campaña y rango de fechas) que muestra
    los KPIs de rendimiento desde interactions_summary.
    """
    template_name = 'reporte_centro_contacto.html'
    form_class = ReporteCentroContactoForm

    def _get_campanas_visibles(self, incluir_finalizadas=True):
        user = self.request.user
        if user.get_is_administrador():
            campanas = Campana.objects.obtener_actuales()
        else:
            supervisor = user.get_supervisor_profile()
            campanas = supervisor.campanas_asignadas_actuales()

        if not incluir_finalizadas:
            campanas = campanas.exclude(estado=Campana.ESTADO_FINALIZADA)
        return campanas

    def _get_grupos_visibles(self, campanas_visibles):
        return (
            Grupo.objects
            .filter(agentes__campana_member__queue_name__campana__in=campanas_visibles)
            .distinct()
            .order_by('nombre')
        )

    def _get_agentes_visibles(self, campanas_visibles):
        return (
            AgenteProfile.objects
            .filter(campana_member__queue_name__campana__in=campanas_visibles)
            .distinct()
            .select_related('user')
            .order_by('user__first_name', 'user__last_name', 'id')
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        campanas_visibles = self._get_campanas_visibles(incluir_finalizadas=True)
        kwargs['campanas_asignadas'] = campanas_visibles
        kwargs['grupos_agentes'] = self._get_grupos_visibles(campanas_visibles)
        kwargs['agentes_asignados'] = self._get_agentes_visibles(campanas_visibles)
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        hoy = fecha_hora_local(timezone.now()).date()
        initial['fecha'] = '{0} - {1}'.format(
            hoy.strftime('%d/%m/%Y'),
            hoy.strftime('%d/%m/%Y')
        )
        return initial

    def form_valid(self, form):
        campanas_seleccionadas = form.cleaned_data.get('campana') or []
        incluir_finalizadas = form.cleaned_data.get('incluir_finalizadas', False)
        grupos_seleccionados = form.cleaned_data.get('grupo_agente') or []
        agentes_seleccionados = form.cleaned_data.get('agente') or []
        contacto_id = form.cleaned_data.get('contacto_id')
        address_query = form.cleaned_data.get('address')
        campanas_visibles = self._get_campanas_visibles(
            incluir_finalizadas=incluir_finalizadas
        )
        campanas_visibles_ids = list(campanas_visibles.values_list('pk', flat=True))
        grupos_visibles = self._get_grupos_visibles(
            self._get_campanas_visibles(incluir_finalizadas=True)
        )
        grupos_visibles_ids = set(grupos_visibles.values_list('id', flat=True))

        if (
            not campanas_seleccionadas or
            ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE in campanas_seleccionadas
        ):
            allowed_campaigns = campanas_visibles_ids
            campana_nombre = _('Todas las campañas')
        else:
            try:
                selected_campaign_ids = [int(campaign_id) for campaign_id in campanas_seleccionadas]
            except (TypeError, ValueError):
                form.add_error('campana', _('Campaña inválida.'))
                return self.form_invalid(form)

            visible_set = set(campanas_visibles_ids)
            if not set(selected_campaign_ids).issubset(visible_set):
                form.add_error('campana', _('Campaña inválida.'))
                return self.form_invalid(form)

            allowed_campaigns = selected_campaign_ids
            if len(selected_campaign_ids) == 1:
                campana_nombre = (
                    Campana.objects
                    .filter(pk=selected_campaign_ids[0])
                    .values_list('nombre', flat=True)
                    .first() or ''
                )
            else:
                campana_nombre = _('%(count)s campañas seleccionadas') % {
                    'count': len(selected_campaign_ids)
                }

        if (
            not grupos_seleccionados or
            ReporteCentroContactoForm.TODOS_LOS_GRUPOS_VALUE in grupos_seleccionados
        ):
            allowed_agent_ids_by_group = None
            grupo_nombre = _('Todos los grupos de agentes')
        else:
            try:
                selected_group_ids = [int(group_id) for group_id in grupos_seleccionados]
            except (TypeError, ValueError):
                form.add_error('grupo_agente', _('Grupo de agentes inválido.'))
                return self.form_invalid(form)

            if not set(selected_group_ids).issubset(grupos_visibles_ids):
                form.add_error('grupo_agente', _('Grupo de agentes inválido.'))
                return self.form_invalid(form)

            allowed_agent_ids_by_group = list(
                AgenteProfile.objects
                .filter(
                    grupo_id__in=selected_group_ids,
                    campana_member__queue_name__campana_id__in=allowed_campaigns,
                )
                .distinct()
                .values_list('id', flat=True)
            )
            if len(selected_group_ids) == 1:
                grupo_nombre = (
                    Grupo.objects
                    .filter(pk=selected_group_ids[0])
                    .values_list('nombre', flat=True)
                    .first() or ''
                )
            else:
                grupo_nombre = _('%(count)s grupos seleccionados') % {
                    'count': len(selected_group_ids)
                }

        agentes_visibles_ids = set(
            self._get_agentes_visibles(
                campanas_visibles.filter(pk__in=allowed_campaigns)
            ).values_list('id', flat=True)
        )
        if (
            not agentes_seleccionados or
            ReporteCentroContactoForm.TODOS_LOS_AGENTES_VALUE in agentes_seleccionados
        ):
            allowed_agent_ids = allowed_agent_ids_by_group
            agente_nombre = _('Todos los agentes')
        else:
            try:
                selected_agent_ids = [int(agent_id) for agent_id in agentes_seleccionados]
            except (TypeError, ValueError):
                form.add_error('agente', _('Agente inválido.'))
                return self.form_invalid(form)

            if not set(selected_agent_ids).issubset(agentes_visibles_ids):
                form.add_error('agente', _('Agente inválido.'))
                return self.form_invalid(form)

            if allowed_agent_ids_by_group is None:
                allowed_agent_ids = selected_agent_ids
            else:
                allowed_group_set = set(allowed_agent_ids_by_group)
                allowed_agent_ids = [
                    agent_id for agent_id in selected_agent_ids if agent_id in allowed_group_set
                ]

            if len(selected_agent_ids) == 1:
                agente = (
                    AgenteProfile.objects
                    .select_related('user')
                    .filter(pk=selected_agent_ids[0])
                    .first()
                )
                agente_nombre = (
                    agente.user.get_full_name() or agente.user.username
                ) if agente else ''
            else:
                agente_nombre = _('%(count)s agentes seleccionados') % {
                    'count': len(selected_agent_ids)
                }

        if not address_query:
            address_nombre = _('Todos')
        else:
            address_nombre = address_query

        desde = getattr(form, 'desde', None)
        hasta = getattr(form, 'hasta', None)
        hora_desde = form.cleaned_data.get('hora_desde')
        hora_hasta = form.cleaned_data.get('hora_hasta')
        duracion_agente_min = form.cleaned_data.get('duracion_agente_min')
        if duracion_agente_min == 0:
            duracion_agente_min = None
        duracion_bot_min = form.cleaned_data.get('duracion_bot_min')
        if duracion_bot_min == 0:
            duracion_bot_min = None
        kpis = obtener_kpis_centro_contacto(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        llamadas_por_campana = obtener_llamadas_por_campana(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='INBOUND',  # Tab Ingresos: solo llamadas entrantes
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        llamadas_por_campana_totals = None
        if llamadas_por_campana:
            total_received = sum(r['received'] for r in llamadas_por_campana)
            total_answered = sum(r['answered'] for r in llamadas_por_campana)
            total_unanswered = sum(r['unanswered'] for r in llamadas_por_campana)
            total_expired = sum(r['expired'] for r in llamadas_por_campana)
            total_abandoned = sum(r['abandoned'] for r in llamadas_por_campana)
            total_transferred = sum(r['transferred'] for r in llamadas_por_campana)
            llamadas_por_campana_totals = {
                'received': total_received,
                'answered': total_answered,
                'unanswered': total_unanswered,
                'expired': total_expired,
                'abandoned': total_abandoned,
                'transferred': total_transferred,
                'pct_answered': round(100.0 * total_answered / total_received, 2) if total_received else 0.0,
                'pct_unanswered': round(100.0 * total_unanswered / total_received, 2) if total_received else 0.0,
                'pct_expired': round(100.0 * total_expired / total_received, 2) if total_received else 0.0,
                'pct_abandoned': round(100.0 * total_abandoned / total_received, 2) if total_received else 0.0,
                'pct_transferred': round(100.0 * total_transferred / total_received, 2) if total_received else 0.0,
            }
        ingresos_voz_por_campana = obtener_llamadas_por_campana(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            visible_campaigns=campanas_visibles_ids,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='INBOUND',
            channel_filter='VOICE',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        ingresos_voz_por_campana_totals = None
        if ingresos_voz_por_campana:
            total_received = sum(r['received'] for r in ingresos_voz_por_campana)
            total_effective_received = sum(
                r.get('effective_received', r['received']) for r in ingresos_voz_por_campana
            )
            total_answered = sum(r['answered'] for r in ingresos_voz_por_campana)
            total_expired = sum(r['expired'] for r in ingresos_voz_por_campana)
            total_abandoned = sum(r['abandoned'] for r in ingresos_voz_por_campana)
            total_transferred = sum(r['transferred'] for r in ingresos_voz_por_campana)
            total_transfer_in_count = sum(
                r.get('transfer_in_count', 0) for r in ingresos_voz_por_campana
            )
            total_transfer_out_count = sum(
                r.get('transfer_out_count', 0) for r in ingresos_voz_por_campana
            )
            ingresos_voz_por_campana_totals = {
                'received': total_received,
                'answered': total_answered,
                'expired': total_expired,
                'abandoned': total_abandoned,
                'transferred': total_transferred,
                'transfer_in_count': total_transfer_in_count,
                'transfer_out_count': total_transfer_out_count,
                'pct_answered': round(100.0 * total_answered / total_effective_received, 2) if total_effective_received else 0.0,
                'pct_expired': round(100.0 * total_expired / total_effective_received, 2) if total_effective_received else 0.0,
                'pct_abandoned': round(100.0 * total_abandoned / total_effective_received, 2) if total_effective_received else 0.0,
                'pct_transferred': round(100.0 * total_transferred / total_effective_received, 2) if total_effective_received else 0.0,
            }
        canalidades_por_campana, canalidades_por_campana_totals = obtener_canalidades_por_campana(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        llamadas_por_hora = obtener_llamadas_por_hora(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='INBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        # En Ingresos/Voz/Horas: si hay rango horario, mostrar solo las filas de horas en ese rango
        if llamadas_por_hora and hora_desde is not None and hora_hasta is not None:
            hour_begin = hora_desde.hour
            hour_end = hora_hasta.hour
            if hour_begin <= hour_end:
                llamadas_por_hora = [r for r in llamadas_por_hora if hour_begin <= r['hour'] <= hour_end]
            else:
                # rango cruzado (ej. 22:00 a 06:00): incluir hour >= hour_begin o hour <= hour_end
                llamadas_por_hora = [
                    r for r in llamadas_por_hora
                    if r['hour'] >= hour_begin or r['hour'] <= hour_end
                ]
                llamadas_por_hora.sort(key=lambda r: (r['hour'] + 24) if r['hour'] < hour_begin else r['hour'])
        llamadas_por_hora_totals = None
        if llamadas_por_hora:
            total_received = sum(r['received'] for r in llamadas_por_hora)
            total_answered = sum(r['answered'] for r in llamadas_por_hora)
            total_unanswered = sum(r['unanswered'] for r in llamadas_por_hora)
            total_abandoned = sum(r['abandoned'] for r in llamadas_por_hora)
            total_transferred = sum(r['transferred'] for r in llamadas_por_hora)
            llamadas_por_hora_totals = {
                'received': total_received,
                'answered': total_answered,
                'unanswered': total_unanswered,
                'abandoned': total_abandoned,
                'transferred': total_transferred,
                'pct_answered': round(100.0 * total_answered / total_received, 2) if total_received else 0.0,
                'pct_unanswered': round(100.0 * total_unanswered / total_received, 2) if total_received else 0.0,
                'pct_abandoned': round(100.0 * total_abandoned / total_received, 2) if total_received else 0.0,
                'pct_transferred': round(100.0 * total_transferred / total_received, 2) if total_received else 0.0,
            }
        canalidades_por_hora, canalidades_por_hora_totals = obtener_canalidades_por_hora(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='INBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        canalidades_por_dia, canalidades_por_dia_totals = obtener_canalidades_por_dia(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='INBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        canalidades_por_mes, canalidades_por_mes_totals = obtener_canalidades_por_mes(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='INBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        llamadas_por_dia = obtener_llamadas_por_dia(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='INBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        llamadas_por_dia_totals = None
        if llamadas_por_dia:
            total_received = sum(r['received'] for r in llamadas_por_dia)
            total_answered = sum(r['answered'] for r in llamadas_por_dia)
            total_unanswered = sum(r['unanswered'] for r in llamadas_por_dia)
            total_abandoned = sum(r['abandoned'] for r in llamadas_por_dia)
            total_transferred = sum(r['transferred'] for r in llamadas_por_dia)
            llamadas_por_dia_totals = {
                'received': total_received,
                'answered': total_answered,
                'unanswered': total_unanswered,
                'abandoned': total_abandoned,
                'transferred': total_transferred,
                'pct_answered': round(100.0 * total_answered / total_received, 2) if total_received else 0.0,
                'pct_unanswered': round(100.0 * total_unanswered / total_received, 2) if total_received else 0.0,
                'pct_abandoned': round(100.0 * total_abandoned / total_received, 2) if total_received else 0.0,
                'pct_transferred': round(100.0 * total_transferred / total_received, 2) if total_received else 0.0,
            }
        llamadas_por_mes = obtener_llamadas_por_mes(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='INBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        llamadas_por_mes_totals = None
        if llamadas_por_mes:
            total_received = sum(r['received'] for r in llamadas_por_mes)
            total_answered = sum(r['answered'] for r in llamadas_por_mes)
            total_unanswered = sum(r['unanswered'] for r in llamadas_por_mes)
            total_abandoned = sum(r['abandoned'] for r in llamadas_por_mes)
            total_transferred = sum(r['transferred'] for r in llamadas_por_mes)
            llamadas_por_mes_totals = {
                'received': total_received,
                'answered': total_answered,
                'unanswered': total_unanswered,
                'abandoned': total_abandoned,
                'transferred': total_transferred,
                'pct_answered': round(100.0 * total_answered / total_received, 2) if total_received else 0.0,
                'pct_unanswered': round(100.0 * total_unanswered / total_received, 2) if total_received else 0.0,
                'pct_abandoned': round(100.0 * total_abandoned / total_received, 2) if total_received else 0.0,
                'pct_transferred': round(100.0 * total_transferred / total_received, 2) if total_received else 0.0,
            }
        page_listado = 1
        try:
            page_listado = int(
                self.request.POST.get('page_listado') or
                self.request.GET.get('page_listado', 1)
            )
        except (TypeError, ValueError):
            pass
        listado_llamadas_atendidas = obtener_listado_llamadas_atendidas(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
            page=page_listado,
            page_size=100,
        )
        num_pages = listado_llamadas_atendidas.paginator.num_pages
        page_no = listado_llamadas_atendidas.number
        if num_pages <= 7 or page_no <= 4:
            listado_pages = list(range(1, min(num_pages + 1, 8)))
        elif page_no > num_pages - 4:
            listado_pages = list(range(max(1, num_pages - 6), num_pages + 1))
        else:
            listado_pages = list(range(page_no - 3, page_no + 4))

        page_listado_no_atendidas = 1
        try:
            page_listado_no_atendidas = int(
                self.request.POST.get('page_listado_no_atendidas') or
                self.request.GET.get('page_listado_no_atendidas', 1)
            )
        except (TypeError, ValueError):
            pass
        listado_llamadas_no_atendidas = obtener_listado_llamadas_no_atendidas(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
            page=page_listado_no_atendidas,
            page_size=100,
        )
        num_pages_na = listado_llamadas_no_atendidas.paginator.num_pages
        page_no_na = listado_llamadas_no_atendidas.number
        if num_pages_na <= 7 or page_no_na <= 4:
            listado_pages_no_atendidas = list(range(1, min(num_pages_na + 1, 8)))
        elif page_no_na > num_pages_na - 4:
            listado_pages_no_atendidas = list(range(max(1, num_pages_na - 6), num_pages_na + 1))
        else:
            listado_pages_no_atendidas = list(range(page_no_na - 3, page_no_na + 4))

        # WhatsApp Vista B: KPIs FRT/SLA (tiempos de respuesta)
        whatsapp_frt_kpis = None
        listado_whatsapp_frt = None
        listado_pages_whatsapp_frt = []
        if desde is not None and hasta is not None:
            qs_frt = reporte_tiempos_respuesta_whatsapp(desde, hasta, sla_segundos=120)
            if allowed_campaigns is not None:
                qs_frt = qs_frt.filter(campana_id__in=allowed_campaigns)
            if allowed_agent_ids is not None:
                qs_frt = qs_frt.filter(agent_id__in=allowed_agent_ids)
            total_conversaciones = qs_frt.count()
            qs_con_frt = qs_frt.filter(frt_segundos__isnull=False)
            conversaciones_con_frt = qs_con_frt.count()
            agg = qs_con_frt.aggregate(avg=Avg('frt_segundos'))
            avg_frt_segundos = _decimal_to_float(agg['avg']) if agg.get('avg') is not None else None
            cumple_sla_count = qs_con_frt.filter(cumple_sla=True).count()
            cumple_sla_pct = (
                round(100.0 * cumple_sla_count / conversaciones_con_frt, 1)
                if conversaciones_con_frt else None
            )
            fuera_sla_count = conversaciones_con_frt - cumple_sla_count
            whatsapp_frt_kpis = {
                'total_conversaciones': total_conversaciones,
                'conversaciones_con_frt': conversaciones_con_frt,
                'avg_frt_segundos': avg_frt_segundos,
                'cumple_sla_count': cumple_sla_count,
                'cumple_sla_pct': cumple_sla_pct,
                'fuera_sla_count': fuera_sla_count,
                'sla_segundos': 120,
            }
            page_listado_whatsapp_frt = 1
            try:
                page_listado_whatsapp_frt = int(
                    self.request.POST.get('page_listado_whatsapp_frt') or
                    self.request.GET.get('page_listado_whatsapp_frt', 1)
                )
            except (TypeError, ValueError):
                pass
            paginator_wa = Paginator(qs_con_frt.order_by('-timestamp'), 50)
            listado_whatsapp_frt = paginator_wa.get_page(page_listado_whatsapp_frt)
            num_pages_wa = listado_whatsapp_frt.paginator.num_pages
            page_no_wa = listado_whatsapp_frt.number
            if num_pages_wa <= 7 or page_no_wa <= 4:
                listado_pages_whatsapp_frt = list(range(1, min(num_pages_wa + 1, 8)))
            elif page_no_wa > num_pages_wa - 4:
                listado_pages_whatsapp_frt = list(
                    range(max(1, num_pages_wa - 6), num_pages_wa + 1)
                )
            else:
                listado_pages_whatsapp_frt = list(
                    range(page_no_wa - 3, page_no_wa + 4)
                )

        # Resumen Operativo > WhatsApp: KPIs y volumetría desde ConversacionWhatsapp
        kpis_whatsapp_resumen = None
        if desde is not None and hasta is not None:
            qs_wa_base = ConversacionWhatsapp.objects.filter(
                timestamp__gte=desde, timestamp__lte=hasta
            )
            if allowed_campaigns is not None:
                qs_wa_base = qs_wa_base.filter(
                    Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
                )
            if allowed_agent_ids is not None:
                qs_wa_base = qs_wa_base.filter(agent_id__in=allowed_agent_ids)
            if contacto_id is not None:
                qs_wa_base = qs_wa_base.filter(client_id=contacto_id)
            if address_query:
                qs_wa_base = qs_wa_base.filter(destination__icontains=address_query)
            if hora_desde is not None:
                qs_wa_base = qs_wa_base.filter(timestamp__time__gte=hora_desde)
            if hora_hasta is not None:
                qs_wa_base = qs_wa_base.filter(timestamp__time__lte=hora_hasta)

            # FRT y % SLA: reutilizar whatsapp_frt_kpis si ya se calculó
            frt_promedio_segundos = None
            pct_dentro_sla = None
            if whatsapp_frt_kpis:
                frt_promedio_segundos = (
                    int(whatsapp_frt_kpis['avg_frt_segundos'])
                    if whatsapp_frt_kpis.get('avg_frt_segundos') is not None else None
                )
                pct_dentro_sla = whatsapp_frt_kpis.get('cumple_sla_pct')

            # AHT: promedio duración (date_last_interaction - timestamp) para atendidas con agente
            qs_wa_aht = qs_wa_base.filter(
                atendida=True,
                agent_id__isnull=False,
                date_last_interaction__isnull=False,
            )
            qs_wa_aht = anotar_frt_y_duracion(qs_wa_aht)
            agg_aht = qs_wa_aht.aggregate(avg_duracion=Avg('duracion_segundos'))
            aht_segundos = None
            if agg_aht.get('avg_duracion') is not None:
                try:
                    aht_segundos = int(round(float(agg_aht['avg_duracion'])))
                except (TypeError, ValueError):
                    aht_segundos = None

            # Volumetría
            total_wa = qs_wa_base.count()
            atendidas_x_humano = qs_wa_base.filter(
                atendida=True, agent_id__isnull=False
            ).count()
            solo_bot = qs_wa_base.filter(agent_id__isnull=True).count()
            total_inbound = qs_wa_base.filter(saliente=False).count()
            inbound_answered = qs_wa_base.filter(
                saliente=False, atendida=True, agent_id__isnull=False
            ).count()
            qs_inbound_no_atendidas = ConversacionWhatsapp.objects.conversaciones_entrantes_no_atendidas(
                desde, hasta
            )
            if allowed_campaigns is not None:
                qs_inbound_no_atendidas = qs_inbound_no_atendidas.filter(
                    Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
                )
            if allowed_agent_ids is not None:
                qs_inbound_no_atendidas = qs_inbound_no_atendidas.filter(
                    agent_id__in=allowed_agent_ids
                )
            if contacto_id is not None:
                qs_inbound_no_atendidas = qs_inbound_no_atendidas.filter(
                    client_id=contacto_id
                )
            if address_query:
                qs_inbound_no_atendidas = qs_inbound_no_atendidas.filter(
                    destination__icontains=address_query
                )
            if hora_desde is not None:
                qs_inbound_no_atendidas = qs_inbound_no_atendidas.filter(
                    timestamp__time__gte=hora_desde
                )
            if hora_hasta is not None:
                qs_inbound_no_atendidas = qs_inbound_no_atendidas.filter(
                    timestamp__time__lte=hora_hasta
                )
            inbound_abandoned = qs_inbound_no_atendidas.count()
            total_outbound = qs_wa_base.filter(saliente=True).count()
            outbound_answered = qs_wa_base.filter(
                saliente=True, atendida=True
            ).count()
            gestiones_exitosas = qs_wa_base.filter(
                conversation_disposition__isnull=False,
                conversation_disposition__opcion_calificacion__positiva=True,
            ).count()

            kpis_whatsapp_resumen = {
                'frt_promedio_segundos': frt_promedio_segundos,
                'pct_dentro_sla': pct_dentro_sla,
                'sla_segundos': 120,
                'tasa_transferencia_pct': 0.0,
                'aht_segundos': aht_segundos,
                'volumetria': {
                    'total': total_wa,
                    'atendidas_x_humano': atendidas_x_humano,
                    'solo_bot': solo_bot,
                    'total_inbound': total_inbound,
                    'inbound_answered': inbound_answered,
                    'inbound_abandoned': inbound_abandoned,
                    'total_outbound': total_outbound,
                    'outbound_answered': outbound_answered,
                    'gestiones_exitosas': gestiones_exitosas,
                    'transferidas': 0,
                },
            }

        # WhatsApp Ingresos: listado Conversaciones Respondidas
        listado_conv_respondidas_wa = None
        listado_pages_conv_respondidas_wa = []
        if desde is not None and hasta is not None:
            qs_conv_wa = ConversacionWhatsapp.objects.conversaciones_entrantes_atendidas(
                desde, hasta
            )
            if allowed_campaigns is not None:
                qs_conv_wa = qs_conv_wa.filter(
                    Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
                )
            if allowed_agent_ids is not None:
                qs_conv_wa = qs_conv_wa.filter(agent_id__in=allowed_agent_ids)
            if contacto_id is not None:
                qs_conv_wa = qs_conv_wa.filter(client_id=contacto_id)
            if address_query:
                qs_conv_wa = qs_conv_wa.filter(destination__icontains=address_query)
            if hora_desde is not None:
                qs_conv_wa = qs_conv_wa.filter(timestamp__time__gte=hora_desde)
            if hora_hasta is not None:
                qs_conv_wa = qs_conv_wa.filter(timestamp__time__lte=hora_hasta)
            qs_conv_wa = qs_conv_wa.select_related(
                'campana',
                'agent',
                'agent__user',
                'agent__grupo',
                'client',
                'conversation_disposition',
                'conversation_disposition__opcion_calificacion',
            )
            qs_conv_wa = anotar_frt_y_duracion(qs_conv_wa).order_by('-timestamp')
            page_conv_wa = 1
            try:
                page_conv_wa = int(
                    self.request.POST.get('page_listado_conv_respondidas_wa')
                    or self.request.GET.get('page_listado_conv_respondidas_wa', 1)
                )
            except (TypeError, ValueError):
                pass
            paginator_conv_wa = Paginator(qs_conv_wa, 50)
            listado_conv_respondidas_wa = paginator_conv_wa.get_page(page_conv_wa)
            num_pages_conv_wa = listado_conv_respondidas_wa.paginator.num_pages
            page_no_conv_wa = listado_conv_respondidas_wa.number
            if num_pages_conv_wa <= 7 or page_no_conv_wa <= 4:
                listado_pages_conv_respondidas_wa = list(
                    range(1, min(num_pages_conv_wa + 1, 8))
                )
            elif page_no_conv_wa > num_pages_conv_wa - 4:
                listado_pages_conv_respondidas_wa = list(
                    range(max(1, num_pages_conv_wa - 6), num_pages_conv_wa + 1)
                )
            else:
                listado_pages_conv_respondidas_wa = list(
                    range(page_no_conv_wa - 3, page_no_conv_wa + 4)
                )

        # WhatsApp Ingresos: listado Conversaciones No Respondidas
        listado_conv_no_respondidas_wa = None
        listado_pages_conv_no_respondidas_wa = []
        if desde is not None and hasta is not None:
            qs_conv_no_wa = ConversacionWhatsapp.objects.conversaciones_entrantes_no_atendidas(
                desde, hasta
            )
            if allowed_campaigns is not None:
                qs_conv_no_wa = qs_conv_no_wa.filter(
                    Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
                )
            if allowed_agent_ids is not None:
                qs_conv_no_wa = qs_conv_no_wa.filter(agent_id__in=allowed_agent_ids)
            if contacto_id is not None:
                qs_conv_no_wa = qs_conv_no_wa.filter(client_id=contacto_id)
            if address_query:
                qs_conv_no_wa = qs_conv_no_wa.filter(destination__icontains=address_query)
            if hora_desde is not None:
                qs_conv_no_wa = qs_conv_no_wa.filter(timestamp__time__gte=hora_desde)
            if hora_hasta is not None:
                qs_conv_no_wa = qs_conv_no_wa.filter(timestamp__time__lte=hora_hasta)
            qs_conv_no_wa = qs_conv_no_wa.select_related(
                'campana',
                'agent',
                'agent__user',
                'agent__grupo',
                'client',
                'conversation_disposition',
                'conversation_disposition__opcion_calificacion',
            )
            qs_conv_no_wa = anotar_frt_y_duracion(qs_conv_no_wa).order_by('-timestamp')
            page_conv_no_wa = 1
            try:
                page_conv_no_wa = int(
                    self.request.POST.get('page_listado_conv_no_respondidas_wa')
                    or self.request.GET.get('page_listado_conv_no_respondidas_wa', 1)
                )
            except (TypeError, ValueError):
                pass
            paginator_conv_no_wa = Paginator(qs_conv_no_wa, 50)
            listado_conv_no_respondidas_wa = paginator_conv_no_wa.get_page(page_conv_no_wa)
            num_pages_conv_no_wa = listado_conv_no_respondidas_wa.paginator.num_pages
            page_no_conv_no_wa = listado_conv_no_respondidas_wa.number
            if num_pages_conv_no_wa <= 7 or page_no_conv_no_wa <= 4:
                listado_pages_conv_no_respondidas_wa = list(
                    range(1, min(num_pages_conv_no_wa + 1, 8))
                )
            elif page_no_conv_no_wa > num_pages_conv_no_wa - 4:
                listado_pages_conv_no_respondidas_wa = list(
                    range(max(1, num_pages_conv_no_wa - 6), num_pages_conv_no_wa + 1)
                )
            else:
                listado_pages_conv_no_respondidas_wa = list(
                    range(page_no_conv_no_wa - 3, page_no_conv_no_wa + 4)
                )

        # WhatsApp Egresos: listado Conversaciones Respondidas (salientes)
        listado_conv_respondidas_wa_egresos = None
        listado_pages_conv_respondidas_wa_egresos = []
        if desde is not None and hasta is not None:
            qs_conv_wa_egresos = ConversacionWhatsapp.objects.conversaciones_salientes_atendidas(
                desde, hasta
            )
            if allowed_campaigns is not None:
                qs_conv_wa_egresos = qs_conv_wa_egresos.filter(
                    Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
                )
            if allowed_agent_ids is not None:
                qs_conv_wa_egresos = qs_conv_wa_egresos.filter(agent_id__in=allowed_agent_ids)
            if contacto_id is not None:
                qs_conv_wa_egresos = qs_conv_wa_egresos.filter(client_id=contacto_id)
            if address_query:
                qs_conv_wa_egresos = qs_conv_wa_egresos.filter(
                    destination__icontains=address_query
                )
            if hora_desde is not None:
                qs_conv_wa_egresos = qs_conv_wa_egresos.filter(
                    timestamp__time__gte=hora_desde
                )
            if hora_hasta is not None:
                qs_conv_wa_egresos = qs_conv_wa_egresos.filter(
                    timestamp__time__lte=hora_hasta
                )
            qs_conv_wa_egresos = qs_conv_wa_egresos.select_related(
                'campana',
                'agent',
                'agent__user',
                'agent__grupo',
                'client',
                'conversation_disposition',
                'conversation_disposition__opcion_calificacion',
            )
            qs_conv_wa_egresos = anotar_frt_y_duracion(qs_conv_wa_egresos).order_by(
                '-timestamp'
            )
            page_conv_wa_egresos = 1
            try:
                page_conv_wa_egresos = int(
                    self.request.POST.get('page_listado_conv_respondidas_wa_egresos')
                    or self.request.GET.get('page_listado_conv_respondidas_wa_egresos', 1)
                )
            except (TypeError, ValueError):
                pass
            paginator_conv_wa_egresos = Paginator(qs_conv_wa_egresos, 50)
            listado_conv_respondidas_wa_egresos = paginator_conv_wa_egresos.get_page(
                page_conv_wa_egresos
            )
            num_pages_conv_wa_egresos = (
                listado_conv_respondidas_wa_egresos.paginator.num_pages
            )
            page_no_conv_wa_egresos = listado_conv_respondidas_wa_egresos.number
            if num_pages_conv_wa_egresos <= 7 or page_no_conv_wa_egresos <= 4:
                listado_pages_conv_respondidas_wa_egresos = list(
                    range(1, min(num_pages_conv_wa_egresos + 1, 8))
                )
            elif page_no_conv_wa_egresos > num_pages_conv_wa_egresos - 4:
                listado_pages_conv_respondidas_wa_egresos = list(
                    range(
                        max(1, num_pages_conv_wa_egresos - 6),
                        num_pages_conv_wa_egresos + 1,
                    )
                )
            else:
                listado_pages_conv_respondidas_wa_egresos = list(
                    range(page_no_conv_wa_egresos - 3, page_no_conv_wa_egresos + 4)
                )

        # WhatsApp Egresos: listado Conversaciones No Respondidas (salientes)
        listado_conv_no_respondidas_wa_egresos = None
        listado_pages_conv_no_respondidas_wa_egresos = []
        if desde is not None and hasta is not None:
            qs_conv_no_wa_egresos = ConversacionWhatsapp.objects.conversaciones_salientes_no_atendidas(
                desde, hasta
            )
            if allowed_campaigns is not None:
                qs_conv_no_wa_egresos = qs_conv_no_wa_egresos.filter(
                    Q(campana_id__in=allowed_campaigns) | Q(campana_id__isnull=True)
                )
            if allowed_agent_ids is not None:
                qs_conv_no_wa_egresos = qs_conv_no_wa_egresos.filter(
                    agent_id__in=allowed_agent_ids
                )
            if contacto_id is not None:
                qs_conv_no_wa_egresos = qs_conv_no_wa_egresos.filter(
                    client_id=contacto_id
                )
            if address_query:
                qs_conv_no_wa_egresos = qs_conv_no_wa_egresos.filter(
                    destination__icontains=address_query
                )
            if hora_desde is not None:
                qs_conv_no_wa_egresos = qs_conv_no_wa_egresos.filter(
                    timestamp__time__gte=hora_desde
                )
            if hora_hasta is not None:
                qs_conv_no_wa_egresos = qs_conv_no_wa_egresos.filter(
                    timestamp__time__lte=hora_hasta
                )
            qs_conv_no_wa_egresos = qs_conv_no_wa_egresos.select_related(
                'campana',
                'agent',
                'agent__user',
                'agent__grupo',
                'client',
                'conversation_disposition',
                'conversation_disposition__opcion_calificacion',
            )
            qs_conv_no_wa_egresos = anotar_frt_y_duracion(qs_conv_no_wa_egresos).order_by(
                '-timestamp'
            )
            page_conv_no_wa_egresos = 1
            try:
                page_conv_no_wa_egresos = int(
                    self.request.POST.get('page_listado_conv_no_respondidas_wa_egresos')
                    or self.request.GET.get('page_listado_conv_no_respondidas_wa_egresos', 1)
                )
            except (TypeError, ValueError):
                pass
            paginator_conv_no_wa_egresos = Paginator(qs_conv_no_wa_egresos, 50)
            listado_conv_no_respondidas_wa_egresos = paginator_conv_no_wa_egresos.get_page(
                page_conv_no_wa_egresos
            )
            num_pages_conv_no_wa_egresos = (
                listado_conv_no_respondidas_wa_egresos.paginator.num_pages
            )
            page_no_conv_no_wa_egresos = listado_conv_no_respondidas_wa_egresos.number
            if num_pages_conv_no_wa_egresos <= 7 or page_no_conv_no_wa_egresos <= 4:
                listado_pages_conv_no_respondidas_wa_egresos = list(
                    range(1, min(num_pages_conv_no_wa_egresos + 1, 8))
                )
            elif page_no_conv_no_wa_egresos > num_pages_conv_no_wa_egresos - 4:
                listado_pages_conv_no_respondidas_wa_egresos = list(
                    range(
                        max(1, num_pages_conv_no_wa_egresos - 6),
                        num_pages_conv_no_wa_egresos + 1,
                    )
                )
            else:
                listado_pages_conv_no_respondidas_wa_egresos = list(
                    range(
                        page_no_conv_no_wa_egresos - 3,
                        page_no_conv_no_wa_egresos + 4,
                    )
                )

        # WhatsApp Vista A (Campañas): mensajes por campaña
        whatsapp_mensajes_por_campana = obtener_whatsapp_mensajes_por_campana(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
        )

        # WhatsApp Egresos: mensajes por campaña (salientes)
        whatsapp_egresos_mensajes_por_campana = obtener_whatsapp_egresos_mensajes_por_campana(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
        )

        # WhatsApp Egresos: mensajes por hora (salientes, sin discriminar por campaña)
        whatsapp_egresos_mensajes_por_hora, whatsapp_egresos_mensajes_por_hora_totals = (
            obtener_whatsapp_egresos_mensajes_por_hora(
                start_date=desde,
                end_date=hasta,
                allowed_campaigns=allowed_campaigns,
                allowed_agent_ids=allowed_agent_ids,
                address_query=address_query,
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
            )
        )

        # WhatsApp Egresos: mensajes por día (salientes, sin discriminar por campaña)
        whatsapp_egresos_mensajes_por_dia, whatsapp_egresos_mensajes_por_dia_totals = (
            obtener_whatsapp_egresos_mensajes_por_dia(
                start_date=desde,
                end_date=hasta,
                allowed_campaigns=allowed_campaigns,
                allowed_agent_ids=allowed_agent_ids,
                address_query=address_query,
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
            )
        )

        # WhatsApp Egresos: mensajes por mes (salientes, sin discriminar por campaña)
        whatsapp_egresos_mensajes_por_mes, whatsapp_egresos_mensajes_por_mes_totals = (
            obtener_whatsapp_egresos_mensajes_por_mes(
                start_date=desde,
                end_date=hasta,
                allowed_campaigns=allowed_campaigns,
                allowed_agent_ids=allowed_agent_ids,
                address_query=address_query,
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
            )
        )

        # WhatsApp Horas: mensajes por hora de día
        whatsapp_mensajes_por_hora, whatsapp_mensajes_por_hora_totals = (
            obtener_whatsapp_mensajes_por_hora(
                start_date=desde,
                end_date=hasta,
                allowed_campaigns=allowed_campaigns,
                allowed_agent_ids=allowed_agent_ids,
                address_query=address_query,
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
            )
        )

        # WhatsApp Días: mensajes por día (sin discriminar por campaña)
        whatsapp_mensajes_por_dia, whatsapp_mensajes_por_dia_totals = (
            obtener_whatsapp_mensajes_por_dia(
                start_date=desde,
                end_date=hasta,
                allowed_campaigns=allowed_campaigns,
                allowed_agent_ids=allowed_agent_ids,
                address_query=address_query,
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
            )
        )

        # WhatsApp Mes: mensajes por mes (sin discriminar por campaña)
        whatsapp_mensajes_por_mes, whatsapp_mensajes_por_mes_totals = (
            obtener_whatsapp_mensajes_por_mes(
                start_date=desde,
                end_date=hasta,
                allowed_campaigns=allowed_campaigns,
                allowed_agent_ids=allowed_agent_ids,
                address_query=address_query,
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
            )
        )

        # Egresos (OUTBOUND): misma estructura que Ingresos
        egresos_canalidades_por_campana, egresos_canalidades_por_campana_totals = (
            obtener_canalidades_por_campana(
                start_date=desde,
                end_date=hasta,
                allowed_campaigns=allowed_campaigns,
                allowed_agent_ids=allowed_agent_ids,
                customer_id=contacto_id,
                address_query=address_query,
                direction_filter='OUTBOUND',
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
                duracion_agente_min=duracion_agente_min,
            )
        )
        egresos_llamadas_por_campana = obtener_llamadas_salientes_por_campana(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        egresos_llamadas_por_campana_totals = None
        if egresos_llamadas_por_campana:
            total_sent = sum(r['sent'] for r in egresos_llamadas_por_campana)
            total_conectadas = sum(r['conectadas'] for r in egresos_llamadas_por_campana)
            total_canceladas = sum(r['canceladas'] for r in egresos_llamadas_por_campana)
            total_no_atiende = sum(r['no_atiende'] for r in egresos_llamadas_por_campana)
            total_ocupado = sum(r['ocupado'] for r in egresos_llamadas_por_campana)
            total_contestador = sum(r['contestador'] for r in egresos_llamadas_por_campana)
            total_shortcall = sum(r['shortcall'] for r in egresos_llamadas_por_campana)
            total_congestion = sum(r['congestion'] for r in egresos_llamadas_por_campana)
            total_otro_error = sum(r['otro_error'] for r in egresos_llamadas_por_campana)
            total_transferred = sum(r['transferred'] for r in egresos_llamadas_por_campana)
            egresos_llamadas_por_campana_totals = {
                'sent': total_sent,
                'conectadas': total_conectadas,
                'canceladas': total_canceladas,
                'no_atiende': total_no_atiende,
                'ocupado': total_ocupado,
                'contestador': total_contestador,
                'shortcall': total_shortcall,
                'congestion': total_congestion,
                'otro_error': total_otro_error,
                'transferred': total_transferred,
                'pct_conectadas': round(100.0 * total_conectadas / total_sent, 2) if total_sent else 0.0,
                'pct_no_conectadas': round(100.0 * (total_sent - total_conectadas) / total_sent, 2) if total_sent else 0.0,
            }
        egresos_llamadas_por_hora = obtener_llamadas_salientes_por_hora(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        if egresos_llamadas_por_hora and hora_desde is not None and hora_hasta is not None:
            hour_begin = hora_desde.hour
            hour_end = hora_hasta.hour
            if hour_begin <= hour_end:
                egresos_llamadas_por_hora = [
                    r for r in egresos_llamadas_por_hora if hour_begin <= r['hour'] <= hour_end
                ]
            else:
                egresos_llamadas_por_hora = [
                    r for r in egresos_llamadas_por_hora
                    if r['hour'] >= hour_begin or r['hour'] <= hour_end
                ]
                egresos_llamadas_por_hora.sort(
                    key=lambda r: (r['hour'] + 24) if r['hour'] < hour_begin else r['hour']
                )
        egresos_llamadas_por_hora_totals = None
        if egresos_llamadas_por_hora:
            total_sent = sum(r['sent'] for r in egresos_llamadas_por_hora)
            total_conectadas = sum(r['conectadas'] for r in egresos_llamadas_por_hora)
            total_canceladas = sum(r['canceladas'] for r in egresos_llamadas_por_hora)
            total_no_atiende = sum(r['no_atiende'] for r in egresos_llamadas_por_hora)
            total_ocupado = sum(r['ocupado'] for r in egresos_llamadas_por_hora)
            total_contestador = sum(r['contestador'] for r in egresos_llamadas_por_hora)
            total_shortcall = sum(r['shortcall'] for r in egresos_llamadas_por_hora)
            total_congestion = sum(r['congestion'] for r in egresos_llamadas_por_hora)
            total_otro_error = sum(r['otro_error'] for r in egresos_llamadas_por_hora)
            total_transferred = sum(r['transferred'] for r in egresos_llamadas_por_hora)
            egresos_llamadas_por_hora_totals = {
                'sent': total_sent,
                'conectadas': total_conectadas,
                'canceladas': total_canceladas,
                'no_atiende': total_no_atiende,
                'ocupado': total_ocupado,
                'contestador': total_contestador,
                'shortcall': total_shortcall,
                'congestion': total_congestion,
                'otro_error': total_otro_error,
                'transferred': total_transferred,
                'pct_conectadas': round(100.0 * total_conectadas / total_sent, 2) if total_sent else 0.0,
                'pct_no_conectadas': round(100.0 * (total_sent - total_conectadas) / total_sent, 2) if total_sent else 0.0,
            }
        egresos_llamadas_por_dia = obtener_llamadas_salientes_por_dia(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        egresos_llamadas_por_dia_totals = None
        if egresos_llamadas_por_dia:
            total_sent = sum(r['sent'] for r in egresos_llamadas_por_dia)
            total_conectadas = sum(r['conectadas'] for r in egresos_llamadas_por_dia)
            total_canceladas = sum(r['canceladas'] for r in egresos_llamadas_por_dia)
            total_no_atiende = sum(r['no_atiende'] for r in egresos_llamadas_por_dia)
            total_ocupado = sum(r['ocupado'] for r in egresos_llamadas_por_dia)
            total_contestador = sum(r['contestador'] for r in egresos_llamadas_por_dia)
            total_shortcall = sum(r['shortcall'] for r in egresos_llamadas_por_dia)
            total_congestion = sum(r['congestion'] for r in egresos_llamadas_por_dia)
            total_otro_error = sum(r['otro_error'] for r in egresos_llamadas_por_dia)
            total_transferred = sum(r['transferred'] for r in egresos_llamadas_por_dia)
            egresos_llamadas_por_dia_totals = {
                'sent': total_sent,
                'conectadas': total_conectadas,
                'canceladas': total_canceladas,
                'no_atiende': total_no_atiende,
                'ocupado': total_ocupado,
                'contestador': total_contestador,
                'shortcall': total_shortcall,
                'congestion': total_congestion,
                'otro_error': total_otro_error,
                'transferred': total_transferred,
                'pct_conectadas': round(100.0 * total_conectadas / total_sent, 2) if total_sent else 0.0,
                'pct_no_conectadas': round(100.0 * (total_sent - total_conectadas) / total_sent, 2) if total_sent else 0.0,
            }
        egresos_llamadas_por_mes = obtener_llamadas_salientes_por_mes(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        egresos_llamadas_por_mes_totals = None
        if egresos_llamadas_por_mes:
            total_sent = sum(r['sent'] for r in egresos_llamadas_por_mes)
            total_conectadas = sum(r['conectadas'] for r in egresos_llamadas_por_mes)
            total_canceladas = sum(r['canceladas'] for r in egresos_llamadas_por_mes)
            total_no_atiende = sum(r['no_atiende'] for r in egresos_llamadas_por_mes)
            total_ocupado = sum(r['ocupado'] for r in egresos_llamadas_por_mes)
            total_contestador = sum(r['contestador'] for r in egresos_llamadas_por_mes)
            total_shortcall = sum(r['shortcall'] for r in egresos_llamadas_por_mes)
            total_congestion = sum(r['congestion'] for r in egresos_llamadas_por_mes)
            total_otro_error = sum(r['otro_error'] for r in egresos_llamadas_por_mes)
            total_transferred = sum(r['transferred'] for r in egresos_llamadas_por_mes)
            egresos_llamadas_por_mes_totals = {
                'sent': total_sent,
                'conectadas': total_conectadas,
                'canceladas': total_canceladas,
                'no_atiende': total_no_atiende,
                'ocupado': total_ocupado,
                'contestador': total_contestador,
                'shortcall': total_shortcall,
                'congestion': total_congestion,
                'otro_error': total_otro_error,
                'transferred': total_transferred,
                'pct_conectadas': round(100.0 * total_conectadas / total_sent, 2) if total_sent else 0.0,
                'pct_no_conectadas': round(100.0 * (total_sent - total_conectadas) / total_sent, 2) if total_sent else 0.0,
            }
        # Egresos Canalidades (Horas, Días, Mes): formato genérico received/answered para el panel Canalidades
        egresos_canalidades_llamadas_por_hora = obtener_llamadas_por_hora(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='OUTBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        egresos_canalidades_llamadas_por_hora_totals = None
        if egresos_canalidades_llamadas_por_hora:
            total_received = sum(r['received'] for r in egresos_canalidades_llamadas_por_hora)
            total_answered = sum(r['answered'] for r in egresos_canalidades_llamadas_por_hora)
            total_unanswered = sum(r['unanswered'] for r in egresos_canalidades_llamadas_por_hora)
            total_abandoned = sum(r['abandoned'] for r in egresos_canalidades_llamadas_por_hora)
            total_transferred = sum(r['transferred'] for r in egresos_canalidades_llamadas_por_hora)
            egresos_canalidades_llamadas_por_hora_totals = {
                'received': total_received,
                'answered': total_answered,
                'unanswered': total_unanswered,
                'abandoned': total_abandoned,
                'transferred': total_transferred,
                'pct_answered': round(100.0 * total_answered / total_received, 2) if total_received else 0.0,
                'pct_unanswered': round(100.0 * total_unanswered / total_received, 2) if total_received else 0.0,
                'pct_abandoned': round(100.0 * total_abandoned / total_received, 2) if total_received else 0.0,
                'pct_transferred': round(100.0 * total_transferred / total_received, 2) if total_received else 0.0,
            }
        egresos_canalidades_por_hora, egresos_canalidades_por_hora_totals = obtener_canalidades_por_hora(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='OUTBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        egresos_canalidades_por_dia, egresos_canalidades_por_dia_totals = obtener_canalidades_por_dia(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='OUTBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        egresos_canalidades_llamadas_por_dia = obtener_llamadas_por_dia(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='OUTBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        egresos_canalidades_llamadas_por_dia_totals = None
        if egresos_canalidades_llamadas_por_dia:
            total_received = sum(r['received'] for r in egresos_canalidades_llamadas_por_dia)
            total_answered = sum(r['answered'] for r in egresos_canalidades_llamadas_por_dia)
            total_unanswered = sum(r['unanswered'] for r in egresos_canalidades_llamadas_por_dia)
            total_abandoned = sum(r['abandoned'] for r in egresos_canalidades_llamadas_por_dia)
            total_transferred = sum(r['transferred'] for r in egresos_canalidades_llamadas_por_dia)
            egresos_canalidades_llamadas_por_dia_totals = {
                'received': total_received,
                'answered': total_answered,
                'unanswered': total_unanswered,
                'abandoned': total_abandoned,
                'transferred': total_transferred,
                'pct_answered': round(100.0 * total_answered / total_received, 2) if total_received else 0.0,
                'pct_unanswered': round(100.0 * total_unanswered / total_received, 2) if total_received else 0.0,
                'pct_abandoned': round(100.0 * total_abandoned / total_received, 2) if total_received else 0.0,
                'pct_transferred': round(100.0 * total_transferred / total_received, 2) if total_received else 0.0,
            }
        egresos_canalidades_por_mes, egresos_canalidades_por_mes_totals = (
            obtener_canalidades_por_mes(
                start_date=desde,
                end_date=hasta,
                allowed_campaigns=allowed_campaigns,
                allowed_agent_ids=allowed_agent_ids,
                customer_id=contacto_id,
                address_query=address_query,
                direction_filter='OUTBOUND',
                hora_desde=hora_desde,
                hora_hasta=hora_hasta,
                duracion_agente_min=duracion_agente_min,
            )
        )
        egresos_canalidades_llamadas_por_mes = obtener_llamadas_por_mes(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='OUTBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
        )
        egresos_canalidades_llamadas_por_mes_totals = None
        if egresos_canalidades_llamadas_por_mes:
            total_received = sum(r['received'] for r in egresos_canalidades_llamadas_por_mes)
            total_answered = sum(r['answered'] for r in egresos_canalidades_llamadas_por_mes)
            total_unanswered = sum(r['unanswered'] for r in egresos_canalidades_llamadas_por_mes)
            total_abandoned = sum(r['abandoned'] for r in egresos_canalidades_llamadas_por_mes)
            total_transferred = sum(r['transferred'] for r in egresos_canalidades_llamadas_por_mes)
            egresos_canalidades_llamadas_por_mes_totals = {
                'received': total_received,
                'answered': total_answered,
                'unanswered': total_unanswered,
                'abandoned': total_abandoned,
                'transferred': total_transferred,
                'pct_answered': round(100.0 * total_answered / total_received, 2) if total_received else 0.0,
                'pct_unanswered': round(100.0 * total_unanswered / total_received, 2) if total_received else 0.0,
                'pct_abandoned': round(100.0 * total_abandoned / total_received, 2) if total_received else 0.0,
                'pct_transferred': round(100.0 * total_transferred / total_received, 2) if total_received else 0.0,
            }
        page_listado_egresos = 1
        try:
            page_listado_egresos = int(
                self.request.POST.get('page_listado_egresos') or
                self.request.GET.get('page_listado_egresos', 1)
            )
        except (TypeError, ValueError):
            pass
        listado_egresos_atendidas = obtener_listado_llamadas_atendidas(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='OUTBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
            page=page_listado_egresos,
            page_size=100,
        )
        num_pages_eg = listado_egresos_atendidas.paginator.num_pages
        page_no_eg = listado_egresos_atendidas.number
        if num_pages_eg <= 7 or page_no_eg <= 4:
            listado_pages_egresos = list(range(1, min(num_pages_eg + 1, 8)))
        elif page_no_eg > num_pages_eg - 4:
            listado_pages_egresos = list(range(max(1, num_pages_eg - 6), num_pages_eg + 1))
        else:
            listado_pages_egresos = list(range(page_no_eg - 3, page_no_eg + 4))
        page_listado_no_atendidas_egresos = 1
        try:
            page_listado_no_atendidas_egresos = int(
                self.request.POST.get('page_listado_no_atendidas_egresos') or
                self.request.GET.get('page_listado_no_atendidas_egresos', 1)
            )
        except (TypeError, ValueError):
            pass
        listado_egresos_no_atendidas = obtener_listado_llamadas_no_atendidas(
            start_date=desde,
            end_date=hasta,
            allowed_campaigns=allowed_campaigns,
            allowed_agent_ids=allowed_agent_ids,
            customer_id=contacto_id,
            address_query=address_query,
            direction_filter='OUTBOUND',
            hora_desde=hora_desde,
            hora_hasta=hora_hasta,
            duracion_agente_min=duracion_agente_min,
            duracion_bot_min=duracion_bot_min,
            page=page_listado_no_atendidas_egresos,
            page_size=100,
        )
        num_pages_na_eg = listado_egresos_no_atendidas.paginator.num_pages
        page_no_na_eg = listado_egresos_no_atendidas.number
        if num_pages_na_eg <= 7 or page_no_na_eg <= 4:
            listado_pages_no_atendidas_egresos = list(
                range(1, min(num_pages_na_eg + 1, 8))
            )
        elif page_no_na_eg > num_pages_na_eg - 4:
            listado_pages_no_atendidas_egresos = list(
                range(max(1, num_pages_na_eg - 6), num_pages_na_eg + 1)
            )
        else:
            listado_pages_no_atendidas_egresos = list(
                range(page_no_na_eg - 3, page_no_na_eg + 4)
            )

        base_url = (self.request.build_absolute_uri('/') or '').rstrip('/')
        return self.render_to_response(self.get_context_data(
            form=form,
            kpis=kpis,
            desde=desde,
            hasta=hasta,
            campana_nombre=campana_nombre,
            grupo_nombre=grupo_nombre,
            agente_nombre=agente_nombre,
            contacto_id=contacto_id,
            address_nombre=address_nombre,
            llamadas_por_campana=llamadas_por_campana,
            llamadas_por_campana_totals=llamadas_por_campana_totals,
            ingresos_voz_por_campana=ingresos_voz_por_campana,
            ingresos_voz_por_campana_totals=ingresos_voz_por_campana_totals,
            canalidades_por_campana=canalidades_por_campana,
            canalidades_por_campana_totals=canalidades_por_campana_totals,
            canalidades_por_hora=canalidades_por_hora,
            canalidades_por_hora_totals=canalidades_por_hora_totals,
            canalidades_por_dia=canalidades_por_dia,
            canalidades_por_dia_totals=canalidades_por_dia_totals,
            canalidades_por_mes=canalidades_por_mes,
            canalidades_por_mes_totals=canalidades_por_mes_totals,
            llamadas_por_hora=llamadas_por_hora,
            llamadas_por_hora_totals=llamadas_por_hora_totals,
            llamadas_por_dia=llamadas_por_dia,
            llamadas_por_dia_totals=llamadas_por_dia_totals,
            llamadas_por_mes=llamadas_por_mes,
            llamadas_por_mes_totals=llamadas_por_mes_totals,
            listado_llamadas_atendidas=listado_llamadas_atendidas,
            listado_pages=listado_pages,
            listado_llamadas_no_atendidas=listado_llamadas_no_atendidas,
            listado_pages_no_atendidas=listado_pages_no_atendidas,
            egresos_canalidades_por_campana=egresos_canalidades_por_campana,
            egresos_canalidades_por_campana_totals=egresos_canalidades_por_campana_totals,
            egresos_llamadas_por_campana=egresos_llamadas_por_campana,
            egresos_llamadas_por_campana_totals=egresos_llamadas_por_campana_totals,
            egresos_llamadas_por_hora=egresos_llamadas_por_hora,
            egresos_llamadas_por_hora_totals=egresos_llamadas_por_hora_totals,
            egresos_llamadas_por_dia=egresos_llamadas_por_dia,
            egresos_llamadas_por_dia_totals=egresos_llamadas_por_dia_totals,
            egresos_llamadas_por_mes=egresos_llamadas_por_mes,
            egresos_llamadas_por_mes_totals=egresos_llamadas_por_mes_totals,
            egresos_canalidades_llamadas_por_hora=egresos_canalidades_llamadas_por_hora,
            egresos_canalidades_llamadas_por_hora_totals=egresos_canalidades_llamadas_por_hora_totals,
            egresos_canalidades_por_hora=egresos_canalidades_por_hora,
            egresos_canalidades_por_hora_totals=egresos_canalidades_por_hora_totals,
            egresos_canalidades_por_dia=egresos_canalidades_por_dia,
            egresos_canalidades_por_dia_totals=egresos_canalidades_por_dia_totals,
            egresos_canalidades_llamadas_por_dia=egresos_canalidades_llamadas_por_dia,
            egresos_canalidades_llamadas_por_dia_totals=egresos_canalidades_llamadas_por_dia_totals,
            egresos_canalidades_por_mes=egresos_canalidades_por_mes,
            egresos_canalidades_por_mes_totals=egresos_canalidades_por_mes_totals,
            egresos_canalidades_llamadas_por_mes=egresos_canalidades_llamadas_por_mes,
            egresos_canalidades_llamadas_por_mes_totals=egresos_canalidades_llamadas_por_mes_totals,
            listado_egresos_atendidas=listado_egresos_atendidas,
            listado_pages_egresos=listado_pages_egresos,
            listado_egresos_no_atendidas=listado_egresos_no_atendidas,
            listado_pages_no_atendidas_egresos=listado_pages_no_atendidas_egresos,
            whatsapp_frt_kpis=whatsapp_frt_kpis,
            listado_whatsapp_frt=listado_whatsapp_frt,
            listado_pages_whatsapp_frt=listado_pages_whatsapp_frt,
            kpis_whatsapp_resumen=kpis_whatsapp_resumen,
            listado_conv_respondidas_wa=listado_conv_respondidas_wa,
            listado_pages_conv_respondidas_wa=listado_pages_conv_respondidas_wa,
            listado_conv_no_respondidas_wa=listado_conv_no_respondidas_wa,
            listado_pages_conv_no_respondidas_wa=listado_pages_conv_no_respondidas_wa,
            listado_conv_respondidas_wa_egresos=listado_conv_respondidas_wa_egresos,
            listado_pages_conv_respondidas_wa_egresos=listado_pages_conv_respondidas_wa_egresos,
            listado_conv_no_respondidas_wa_egresos=listado_conv_no_respondidas_wa_egresos,
            listado_pages_conv_no_respondidas_wa_egresos=listado_pages_conv_no_respondidas_wa_egresos,
            whatsapp_mensajes_por_campana=whatsapp_mensajes_por_campana,
            whatsapp_egresos_mensajes_por_campana=whatsapp_egresos_mensajes_por_campana,
            whatsapp_egresos_mensajes_por_hora=whatsapp_egresos_mensajes_por_hora,
            whatsapp_egresos_mensajes_por_hora_totals=whatsapp_egresos_mensajes_por_hora_totals,
            whatsapp_egresos_mensajes_por_dia=whatsapp_egresos_mensajes_por_dia,
            whatsapp_egresos_mensajes_por_dia_totals=whatsapp_egresos_mensajes_por_dia_totals,
            whatsapp_egresos_mensajes_por_mes=whatsapp_egresos_mensajes_por_mes,
            whatsapp_egresos_mensajes_por_mes_totals=whatsapp_egresos_mensajes_por_mes_totals,
            whatsapp_mensajes_por_hora=whatsapp_mensajes_por_hora,
            whatsapp_mensajes_por_hora_totals=whatsapp_mensajes_por_hora_totals,
            whatsapp_mensajes_por_dia=whatsapp_mensajes_por_dia,
            whatsapp_mensajes_por_dia_totals=whatsapp_mensajes_por_dia_totals,
            whatsapp_mensajes_por_mes=whatsapp_mensajes_por_mes,
            whatsapp_mensajes_por_mes_totals=whatsapp_mensajes_por_mes_totals,
            base_url=base_url,
        ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('llamadas_por_campana', [])
        context.setdefault('llamadas_por_campana_totals', None)
        context.setdefault('ingresos_voz_por_campana', [])
        context.setdefault('ingresos_voz_por_campana_totals', None)
        context.setdefault('canalidades_por_campana', [])
        context.setdefault('canalidades_por_campana_totals', None)
        context.setdefault('canalidades_por_hora', [])
        context.setdefault('canalidades_por_hora_totals', None)
        context.setdefault('canalidades_por_dia', [])
        context.setdefault('canalidades_por_dia_totals', None)
        context.setdefault('canalidades_por_mes', [])
        context.setdefault('canalidades_por_mes_totals', None)
        context.setdefault('llamadas_por_hora', [])
        context.setdefault('llamadas_por_hora_totals', None)
        context.setdefault('llamadas_por_dia', [])
        context.setdefault('llamadas_por_dia_totals', None)
        context.setdefault('llamadas_por_mes', [])
        context.setdefault('llamadas_por_mes_totals', None)
        context.setdefault('listado_llamadas_atendidas', None)
        context.setdefault('listado_pages', [])
        context.setdefault('listado_llamadas_no_atendidas', None)
        context.setdefault('listado_pages_no_atendidas', [])
        context.setdefault('egresos_canalidades_por_campana', [])
        context.setdefault('egresos_canalidades_por_campana_totals', None)
        context.setdefault('egresos_canalidades_por_hora', [])
        context.setdefault('egresos_canalidades_por_hora_totals', None)
        context.setdefault('egresos_canalidades_por_dia', [])
        context.setdefault('egresos_canalidades_por_dia_totals', None)
        context.setdefault('egresos_canalidades_por_mes', [])
        context.setdefault('egresos_canalidades_por_mes_totals', None)
        context.setdefault('egresos_llamadas_por_campana', [])
        context.setdefault('egresos_llamadas_por_campana_totals', None)
        context.setdefault('egresos_llamadas_por_hora', [])
        context.setdefault('egresos_llamadas_por_hora_totals', None)
        context.setdefault('egresos_llamadas_por_dia', [])
        context.setdefault('egresos_llamadas_por_dia_totals', None)
        context.setdefault('egresos_llamadas_por_mes', [])
        context.setdefault('egresos_llamadas_por_mes_totals', None)
        context.setdefault('listado_egresos_atendidas', None)
        context.setdefault('listado_pages_egresos', [])
        context.setdefault('listado_egresos_no_atendidas', None)
        context.setdefault('listado_pages_no_atendidas_egresos', [])
        context.setdefault('whatsapp_frt_kpis', None)
        context.setdefault('listado_whatsapp_frt', None)
        context.setdefault('listado_pages_whatsapp_frt', [])
        context.setdefault('kpis_whatsapp_resumen', None)
        context.setdefault('listado_conv_respondidas_wa', None)
        context.setdefault('listado_pages_conv_respondidas_wa', [])
        context.setdefault('listado_conv_no_respondidas_wa', None)
        context.setdefault('listado_pages_conv_no_respondidas_wa', [])
        context.setdefault('listado_conv_respondidas_wa_egresos', None)
        context.setdefault('listado_pages_conv_respondidas_wa_egresos', [])
        context.setdefault('listado_conv_no_respondidas_wa_egresos', None)
        context.setdefault('listado_pages_conv_no_respondidas_wa_egresos', [])
        context.setdefault('whatsapp_mensajes_por_campana', [])
        context.setdefault('whatsapp_egresos_mensajes_por_campana', [])
        context.setdefault('whatsapp_egresos_mensajes_por_hora', [])
        context.setdefault('whatsapp_egresos_mensajes_por_hora_totals', None)
        context.setdefault('whatsapp_egresos_mensajes_por_dia', [])
        context.setdefault('whatsapp_egresos_mensajes_por_dia_totals', None)
        context.setdefault('whatsapp_egresos_mensajes_por_mes', [])
        context.setdefault('whatsapp_egresos_mensajes_por_mes_totals', None)
        context.setdefault('whatsapp_mensajes_por_hora', [])
        context.setdefault('whatsapp_mensajes_por_hora_totals', None)
        context.setdefault('whatsapp_mensajes_por_dia', [])
        context.setdefault('whatsapp_mensajes_por_dia_totals', None)
        context.setdefault('whatsapp_mensajes_por_mes', [])
        context.setdefault('whatsapp_mensajes_por_mes_totals', None)
        context.setdefault('base_url', (self.request.build_absolute_uri('/') or '').rstrip('/'))
        try:
            context.setdefault(
                'api_omnichannel_share_url',
                self.request.build_absolute_uri(reverse('api_reporte_omnichannel_share')),
            )
        except Exception:
            context.setdefault('api_omnichannel_share_url', '')
        context.update(kwargs)
        return context


class ReporteCentroContactoAPIView(APIView):
    """
    GET /api/reporte/centro_de_contacto/
    Parámetros: campaign_id (opcional), start_date, end_date (opcionales).
    Sin campaign_id: métricas globales (todas las campañas o solo las permitidas al usuario).
    Devuelve KPIs de rendimiento desde interactions_summary.
    """
    renderer_classes = (JSONRenderer,)
    http_method_names = ['get']

    def get(self, request):
        from django.utils.dateparse import parse_datetime

        campaign_id_param = request.query_params.get('campaign_id')
        if campaign_id_param is not None and campaign_id_param != '':
            try:
                campaign_id = int(campaign_id_param)
            except (TypeError, ValueError):
                return Response(
                    {'error': 'campaign_id debe ser un entero'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            campaign_id = None

        start_date_raw = request.query_params.get('start_date')
        end_date_raw = request.query_params.get('end_date')
        start_date = parse_datetime(start_date_raw) if start_date_raw else None
        end_date = parse_datetime(end_date_raw) if end_date_raw else None

        allowed_campaigns = None
        if campaign_id is None:
            if request.user.get_is_administrador():
                allowed_campaigns = None
            else:
                supervisor = request.user.get_supervisor_profile()
                campanas = supervisor.campanas_asignadas_actuales()
                allowed_campaigns = list(campanas.values_list('pk', flat=True))

        payload = obtener_kpis_centro_contacto(
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date,
            allowed_campaigns=allowed_campaigns,
        )
        serializer = CentroContactoKPISerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class GetOmnichannelShareDataView(APIView):
    """
    GET /api/reporte/omnichannel_share/
    Parámetros opcionales: start_date, end_date (ISO date o datetime).
    Si no se envían, se usa el día actual (hoy).
    Devuelve JSON listo para Chart.js (donut): total_volume, chart_data, shares.
    """
    renderer_classes = (JSONRenderer,)
    http_method_names = ['get']

    def get(self, request):
        from django.utils.dateparse import parse_datetime, parse_date

        start_date_raw = request.query_params.get('start_date')
        end_date_raw = request.query_params.get('end_date')
        start_date = None
        end_date = None
        if start_date_raw:
            start_date = parse_datetime(start_date_raw) or parse_date(start_date_raw)
        if end_date_raw:
            end_date = parse_datetime(end_date_raw) or parse_date(end_date_raw)

        payload = get_omnichannel_share_data(start_date=start_date, end_date=end_date)
        return Response(payload, status=status.HTTP_200_OK)


# --- Export CSV Canalidades por campaña (mismo flujo que reporte_grafico contactados) ---

import threading
from datetime import datetime as dt_datetime

from ominicontacto_app.utiles import convert_fecha_datetime
from reportes_app.services.exportacion_canalidades_centro_contacto import (
    KEY_TASK_TEMPLATE,
    generar_csv_canalidades_centro_contacto,
)
from reportes_app.services.exportacion_canalidades_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CANALIDADES_EGRESOS,
    generar_csv_canalidades_egresos_centro_contacto,
)
from reportes_app.services.exportacion_canalidades_por_hora_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CANALIDADES_POR_HORA,
    generar_csv_canalidades_por_hora_centro_contacto,
)
from reportes_app.services.exportacion_canalidades_por_hora_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CANALIDADES_POR_HORA_EGRESOS,
    generar_csv_canalidades_por_hora_egresos_centro_contacto,
)
from reportes_app.services.exportacion_canalidades_por_dia_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CANALIDADES_POR_DIA,
    generar_csv_canalidades_por_dia_centro_contacto,
)
from reportes_app.services.exportacion_canalidades_por_dia_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CANALIDADES_POR_DIA_EGRESOS,
    generar_csv_canalidades_por_dia_egresos_centro_contacto,
)
from reportes_app.services.exportacion_canalidades_por_mes_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CANALIDADES_POR_MES,
    generar_csv_canalidades_por_mes_centro_contacto,
)
from reportes_app.services.exportacion_canalidades_por_mes_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CANALIDADES_POR_MES_EGRESOS,
    generar_csv_canalidades_por_mes_egresos_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_atendidas_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_ATENDIDAS,
    generar_csv_llamadas_atendidas_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_atendidas_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_ATENDIDAS_EGRESOS,
    generar_csv_llamadas_atendidas_egresos_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_no_atendidas_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_NO_ATENDIDAS,
    generar_csv_llamadas_no_atendidas_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_no_atendidas_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_NO_ATENDIDAS_EGRESOS,
    generar_csv_llamadas_no_atendidas_egresos_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_voz_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_VOZ,
    generar_csv_llamadas_voz_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_voz_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_VOZ_EGRESOS,
    generar_csv_llamadas_voz_egresos_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_por_hora_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_POR_HORA,
    generar_csv_llamadas_por_hora_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_por_hora_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_POR_HORA_EGRESOS,
    generar_csv_llamadas_por_hora_egresos_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_por_dia_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_POR_DIA,
    generar_csv_llamadas_por_dia_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_por_dia_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_POR_DIA_EGRESOS,
    generar_csv_llamadas_por_dia_egresos_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_por_mes_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_POR_MES,
    generar_csv_llamadas_por_mes_centro_contacto,
)
from reportes_app.services.exportacion_llamadas_por_mes_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_LLAMADAS_POR_MES_EGRESOS,
    generar_csv_llamadas_por_mes_egresos_centro_contacto,
)
from reportes_app.services.exportacion_conversaciones_respondidas_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CONV_RESP,
    generar_csv_conversaciones_respondidas_centro_contacto,
)
from reportes_app.services.exportacion_conversaciones_respondidas_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CONV_RESP_EGRESOS,
    generar_csv_conversaciones_respondidas_egresos_centro_contacto,
)
from reportes_app.services.exportacion_conversaciones_no_respondidas_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CONV_NO_RESP,
    generar_csv_conversaciones_no_respondidas_centro_contacto,
)
from reportes_app.services.exportacion_conversaciones_no_respondidas_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_CONV_NO_RESP_EGRESOS,
    generar_csv_conversaciones_no_respondidas_egresos_centro_contacto,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_hora_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_WA_MSG_HORA,
    generar_csv_whatsapp_mensajes_por_hora,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_hora_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_WA_MSG_HORA_EGRESOS,
    generar_csv_whatsapp_mensajes_por_hora_egresos_centro_contacto,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_campana_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_WA_MSG_CAMPANA,
    generar_csv_whatsapp_mensajes_por_campana,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_campana_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_WA_MSG_CAMPANA_EGRESOS,
    generar_csv_whatsapp_mensajes_por_campana_egresos_centro_contacto,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_dia_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_WA_MSG_DIA,
    generar_csv_whatsapp_mensajes_por_dia,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_dia_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_WA_MSG_DIA_EGRESOS,
    generar_csv_whatsapp_mensajes_por_dia_egresos_centro_contacto,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_mes_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_WA_MSG_MES,
    generar_csv_whatsapp_mensajes_por_mes,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_mes_egresos_centro_contacto import (
    KEY_TASK_TEMPLATE as KEY_TASK_TEMPLATE_WA_MSG_MES_EGRESOS,
    generar_csv_whatsapp_mensajes_por_mes_egresos_centro_contacto,
)
from api_app.views.permissions import (
    TienePermisoInteractionTransfersOGrabacionBuscar,
    TienePermisoOML,
)


def _parse_agent_segments(channel_data):
    """Extrae la lista agent_segments de channel_data (interactions_summary)."""
    if not isinstance(channel_data, dict):
        return []
    raw = channel_data.get('agent_segments')
    if not isinstance(raw, list):
        return []
    return [s for s in raw if isinstance(s, dict)]


def _parse_iso_datetime_for_segment(value):
    """Parsea start_ts/end_ts de segmentos (ISO con o sin zona)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        s_norm = s.replace('Z', '+00:00')
        return datetime.fromisoformat(s_norm)
    except ValueError:
        pass
    from django.utils.dateparse import parse_datetime
    return parse_datetime(s)


def _segment_start_ts_sort_tuple(seg):
    """
    Tupla comparable para ordenar segmentos por start_ts sin mezclar naive/aware
    (evita TypeError en sort entre datetimes con y sin tzinfo).
    """
    if not isinstance(seg, dict):
        return (2, 0.0, 0)
    dt = _parse_iso_datetime_for_segment(seg.get('start_ts'))
    if dt is None:
        return (1, 0.0, 0)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    # timestamp() es comparable entre instancias aware
    return (0, dt.timestamp(), 0)


def _ordered_segments_for_agent(segments, agent_id):
    """
    Segmentos cuyo agent_id coincide con agent_id, ordenados por start_ts;
    sin parse válido conservan el orden relativo original (índice en lista).
    """
    if agent_id is None:
        return []
    matching_indexed = []
    for idx, seg in enumerate(segments):
        aid = seg.get('agent_id')
        if aid is None:
            continue
        try:
            if int(aid) != int(agent_id):
                continue
        except (TypeError, ValueError):
            continue
        matching_indexed.append((idx, seg))

    def sort_key(item):
        list_idx, seg = item
        kind, ts, _ = _segment_start_ts_sort_tuple(seg)
        if kind == 0:
            return (0, ts, list_idx)
        if kind == 1:
            return (1, list_idx, list_idx)
        return (2, list_idx, list_idx)

    matching_indexed.sort(key=sort_key)
    return [seg for _, seg in matching_indexed]


def _ordered_segments_chronologically(segments):
    """
    Todos los agent_segments ordenados por start_ts (misma clave de orden que
    _ordered_segments_for_agent). Sirve para alinear la fila i de transferencias
    con el segmento i cuando no hay destination_agent_id (p. ej. CAMPAIGN).
    """
    indexed = list(enumerate(segments))

    def sort_key(item):
        list_idx, seg = item
        kind, ts, _ = _segment_start_ts_sort_tuple(seg)
        if kind == 0:
            return (0, ts, list_idx)
        if kind == 1:
            return (1, list_idx, list_idx)
        return (2, list_idx, list_idx)

    indexed.sort(key=sort_key)
    return [seg for _, seg in indexed if isinstance(seg, dict)]


def _talk_duration_seconds_from_segment(seg):
    """Extrae talk_duration de un dict de segmento como float o None."""
    if not isinstance(seg, dict):
        return None
    raw = seg.get('talk_duration')
    if raw is None:
        return None
    try:
        sec = float(raw)
    except (TypeError, ValueError):
        return None
    if sec < 0:
        return None
    return sec


def _segment_duration_seconds_for_transfer(transfer, transfers_ordered, segments):
    """
    talk_duration (segundos) para la fila de transferencia.

    Paso A: si hay destination_agent_id, segmentos de ese agente ordenados por
    tiempo; k = nº de transferencias anteriores con el mismo destino.

    Paso B (fallback): índice de la transferencia en la lista ordenada → mismo
    índice en agent_segments ordenados cronológicamente (p. ej. transfer a
    CAMPAIGN sin agente destino).
    """
    sec = None
    dest = transfer.destination_agent_id
    if dest is not None:
        ordered = _ordered_segments_for_agent(segments, dest)
        if ordered:
            k = sum(
                1 for t in transfers_ordered
                if t.id < transfer.id and t.destination_agent_id == dest
            )
            if k < len(ordered):
                sec = _talk_duration_seconds_from_segment(ordered[k])

    if sec is None:
        chronological = _ordered_segments_chronologically(segments)
        transfer_index = next(
            (
                i for i, t in enumerate(transfers_ordered)
                if t.id == transfer.id
            ),
            None,
        )
        if (
            transfer_index is not None
            and transfer_index < len(chronological)
        ):
            sec = _talk_duration_seconds_from_segment(
                chronological[transfer_index],
            )

    return sec


def _segment_agent_id_value(seg):
    """Extrae agent_id entero de un dict de segmento o None si no es válido."""
    if not isinstance(seg, dict):
        return None
    raw = seg.get('agent_id')
    if raw is None:
        return None
    try:
        aid = int(raw)
    except (TypeError, ValueError):
        return None
    if aid == -1:
        return None
    return aid


def _campaign_answering_agent_id_from_segments(transfer, transfers_ordered, segments):
    """
    Para transferencia a CAMPAIGN sin destination_agent_id y status OK, infiere el
    agent_id del tramo siguiente en agent_segments (quien atiende tras la transferencia).
    """
    if (transfer.destination_type or '').upper() != 'CAMPAIGN':
        return None
    if transfer.destination_agent_id is not None:
        return None
    if (transfer.status or '').upper() != 'OK':
        return None
    chronological = _ordered_segments_chronologically(segments)
    transfer_index = next(
        (
            i for i, t in enumerate(transfers_ordered)
            if t.id == transfer.id
        ),
        None,
    )
    if transfer_index is None:
        return None
    seg_idx = transfer_index + 1
    if seg_idx >= len(chronological):
        return None
    return _segment_agent_id_value(chronological[seg_idx])


def _format_duration_mmss(seconds):
    """
    Formato MM:SS si < 1 h; si no H:MM:SS (sin relleno de horas a 2 dígitos).
    """
    if seconds is None:
        return '—'
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return '—'
    if total < 0:
        total = 0
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return '{:d}:{:02d}:{:02d}'.format(h, m, s)
    return '{:02d}:{:02d}'.format(m, s)


def _segment_duration_display_for_transfer(transfer, transfers_ordered, segments):
    """Etiqueta de duración del segmento (channel_data) o fallback talk_time_after."""
    sec = _segment_duration_seconds_for_transfer(transfer, transfers_ordered, segments)
    if sec is None:
        tta = getattr(transfer, 'talk_time_after', None)
        if tta is not None:
            try:
                tta_f = float(tta)
                if tta_f > 0:
                    sec = tta_f
            except (TypeError, ValueError):
                pass
    if sec is None:
        return '—'
    return _format_duration_mmss(sec)


def _build_agent_labels_map(agent_ids):
    """
    id -> nombre legible (mismo criterio que listado llamadas atendidas:
    nombre completo o username).
    """
    ids = {aid for aid in agent_ids if aid is not None and aid != -1}
    if not ids:
        return {}
    labels = {}
    for ap in AgenteProfile.objects.filter(pk__in=ids).select_related('user'):
        nombre = (ap.user.get_full_name() or ap.user.username) if ap.user else ''
        labels[ap.id] = nombre if nombre else str(ap.id)
    return labels


def _build_campaign_labels_map(campaign_ids):
    """id campaña -> nombre."""
    ids = {cid for cid in campaign_ids if cid is not None}
    if not ids:
        return {}
    return dict(Campana.objects.filter(pk__in=ids).values_list('id', 'nombre'))


def _agent_label_for_transfer(agent_id, labels_map):
    if agent_id is None or agent_id == -1:
        return '—'
    if agent_id in labels_map:
        return labels_map[agent_id]
    return str(agent_id)


def _campaign_label_for_transfer(campaign_id, labels_map):
    if campaign_id is None:
        return '—'
    if campaign_id in labels_map:
        return labels_map[campaign_id]
    return str(campaign_id)


def _interaction_transfer_to_dict(
        transfer, agent_labels, campaign_labels, segment_duration_display='—',
        campaign_answered_agent_id=None):
    """Serializa InteractionTransfers a dict JSON-friendly."""
    def _dt_iso(dt):
        if dt is None:
            return None
        return dt.isoformat()

    dest_label_id = transfer.destination_agent_id
    if dest_label_id is None and campaign_answered_agent_id is not None:
        dest_label_id = campaign_answered_agent_id

    return {
        'id': transfer.id,
        'destination_target': transfer.destination_target,
        'destination_type': transfer.destination_type,
        'transfer_type': transfer.transfer_type,
        'status': transfer.status,
        'source_agent_id': transfer.source_agent_id,
        'destination_agent_id': transfer.destination_agent_id,
        'destination_campaign_id': transfer.destination_campaign_id,
        'source_agent_label': _agent_label_for_transfer(
            transfer.source_agent_id, agent_labels,
        ),
        'destination_agent_label': _agent_label_for_transfer(
            dest_label_id, agent_labels,
        ),
        'destination_campaign_label': _campaign_label_for_transfer(
            transfer.destination_campaign_id, campaign_labels,
        ),
        'segment_duration': segment_duration_display,
        'destination_external_endpoint': transfer.destination_external_endpoint,
        'source_channel': transfer.source_channel,
        'created_at': _dt_iso(transfer.created_at),
        'completed_at': _dt_iso(transfer.completed_at),
        'talk_time_after': _decimal_to_float(transfer.talk_time_after),
        'fail_reason': transfer.fail_reason,
    }


class InteractionTransfersPorLlamadaAPIView(APIView):
    """
    GET /api/v1/reporte/centro_contacto/interaction_transfers/
    Query: interaction_id (obligatorio). Lista registros de interaction_transfers
    si el usuario puede ver la interacción (misma regla de campañas que el reporte).
    """
    permission_classes = (TienePermisoInteractionTransfersOGrabacionBuscar,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['get']

    def get(self, request):
        raw_id = request.query_params.get('interaction_id')
        if raw_id is None or not str(raw_id).strip():
            return Response(
                {'error': _('Parámetro interaction_id requerido.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        interaction_id = str(raw_id).strip()
        if len(interaction_id) > 64:
            return Response(
                {'error': _('interaction_id inválido.')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        summary = InteractionsSummary.objects.filter(
            interaction_id=interaction_id,
        ).first()
        if not summary:
            return Response(
                {'error': _('Interacción no encontrada.')},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_admin = request.user.get_is_administrador()
        if not is_admin:
            if summary.campaign_id is None:
                # Sin campaña solo administradores (evita filtrar por visibilidad ambigua).
                return Response(
                    {'error': _('No autorizado.')},
                    status=status.HTTP_403_FORBIDDEN,
                )
            supervisor = request.user.get_supervisor_profile()
            campanas = supervisor.campanas_asignadas_actuales()
            allowed_ids = set(campanas.values_list('pk', flat=True))
            if summary.campaign_id not in allowed_ids:
                return Response(
                    {'error': _('No autorizado.')},
                    status=status.HTTP_403_FORBIDDEN,
                )

        transfers = list(
            InteractionTransfers.objects.filter(
                interaction_id=interaction_id,
            ).order_by('id')
        )
        segments = _parse_agent_segments(summary.channel_data)
        campaign_answered_agent_by_transfer_id = {
            t.id: _campaign_answering_agent_id_from_segments(t, transfers, segments)
            for t in transfers
        }
        agent_ids = set()
        campaign_ids = set()
        for t in transfers:
            if t.source_agent_id is not None:
                agent_ids.add(t.source_agent_id)
            if t.destination_agent_id is not None:
                agent_ids.add(t.destination_agent_id)
            if t.destination_campaign_id is not None:
                campaign_ids.add(t.destination_campaign_id)
            answered_id = campaign_answered_agent_by_transfer_id.get(t.id)
            if answered_id is not None:
                agent_ids.add(answered_id)
        agent_labels = _build_agent_labels_map(agent_ids)
        campaign_labels = _build_campaign_labels_map(campaign_ids)
        return Response(
            {
                'transfers': [
                    _interaction_transfer_to_dict(
                        t,
                        agent_labels,
                        campaign_labels,
                        segment_duration_display=_segment_duration_display_for_transfer(
                            t, transfers, segments,
                        ),
                        campaign_answered_agent_id=campaign_answered_agent_by_transfer_id.get(
                            t.id,
                        ),
                    )
                    for t in transfers
                ],
            },
            status=status.HTTP_200_OK,
        )


def _parse_time(value):
    """Convierte string 'HH:MM' o 'HH:MM:SS' a time o None."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if hasattr(value, 'hour'):
        return value
    s = str(value).strip()
    if not s:
        return None
    parts = s.split(':')
    if len(parts) >= 2:
        try:
            h, m = int(parts[0]), int(parts[1])
            sec = int(parts[2]) if len(parts) > 2 else 0
            return dt_datetime.strptime('{:02d}:{:02d}:{:02d}'.format(h, m, sec), '%H:%M:%S').time()
        except (ValueError, IndexError):
            pass
    return None


def _parse_export_filters(request):
    """
    Parsea request.data (POST) del formulario de reporte centro de contacto
    y retorna (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
    customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
    duracion_bot_min) para el servicio CSV.
    Lanza Response(400) si faltan datos o son inválidos.
    """
    data = getattr(request, 'data', None) or {}
    if hasattr(request, 'data'):
        data = request.data
    # Normalizar listas (DRF puede devolver dict o QueryDict)
    def _get_list(key):
        val = data.get(key)
        if val is None and hasattr(data, 'getlist'):
            return data.getlist(key) or []
        if isinstance(val, (list, tuple)):
            return list(val)
        if val is not None and val != '':
            return [val]
        return []
    task_id = data.get('task_id')
    if not task_id or not str(task_id).strip():
        return None, Response(
            {'error': _('Falta task_id')},
            status=status.HTTP_400_BAD_REQUEST
        )

    desde_str = data.get('desde') or ''
    hasta_str = data.get('hasta') or ''
    if not desde_str.strip() or not hasta_str.strip():
        return None, Response(
            {'error': _('Indique rango de fechas (desde y hasta).')},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        desde = convert_fecha_datetime(desde_str.strip())
        hasta = convert_fecha_datetime(hasta_str.strip(), final_dia=True)
    except (ValueError, IndexError, TypeError):
        return None, Response(
            {'error': _('Formato de fecha inválido. Use dd/mm/aaaa.')},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user
    incluir_finalizadas = data.get('incluir_finalizadas') in (True, 'true', '1', 1)
    campanas_visibles = _get_campanas_visibles(user, incluir_finalizadas)
    campanas_visibles_ids = list(campanas_visibles.values_list('pk', flat=True))

    campanas_seleccionadas = _get_list('campana')

    if (
        not campanas_seleccionadas or
        ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE in campanas_seleccionadas
    ):
        allowed_campaigns = campanas_visibles_ids
    else:
        try:
            selected_campaign_ids = [int(c) for c in campanas_seleccionadas]
        except (TypeError, ValueError):
            return None, Response({'error': _('Campaña inválida.')}, status=status.HTTP_400_BAD_REQUEST)
        visible_set = set(campanas_visibles_ids)
        if not set(selected_campaign_ids).issubset(visible_set):
            return None, Response({'error': _('Campaña inválida.')}, status=status.HTTP_400_BAD_REQUEST)
        allowed_campaigns = selected_campaign_ids

    grupos_visibles = Grupo.objects.filter(
        agentes__campana_member__queue_name__campana__in=campanas_visibles
    ).distinct()
    grupos_visibles_ids = set(grupos_visibles.values_list('id', flat=True))

    grupos_seleccionados = _get_list('grupo_agente')

    if (
        not grupos_seleccionados or
        ReporteCentroContactoForm.TODOS_LOS_GRUPOS_VALUE in grupos_seleccionados
    ):
        allowed_agent_ids_by_group = None
    else:
        try:
            selected_group_ids = [int(g) for g in grupos_seleccionados]
        except (TypeError, ValueError):
            return None, Response({'error': _('Grupo de agentes inválido.')}, status=status.HTTP_400_BAD_REQUEST)
        if not set(selected_group_ids).issubset(grupos_visibles_ids):
            return None, Response({'error': _('Grupo de agentes inválido.')}, status=status.HTTP_400_BAD_REQUEST)
        allowed_agent_ids_by_group = list(
            AgenteProfile.objects.filter(
                grupo_id__in=selected_group_ids,
                campana_member__queue_name__campana_id__in=allowed_campaigns,
            ).distinct().values_list('id', flat=True)
        )

    agentes_visibles_ids = set(
        AgenteProfile.objects.filter(
            campana_member__queue_name__campana__in=campanas_visibles.filter(pk__in=allowed_campaigns)
        ).distinct().values_list('id', flat=True)
    )
    agentes_seleccionados = _get_list('agente')

    if (
        not agentes_seleccionados or
        ReporteCentroContactoForm.TODOS_LOS_AGENTES_VALUE in agentes_seleccionados
    ):
        allowed_agent_ids = allowed_agent_ids_by_group
    else:
        try:
            selected_agent_ids = [int(a) for a in agentes_seleccionados]
        except (TypeError, ValueError):
            return None, Response({'error': _('Agente inválido.')}, status=status.HTTP_400_BAD_REQUEST)
        if not set(selected_agent_ids).issubset(agentes_visibles_ids):
            return None, Response({'error': _('Agente inválido.')}, status=status.HTTP_400_BAD_REQUEST)
        if allowed_agent_ids_by_group is None:
            allowed_agent_ids = selected_agent_ids
        else:
            allowed_group_set = set(allowed_agent_ids_by_group)
            allowed_agent_ids = [aid for aid in selected_agent_ids if aid in allowed_group_set]

    contacto_id = data.get('contacto_id')
    if contacto_id is not None and str(contacto_id).strip() != '':
        try:
            customer_id = int(contacto_id)
        except (TypeError, ValueError):
            customer_id = None
    else:
        customer_id = None

    address_query = (data.get('address') or '').strip() or None
    hora_desde = _parse_time(data.get('hora_desde'))
    hora_hasta = _parse_time(data.get('hora_hasta'))
    duracion_agente_min_raw = data.get('duracion_agente_min')
    duracion_agente_min = None
    if duracion_agente_min_raw is not None and str(duracion_agente_min_raw).strip() != '':
        try:
            n = int(duracion_agente_min_raw)
            duracion_agente_min = n if n > 0 else None
        except (TypeError, ValueError):
            duracion_agente_min = None

    duracion_bot_min_raw = data.get('duracion_bot_min')
    duracion_bot_min = None
    if duracion_bot_min_raw is not None and str(duracion_bot_min_raw).strip() != '':
        try:
            n = int(duracion_bot_min_raw)
            duracion_bot_min = n if n > 0 else None
        except (TypeError, ValueError):
            duracion_bot_min = None

    return (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
            customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
            duracion_bot_min), None


def _get_campanas_visibles(user, incluir_finalizadas=True):
    if user.get_is_administrador():
        campanas = Campana.objects.obtener_actuales()
    else:
        supervisor = user.get_supervisor_profile()
        campanas = supervisor.campanas_asignadas_actuales()
    if not incluir_finalizadas:
        campanas = campanas.exclude(estado=Campana.ESTADO_FINALIZADA)
    return campanas


def _parse_export_filters_with_visible_campaigns(request):
    """Extiende _parse_export_filters con campañas visibles del usuario."""
    parsed, err_response = _parse_export_filters(request)
    if err_response is not None:
        return None, err_response
    data = request.data or {}
    incluir_finalizadas = data.get('incluir_finalizadas') in (True, 'true', '1', 1)
    visible_campaigns = list(
        _get_campanas_visibles(request.user, incluir_finalizadas).values_list('pk', flat=True)
    )
    return parsed + (visible_campaigns,), None


class ExportarCSVCanalidadesCentroContacto(APIView):
    """POST: inicia generación en background del CSV Canalidades por campaña."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_canalidades_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Canalidades por campaña a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVCanalidadesEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Canalidades por campaña (Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CANALIDADES_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_canalidades_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Canalidades por campaña (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVCanalidadesPorHoraCentroContacto(APIView):
    """POST: inicia generación en background del CSV Canalidades por hora."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CANALIDADES_POR_HORA.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_canalidades_por_hora_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Canalidades por hora a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVCanalidadesPorHoraEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Canalidades por hora (Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CANALIDADES_POR_HORA_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_canalidades_por_hora_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Canalidades por hora (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVCanalidadesPorDiaCentroContacto(APIView):
    """POST: inicia generación en background del CSV Canalidades por día."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CANALIDADES_POR_DIA.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_canalidades_por_dia_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Canalidades por día a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVCanalidadesPorDiaEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Canalidades por día (Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CANALIDADES_POR_DIA_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_canalidades_por_dia_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Canalidades por día (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVCanalidadesPorMesCentroContacto(APIView):
    """POST: inicia generación en background del CSV Canalidades por mes."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CANALIDADES_POR_MES.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_canalidades_por_mes_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Canalidades por mes a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVCanalidadesPorMesEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Canalidades por mes (Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CANALIDADES_POR_MES_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_canalidades_por_mes_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Canalidades por mes (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasAtendidasCentroContacto(APIView):
    """POST: inicia generación en background del CSV Listado de llamadas atendidas (Ingresos/Voz)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_ATENDIDAS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_atendidas_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Listado de llamadas atendidas a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasAtendidasEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Listado de llamadas atendidas (Egresos/Voz)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_ATENDIDAS_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_atendidas_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Listado de llamadas atendidas (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasNoAtendidasCentroContacto(APIView):
    """POST: inicia generación en background del CSV Listado de llamadas no atendidas (Ingresos/Voz)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_NO_ATENDIDAS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_no_atendidas_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Listado de llamadas no atendidas a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasNoAtendidasEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Listado de llamadas no atendidas (Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_NO_ATENDIDAS_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_no_atendidas_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Listado de llamadas no atendidas (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasVozCentroContacto(APIView):
    """POST: inicia generación en background del CSV Llamadas de voz por campaña (Ingresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters_with_visible_campaigns(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min, visible_campaigns) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_VOZ.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_voz_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'visible_campaigns': visible_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Llamadas de voz por campaña a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasVozEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Llamadas de voz por campaña (Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_VOZ_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_voz_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Llamadas de voz por campaña (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasPorHoraCentroContacto(APIView):
    """POST: inicia generación en background del CSV Llamadas por hora de día (Ingresos/Voz/Horas)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_POR_HORA.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_por_hora_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Llamadas por hora de día a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasPorHoraEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Llamadas por hora de día (Egresos/Voz/Horas)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_POR_HORA_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_por_hora_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Llamadas por hora de día (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasPorDiaCentroContacto(APIView):
    """POST: inicia generación en background del CSV Llamadas por día (Ingresos/Voz/Días)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_POR_DIA.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_por_dia_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Llamadas por día a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasPorDiaEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Llamadas por día (Egresos/Voz/Días)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_POR_DIA_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_por_dia_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Llamadas por día (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasPorMesCentroContacto(APIView):
    """POST: inicia generación en background del CSV Llamadas por mes (Ingresos/Voz/Mes)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_POR_MES.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_por_mes_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Llamadas por mes a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVLlamadasPorMesEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Llamadas por mes (Egresos/Voz/Mes)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_LLAMADAS_POR_MES_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_llamadas_por_mes_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Llamadas por mes (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVConversacionesRespondidasCentroContacto(APIView):
    """POST: inicia generación en background del CSV Conversaciones Respondidas (Ingresos WhatsApp)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CONV_RESP.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_conversaciones_respondidas_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Conversaciones Respondidas a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVConversacionesRespondidasEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Conversaciones Respondidas (Egresos WhatsApp)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CONV_RESP_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_conversaciones_respondidas_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Conversaciones Respondidas (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVConversacionesNoRespondidasCentroContacto(APIView):
    """POST: inicia generación en background del CSV Conversaciones no respondidas (Ingresos WhatsApp)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CONV_NO_RESP.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_conversaciones_no_respondidas_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Conversaciones no respondidas a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVConversacionesNoRespondidasEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Conversaciones no respondidas (Egresos WhatsApp)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_CONV_NO_RESP_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_conversaciones_no_respondidas_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Conversaciones no respondidas (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVWhatsappMensajesPorHoraCentroContacto(APIView):
    """POST: inicia generación en background del CSV Mensajes por hora de día (WhatsApp Ingresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_WA_MSG_HORA.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_whatsapp_mensajes_por_hora,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Mensajes por hora de día a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVWhatsappMensajesPorHoraEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Mensajes por hora (WhatsApp Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_WA_MSG_HORA_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_whatsapp_mensajes_por_hora_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Mensajes por hora (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVWhatsappMensajesPorCampanaCentroContacto(APIView):
    """POST: inicia generación en background del CSV Mensajes por campaña (WhatsApp Ingresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_WA_MSG_CAMPANA.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_whatsapp_mensajes_por_campana,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Mensajes por campaña a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVWhatsappMensajesPorCampanaEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Mensajes por campaña (WhatsApp Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_WA_MSG_CAMPANA_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_whatsapp_mensajes_por_campana_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'customer_id': customer_id,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Mensajes por campaña (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVWhatsappMensajesPorDiaCentroContacto(APIView):
    """POST: inicia generación en background del CSV Mensajes por día (WhatsApp Ingresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_WA_MSG_DIA.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_whatsapp_mensajes_por_dia,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Mensajes por día a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVWhatsappMensajesPorDiaEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Mensajes por día (WhatsApp Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_WA_MSG_DIA_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_whatsapp_mensajes_por_dia_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Mensajes por día (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVWhatsappMensajesPorMesCentroContacto(APIView):
    """POST: inicia generación en background del CSV Mensajes por mes (WhatsApp Ingresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_WA_MSG_MES.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_whatsapp_mensajes_por_mes,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Mensajes por mes a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )


class ExportarCSVWhatsappMensajesPorMesEgresosCentroContacto(APIView):
    """POST: inicia generación en background del CSV Mensajes por mes (WhatsApp Egresos)."""
    permission_classes = (TienePermisoOML,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        parsed, err_response = _parse_export_filters(request)
        if err_response is not None:
            return err_response
        (task_id, desde, hasta, allowed_campaigns, allowed_agent_ids,
         customer_id, address_query, hora_desde, hora_hasta, duracion_agente_min,
         duracion_bot_min) = parsed

        key_task = KEY_TASK_TEMPLATE_WA_MSG_MES_EGRESOS.format(task_id=task_id)
        thread = threading.Thread(
            target=generar_csv_whatsapp_mensajes_por_mes_egresos_centro_contacto,
            kwargs={
                'key_task': key_task,
                'task_id': task_id,
                'start_date': desde,
                'end_date': hasta,
                'allowed_campaigns': allowed_campaigns,
                'allowed_agent_ids': allowed_agent_ids,
                'address_query': address_query,
                'hora_desde': hora_desde,
                'hora_hasta': hora_hasta,
                'duracion_agente_min': duracion_agente_min,
                'duracion_bot_min': duracion_bot_min,
            },
            daemon=True,
        )
        thread.start()
        return Response(
            data={
                'status': 'OK',
                'msg': _('Exportación de Mensajes por mes (Egresos) a CSV en proceso.'),
                'id': task_id,
            },
            status=status.HTTP_200_OK,
        )
