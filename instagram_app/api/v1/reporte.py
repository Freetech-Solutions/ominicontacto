# -*- coding: utf-8 -*-
import datetime
from dataclasses import dataclass

from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from rest_framework import response, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from instagram_app.api.utils import HttpResponseStatus, get_response_data
from instagram_app.models import ConversationInstagramApp, MessageInstagramApp
from ominicontacto_app.models import CalificacionCliente, Campana
from ominicontacto_app.utiles import datetime_hora_maxima_dia, datetime_hora_minima_dia


@dataclass
class ReportParams:
    start_date: datetime.datetime
    end_date: datetime.datetime
    campaign: int


class ReporteParamsSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    campaign = serializers.IntegerField()

    def create(self, validated_data):
        validated_data['start_date'] = datetime_hora_minima_dia(validated_data['start_date'])
        validated_data['end_date'] = datetime_hora_maxima_dia(validated_data['end_date'])
        return ReportParams(**validated_data)


@dataclass
class ReporteCampanaInstagram:
    sent_messages: int
    received_messages: int
    interactions_started: int
    attended_chats: int
    not_attended_chats: int
    inbound_chats_attended: int
    inbound_chats_not_attended: int
    inbound_chats_expired: int
    outbound_chats_attended: int
    outbound_chats_not_attended: int
    outbound_chats_expired: int
    outbound_chats_failed: int
    dispositions: dict

    def __init__(self, params):
        campana = Campana.objects.get(id=params.campaign)
        chats = ConversationInstagramApp.objects.filter(campana=campana)
        date_range = Q(timestamp__range=[params.start_date, params.end_date])
        now = timezone.now().astimezone(timezone.get_current_timezone())

        inbound_attended = chats.filter(date_range, atendida=True, agent__isnull=False)
        inbound_not_attended = chats.filter(
            Q(date_range, atendida=False) |
            Q(date_range, is_disposition=True, agent__isnull=True)
        )
        messages = MessageInstagramApp.objects.filter(
            conversation__campana=campana,
            timestamp__range=[params.start_date, params.end_date],
        )

        self.sent_messages = messages.filter(
            origen=F('conversation__account__ig_user_id')
        ).count()
        self.received_messages = messages.exclude(
            origen=F('conversation__account__ig_user_id')
        ).count()
        self.interactions_started = 0
        self.attended_chats = inbound_attended.count()
        self.not_attended_chats = inbound_not_attended.count()
        self.inbound_chats_attended = inbound_attended.count()
        self.inbound_chats_not_attended = inbound_not_attended.count()
        self.inbound_chats_expired = chats.filter(
            date_range, atendida=False, expire__lte=now
        ).count()
        self.outbound_chats_attended = 0
        self.outbound_chats_not_attended = 0
        self.outbound_chats_expired = 0
        self.outbound_chats_failed = 0
        self.dispositions = {
            'done': [
                {item['opcion_calificacion__nombre']: item['total']}
                for item in CalificacionCliente.objects.calificaciones_instagram_campanas(
                    campana, params.start_date, params.end_date
                )
            ],
            'not_done': chats.filter(
                date_range, atendida=True, is_disposition=False
            ).count(),
        }


class ReporteCampanaInstagramSerializer(serializers.Serializer):
    sent_messages = serializers.IntegerField()
    received_messages = serializers.IntegerField()
    interactions_started = serializers.IntegerField()
    attended_chats = serializers.IntegerField()
    not_attended_chats = serializers.IntegerField()
    inbound_chats_attended = serializers.IntegerField()
    inbound_chats_not_attended = serializers.IntegerField()
    inbound_chats_expired = serializers.IntegerField()
    outbound_chats_attended = serializers.IntegerField()
    outbound_chats_not_attended = serializers.IntegerField()
    outbound_chats_expired = serializers.IntegerField()
    outbound_chats_failed = serializers.IntegerField()
    dispositions = serializers.JSONField()


class ReportAPIView(APIView):
    permission_classes = [TienePermisoOML]
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication)

    def post(self, request):
        try:
            params_serializer = ReporteParamsSerializer(
                data={
                    'start_date': request.data.get('start_date'),
                    'end_date': request.data.get('end_date'),
                    'campaign': request.data.get('campaign'),
                },
                context={'request': request},
            )
            params_serializer.is_valid(raise_exception=True)
            params = params_serializer.save()
            data = ReporteCampanaInstagram(params)
            serializer = ReporteCampanaInstagramSerializer(instance=data)
        except Exception as error:
            print(error)
            return response.Response(
                data=get_response_data(message=_('Error al obtener el reporte')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return response.Response(
            data=get_response_data(
                status=HttpResponseStatus.SUCCESS,
                message=_('Reporte obtenido exitosamente'),
                data=serializer.data,
            ),
            status=status.HTTP_200_OK,
        )
