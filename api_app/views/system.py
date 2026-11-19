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
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from api_app.authentication import InternalSecretAuthentication, IsInternalComponent
from ominicontacto_app.models import AgenteProfile
from notification_app.notification import AgentNotifier


class NotifyAttendedMultinumCall(APIView):
    authentication_classes = (InternalSecretAuthentication, )
    permission_classes = (IsInternalComponent, )
    http_method_names = ['post', 'POST']
    renderer_classes = (JSONRenderer, )

    def post(self, request, *args, **kwargs):
        agent_id = request.data.get('agent_id')
        try:
            agente = AgenteProfile.objects.get(id=agent_id)
        except (AgenteProfile.DoesNotExist, ValueError, TypeError):
            return Response(data={'status': 'ERROR', 'message': 'Invalid agent_id'},
                            status=status.HTTP_400_BAD_REQUEST)
        phone = request.data.get('phone')
        AgentNotifier().notify_attended_multinum_call(agente.user_id, phone)
        return Response(data={'status': 'OK'})
