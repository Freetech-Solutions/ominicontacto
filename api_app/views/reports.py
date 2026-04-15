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

import redis
from datetime import datetime
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, Sum
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.services.redis.connection import create_redis_connection
from ominicontacto_app.services.asterisk.redis_database import CampaignAgentsFamily, AgenteFamily
from ominicontacto_app.models import Campana
from ominicontacto_app.utiles import datetime_hora_minima_dia, datetime_hora_maxima_dia
from reportes_app.models import LlamadaLog, InteractionsSummary, InteractionTransfers


class AgentStatusView(APIView):
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    renderer_classes = (JSONRenderer, )
    http_method_names = ['get']

    def get(self, request, campaign_id):
        campaign = get_object_or_404(Campana, pk=campaign_id)
        campaign_agents = campaign.obtener_agentes().values_list('id', flat=True)
        data = dict.fromkeys(['ready', 'oncall', 'pause'], 0)
        redis_connection = redis.Redis(
            host=settings.REDIS_HOSTNAME, port=settings.CONSTANCE_REDIS_CONNECTION['port'],
            decode_responses=True)
        keys_agentes = redis_connection.keys('OML:AGENT:*')
        for key in keys_agentes:
            if int(key.split('OML:AGENT:')[1]) in campaign_agents:
                agente_info = redis_connection.hgetall(key)
                if agente_info['STATUS'] == 'READY':
                    data['ready'] += 1
                elif agente_info['STATUS'] == 'ONCALL':
                    data['oncall'] += 1
                elif agente_info['STATUS'].startswith('PAUSE'):
                    data['pause'] += 1
        return Response(data)


class AgentStatusListView(APIView):
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    renderer_classes = (JSONRenderer, )
    http_method_names = ['get']

    def get(self, request, campaign_id):
        # Verifico que exista en la base de datos.
        get_object_or_404(Campana, pk=campaign_id)
        redis_connection = create_redis_connection()
        key = CampaignAgentsFamily.KEY_PREFIX.format(campaign_id)
        agents_ids = redis_connection.smembers(key)
        data = []
        for agent_id in agents_ids:
            key_agent = AgenteFamily.KEY_PREFIX.format(agent_id)
            agent_data = redis_connection.hmget(key_agent, 'NAME', 'STATUS')
            name = agent_data[0]
            if name:
                data.append({'name': name,
                             'status': self._parse_status(agent_data[1])})
        return Response(data)

    def _parse_status(self, status):
        print(status)
        if status.startswith('PAUSE'):
            return 'PAUSE'
        if status == '' or status is None:
            return 'OFFLINE'
        return status


class CallStatusView(APIView):
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    renderer_classes = (JSONRenderer, )
    http_method_names = ['get']

    def get(self, request, campaign_id):
        start = request.GET.get('date_start', None)
        end = request.GET.get('date_end', None)
        call_logs = LlamadaLog.objects.filter(campana_id=campaign_id)
        if start and end:
            format_date = "%Y-%m-%d"
            start = datetime_hora_minima_dia(datetime.strptime(start, format_date))
            end = datetime_hora_maxima_dia(datetime.strptime(end, format_date))
            call_logs = call_logs.filter(time__range=(start, end))

        data = dict.fromkeys(['attended', 'abandoned', 'expired'], 0)
        attended = call_logs.filter(event__in=LlamadaLog.EVENTOS_INICIO_CONEXION_AGENTE).count()
        abandoned = call_logs.filter(event__in=LlamadaLog.EVENTOS_NO_DIALOGO).count()
        expired = call_logs.filter(event__in=LlamadaLog.EVENTOS_NO_CONTACTACION).count()
        data = {
            'attended': attended,
            'abandoned': abandoned,
            'expired': expired
        }
        return Response(data)


