# Copyright (C) 2026 Freetech Solutions
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
# Supervisor-facing email reporting/conversation listing for a campaign. Mirrors
# the WhatsApp "Reportes" / "Conversaciones" (whatsapp_app.api.v1.reporte and
# .conversacion.filter_chats) but exposes EMAIL-appropriate fields: the user's
# email address instead of a phone number, "correos" instead of "mensajes", the
# mail account instead of the WhatsApp line, etc. These endpoints are consumed by
# the webui supervisor pages, not by the agent console.

import logging

from django.db.models import Count, Q
from django.utils.translation import ugettext as _
from rest_framework import response
from rest_framework import serializers
from rest_framework import status
from rest_framework.views import APIView

from ominicontacto_app.models import Campana
from ominicontacto_app.utiles import (
    datetime_hora_minima_dia, datetime_hora_maxima_dia)

from ... import models
from ..permissions import ViewPermission
from .conversation import MessageSerializer

log = logging.getLogger(__name__)


class RangeSerializer(serializers.Serializer):
    """Date range coming from the webui (YYYY-MM-DD), expanded to the full day."""
    start_date = serializers.DateField()
    end_date = serializers.DateField()

    def range(self):
        return (
            datetime_hora_minima_dia(self.validated_data["start_date"]),
            datetime_hora_maxima_dia(self.validated_data["end_date"]),
        )


def _campaign_or_404(pk_campana):
    try:
        return Campana.objects.get(pk=pk_campana)
    except Campana.DoesNotExist:
        return None


def _agent_payload(conversation):
    if not conversation.agent_id:
        return None
    agente = conversation.agent
    name = ""
    if agente.user_id:
        name = agente.user.get_full_name() or agente.user.username
    return {"id": agente.id, "name": name or str(agente.id)}


def _disposition_name(conversation):
    historica = conversation.conversation_disposition
    if historica is None:
        return ""
    opcion = getattr(historica, "opcion_calificacion", None)
    return opcion.nombre if opcion is not None else ""


# --- Reporte general -------------------------------------------------------

def build_campaign_report(campana, start, end):
    """Email-appropriate metrics for ``campana`` in the [start, end] window.

    Translation of the WhatsApp report concepts to email:
        sent/received messages -> correos enviados/recibidos
        attended/not-attended chats -> conversaciones atendidas/sin atender
        outbound failed -> correos fallidos
        dispositions -> calificaciones (igual que WhatsApp)
    Email has no "expired" (24h window) concept, so those metrics are dropped;
    "answered" (Respondido / pendiente cliente) and "reopened" are added instead.
    """
    Conv = models.ConversacionEmail
    Msg = models.Message

    convs = Conv.objects.filter(campana=campana, timestamp__range=(start, end))
    msgs = Msg.objects.filter(
        conversation__campana=campana, date__range=(start, end))
    inbound = msgs.filter(direction=Msg.DIRECTION_INBOUND)
    outbound = msgs.filter(direction=Msg.DIRECTION_OUTBOUND)
    failed = outbound.filter(
        Q(status__in=["error", "failed"]) | ~Q(fail_reason=""))

    dispositions_done = list(
        convs.filter(
            is_disposition=True, conversation_disposition__isnull=False)
        .values("conversation_disposition__opcion_calificacion__nombre")
        .annotate(total=Count("id"))
    )
    not_disposed = convs.filter(is_disposition=False).count()

    return {
        "correos_recibidos": inbound.count(),
        "correos_enviados": outbound.count(),
        "correos_fallidos": failed.count(),
        "conversaciones_iniciadas": convs.count(),
        "conversaciones_atendidas": convs.filter(atendida=True).count(),
        "conversaciones_sin_atender": convs.filter(
            atendida=False, status__in=Conv.GENERAL_INBOX_QUEUED).count(),
        "conversaciones_respondidas": convs.filter(
            status=Conv.STATUS_ANSWERED).count(),
        "conversaciones_reabiertas": convs.filter(
            status=Conv.STATUS_REOPENED).count(),
        "conversaciones_calificadas": convs.filter(is_disposition=True).count(),
        "conversaciones_sin_calificar": not_disposed,
        "dispositions": {
            "done": [
                {item["conversation_disposition__opcion_calificacion__nombre"]:
                    item["total"]}
                for item in dispositions_done
            ],
            "not_done": not_disposed,
        },
    }


class CampaignReportAPIView(APIView):
    permission_classes = [ViewPermission]

    def post(self, request, pk_campana):
        campana = _campaign_or_404(pk_campana)
        if campana is None:
            return response.Response(
                data={"detail": _("The campaign does not exist.")},
                status=status.HTTP_404_NOT_FOUND)
        rango = RangeSerializer(data=request.data)
        rango.is_valid(raise_exception=True)
        start, end = rango.range()
        return response.Response(data=build_campaign_report(campana, start, end))


# --- Conversaciones --------------------------------------------------------

class SupervisorConversationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    subject = serializers.CharField()
    client_mail = serializers.CharField()
    client_name = serializers.CharField()
    status = serializers.CharField()
    is_active = serializers.BooleanField()
    is_disposition = serializers.BooleanField()
    timestamp = serializers.DateTimeField()
    date_last_interaction = serializers.DateTimeField()
    account_name = serializers.SerializerMethodField()
    campaign_name = serializers.SerializerMethodField()
    agent = serializers.SerializerMethodField()
    disposition = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    received = serializers.SerializerMethodField()
    sent = serializers.SerializerMethodField()

    def get_account_name(self, conversation):
        return conversation.account.name if conversation.account_id else ""

    def get_campaign_name(self, conversation):
        return conversation.campana.nombre if conversation.campana_id else ""

    def get_agent(self, conversation):
        return _agent_payload(conversation)

    def get_disposition(self, conversation):
        return _disposition_name(conversation)

    def get_messages(self, conversation):
        value = getattr(conversation, "messages_count", None)
        return value if value is not None else conversation.mensajes.count()

    def get_received(self, conversation):
        value = getattr(conversation, "received_count", None)
        if value is not None:
            return value
        return conversation.mensajes.filter(
            direction=models.Message.DIRECTION_INBOUND).count()

    def get_sent(self, conversation):
        value = getattr(conversation, "sent_count", None)
        if value is not None:
            return value
        return conversation.mensajes.filter(
            direction=models.Message.DIRECTION_OUTBOUND).count()


class SupervisorConversationDetailSerializer(SupervisorConversationSerializer):
    mensajes = serializers.SerializerMethodField()

    def get_mensajes(self, conversation):
        ordered = conversation.mensajes.order_by("date", "id")
        return MessageSerializer(ordered, many=True).data


class FilterSerializer(RangeSerializer):
    email = serializers.CharField(
        required=False, allow_blank=True, default="")
    # agent ids to keep; -1 means "sin agente" (unassigned). Empty -> all.
    agents = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list)


def _scoped_conversations(campana):
    return models.ConversacionEmail.objects.filter(
        campana=campana
    ).select_related(
        "account", "campana", "agent__user",
        "conversation_disposition__opcion_calificacion",
    ).annotate(
        messages_count=Count("mensajes", distinct=True),
        received_count=Count(
            "mensajes",
            filter=Q(mensajes__direction=models.Message.DIRECTION_INBOUND),
            distinct=True),
        sent_count=Count(
            "mensajes",
            filter=Q(mensajes__direction=models.Message.DIRECTION_OUTBOUND),
            distinct=True),
    )


class CampaignConversationsAPIView(APIView):
    permission_classes = [ViewPermission]

    def post(self, request, pk_campana):
        campana = _campaign_or_404(pk_campana)
        if campana is None:
            return response.Response(
                data={"detail": _("The campaign does not exist.")},
                status=status.HTTP_404_NOT_FOUND)
        filtros = FilterSerializer(data=request.data)
        filtros.is_valid(raise_exception=True)
        start, end = filtros.range()
        qs = _scoped_conversations(campana).filter(timestamp__range=(start, end))
        email = filtros.validated_data["email"].strip()
        if email:
            qs = qs.filter(client_mail__icontains=email)
        agents = filtros.validated_data["agents"]
        if agents:
            condition = Q()
            ids = [a for a in agents if a != -1]
            if ids:
                condition |= Q(agent_id__in=ids)
            if -1 in agents:
                condition |= Q(agent__isnull=True)
            qs = qs.filter(condition)
        return response.Response(
            data=SupervisorConversationSerializer(qs, many=True).data)


class CampaignConversationDetailAPIView(APIView):
    permission_classes = [ViewPermission]

    def get(self, request, pk_campana, pk):
        campana = _campaign_or_404(pk_campana)
        if campana is None:
            return response.Response(
                data={"detail": _("The campaign does not exist.")},
                status=status.HTTP_404_NOT_FOUND)
        try:
            conversation = _scoped_conversations(campana).get(pk=pk)
        except models.ConversacionEmail.DoesNotExist:
            return response.Response(
                data={"detail": _("The conversation does not exist.")},
                status=status.HTTP_404_NOT_FOUND)
        return response.Response(
            data=SupervisorConversationDetailSerializer(conversation).data)


class CampaignAgentsAPIView(APIView):
    """Agents of the campaign, to populate the conversation filter dropdown."""
    permission_classes = [ViewPermission]

    def get(self, request, pk_campana):
        campana = _campaign_or_404(pk_campana)
        if campana is None:
            return response.Response(
                data={"detail": _("The campaign does not exist.")},
                status=status.HTTP_404_NOT_FOUND)
        data = []
        try:
            members = campana.obtener_agentes()
        except Exception:
            # campaign without a queue yet -> no agents to filter by
            members = []
        for member in members:
            agente = member.member
            name = ""
            if agente.user_id:
                name = agente.user.get_full_name() or agente.user.username
            data.append({"id": agente.id, "name": name or str(agente.id)})
        return response.Response(data=data)
