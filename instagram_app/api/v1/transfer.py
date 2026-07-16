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
from django.utils.translation import gettext as _
from rest_framework import decorators, response, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication

from instagram_app.api.permissions import TienePermisoCanalInstagramAgente
from instagram_app.api.utils import HttpResponseStatus, get_response_data
from instagram_app.models import ConversationInstagramApp
from notification_app.notification import AgentNotifier
from ominicontacto_app.models import AgenteProfile, Campana


class AgenteListSerializer(serializers.Serializer):
    agent_id = serializers.IntegerField(source='user_id')
    agent_full_name = serializers.CharField(source='user.username')
    status = serializers.CharField(source='estado')


class ViewSet(viewsets.ViewSet):
    permission_classes = [TienePermisoCanalInstagramAgente]
    authentication_classes = (SessionAuthentication, )

    @decorators.action(detail=False, methods=['get'], url_path='(?P<campana_pk>[^/.]+)/agents')
    def agents(self, request, campana_pk):
        try:
            queryset = Campana.objects.get(id=campana_pk).obtener_agentes()
            if request.user.is_agente:
                queryset = queryset.exclude(user_id=request.user.id)
            serializer = AgenteListSerializer(queryset, many=True)
            return response.Response(
                data=get_response_data(status=HttpResponseStatus.SUCCESS, data=serializer.data),
                status=status.HTTP_200_OK)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al obtener los agentes')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=False, methods=['post'])
    def to_agent(self, request):
        try:
            chat_id = request.data.get('conversationId')
            agent_id = request.data.get('to')
            conversacion = ConversationInstagramApp.objects.get(id=chat_id)
            agent = AgenteProfile.objects.get(user__id=agent_id)
            success = conversacion.otorgar_conversacion(agent, attended=False)
            if success:
                AgentNotifier().notify_instagram_chat_transfered(
                    request.user.username, agent_id, conversacion)
                return response.Response(
                    data=get_response_data(status=HttpResponseStatus.SUCCESS),
                    status=status.HTTP_200_OK)
            return response.Response(
                data=get_response_data(message=_('Error al tranferir conversacion')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al tranferir conversacion')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