class CampaignStatsReportView(APIView):
    """
    GET /api/reports/campaign-stats/
    Query params: campaign_id (obligatorio), start_date, end_date (opcionales, formato YYYY-MM-DD).
    Devuelve KPIs: contact_rate, conversion_rate, rpc (y opcionalmente contadores en totals).
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['get']

    def get(self, request):
        campaign_id = request.GET.get('campaign_id')
        if campaign_id is None or campaign_id == '':
            return Response(
                {'error': 'campaign_id es obligatorio'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            campaign_id = int(campaign_id)
        except (ValueError, TypeError):
            return Response(
                {'error': 'campaign_id debe ser un entero'},
                status=status.HTTP_400_BAD_REQUEST
            )

        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        format_date = '%Y-%m-%d'

        if start_date:
            try:
                start_date = datetime.strptime(start_date, format_date).date()
            except ValueError:
                return Response(
                    {'error': 'start_date debe tener formato YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        if end_date:
            try:
                end_date = datetime.strptime(end_date, format_date).date()
            except ValueError:
                return Response(
                    {'error': 'end_date debe tener formato YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        transferidas_in_ids = (
            InteractionTransfers.objects.filter(
                destination_campaign_id=campaign_id
            ).values_list('interaction_id', flat=True)
        )
        qs = InteractionsSummary.objects.filter(
            Q(campaign_id=campaign_id) | Q(interaction_id__in=transferidas_in_ids)
        )
        if start_date:
            qs = qs.filter(start_time__gte=datetime_hora_minima_dia(start_date))
        if end_date:
            qs = qs.filter(start_time__lte=datetime_hora_maxima_dia(end_date))

        stats = qs.aggregate(
            total=Count('id'),
            total_outbound=Count('id', filter=Q(direction='OUTBOUND')),
            outbound_answered=Count('id', filter=Q(direction='OUTBOUND', status='EXIT_ANSWERED')),
            answered_direct=Count('id', filter=Q(campaign_id=campaign_id, status='EXIT_ANSWERED')),
            answered_transferred=Count(
                'id', filter=Q(interaction_id__in=transferidas_in_ids, status='EXIT_ANSWERED')
            ),
            sales=Count('id', filter=Q(is_sale=True)),
            answered_by_agent=Count(
                'id',
                filter=Q(status='EXIT_ANSWERED') & (Q(agent_id__isnull=False) | Q(agent_duration__gt=0))
            ),
            answered_agent_gt_10s=Count(
                'id',
                filter=Q(status='EXIT_ANSWERED', agent_duration__gt=10)
            ),
            # KPIs adicionales
            sum_agent_duration_gt0=Sum('agent_duration', filter=Q(agent_duration__gt=0)),
            count_agent_duration_gt0=Count('id', filter=Q(agent_duration__gt=0)),
            sum_wait_conn_duration_inbound_answered=Sum(
                'wait_conn_duration', filter=Q(direction='INBOUND', status='EXIT_ANSWERED')
            ),
            count_inbound_answered=Count(
                'id', filter=Q(direction='INBOUND', status='EXIT_ANSWERED')
            ),
            inbound_abandoned_gt5=Count(
                'id',
                filter=Q(direction='INBOUND', status='ABANDONED', wait_conn_duration__gt=5)
            ),
            total_inbound=Count('id', filter=Q(direction='INBOUND')),
            transferred_count=Count('id', filter=Q(is_transferred=True)),
            bot_contained=Count(
                'id',
                filter=Q(agent_duration=0, bot_duration__gt=0, status='EXIT_ANSWERED')
            ),
            sum_bot_duration=Sum('bot_duration'),
        )

        total_outbound = stats['total_outbound'] or 0
        outbound_answered = stats['outbound_answered'] or 0
        answered_direct = stats['answered_direct'] or 0
        answered_transferred = stats['answered_transferred'] or 0
        total_answered = answered_direct + answered_transferred
        sales = stats['sales'] or 0
        answered_by_agent = stats['answered_by_agent'] or 0
        answered_agent_gt_10s = stats['answered_agent_gt_10s'] or 0
        total = stats['total'] or 0

        sum_agent_gt0 = stats['sum_agent_duration_gt0'] or 0
        count_agent_gt0 = stats['count_agent_duration_gt0'] or 0
        sum_queue_ib_answered = stats['sum_wait_conn_duration_inbound_answered'] or 0
        count_ib_answered = stats['count_inbound_answered'] or 0
        inbound_abandoned_gt5 = stats['inbound_abandoned_gt5'] or 0
        total_inbound = stats['total_inbound'] or 0
        transferred_count = stats['transferred_count'] or 0
        bot_contained = stats['bot_contained'] or 0
        sum_bot_duration = stats['sum_bot_duration'] or 0

        contact_rate = round((outbound_answered / total_outbound * 100), 2) if total_outbound else 0
        conversion_rate = round((sales / answered_by_agent * 100), 2) if answered_by_agent else 0
        rpc = round((answered_agent_gt_10s / total * 100), 2) if total else 0

        # AHT: promedio agent_duration donde > 0 (en segundos)
        aht = round(float(sum_agent_gt0 / count_agent_gt0), 3) if count_agent_gt0 else 0
        # ASA: promedio wait_conn_duration solo Inbound Answered (en segundos)
        asa = round(float(sum_queue_ib_answered / count_ib_answered), 3) if count_ib_answered else 0
        # Abandon Rate: (Inbound Abandoned wait_conn_duration>5s / Total Inbound) * 100
        abandon_rate = round((inbound_abandoned_gt5 / total_inbound * 100), 2) if total_inbound else 0
        # Transfer Rate: (is_transferred / atendidas por agente) * 100
        transfer_rate = round((transferred_count / answered_by_agent * 100), 2) if answered_by_agent else 0
        # Bot Containment Rate: (agent_duration=0 y bot_duration>0 y EXIT_ANSWERED / total) * 100
        bot_containment_rate = round((bot_contained / total * 100), 2) if total else 0
        # Bot Total Hours: suma bot_duration / 3600
        bot_total_hours = round(float(sum_bot_duration / 3600), 4) if sum_bot_duration else 0

        data = {
            'campaign_id': campaign_id,
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'contact_rate': contact_rate,
            'conversion_rate': conversion_rate,
            'rpc': rpc,
            'aht': aht,
            'asa': asa,
            'abandon_rate': abandon_rate,
            'transfer_rate': transfer_rate,
            'bot_containment_rate': bot_containment_rate,
            'bot_total_hours': bot_total_hours,
            'total_interactions': total,
            'totals': {
                'total_outbound': total_outbound,
                'outbound_answered': outbound_answered,
                'answered_direct': answered_direct,
                'answered_transferred': answered_transferred,
                'total_answered': total_answered,
                'sales': sales,
                'answered_by_agent': answered_by_agent,
                'answered_agent_gt_10s': answered_agent_gt_10s,
                'total': total,
                'inbound_abandoned_gt5': inbound_abandoned_gt5,
                'total_inbound': total_inbound,
                'transferred_count': transferred_count,
                'bot_contained': bot_contained,
                'sum_bot_duration': float(sum_bot_duration),
            },
        }
        return Response(data)
