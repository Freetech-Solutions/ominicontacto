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
import os
import logging
import redis
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.authentication import SessionAuthentication

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.services.redis.connection import create_redis_connection
from ominicontacto_app.utiles import reemplazar_no_alfanumericos_por_guion
from ominicontacto_app.models import AgenteProfile, QueueMember
from notification_app.notification import AgentNotifier

logger = logging.getLogger(__name__)

# NODE_ID lógico de este nodo (DEBE matchear con el NODE_ID del acd.py)
NODE_ID = os.getenv('NODE_ID', 'acd01')
# Nombre base del Stream en Redis
BASE_STREAM_KEY = "acd:stream:commands"
# Stream concreto para este nodo
STREAM_KEY = f"{BASE_STREAM_KEY}:{NODE_ID}"


class AsteriskQueuesData(APIView):
    permission_classes = (AllowAny, )
    http_method_names = ['get']
    renderer_classes = (JSONRenderer, )

    def get(self, request):

        agents_data = []
        redis_connection = redis.Redis(
            host=settings.REDIS_HOSTNAME,
            port=settings.CONSTANCE_REDIS_CONNECTION['port'],
            decode_responses=True)
        ids = AgenteProfile.objects.all().values_list('id', flat=True)
        for agent_id in list(ids):
            agent_data = redis_connection.hmget('OML:AGENT:' + str(agent_id),
                                                ['SIP', 'NAME', 'STATUS'])
            status = agent_data[2]
            pause = '0'
            if status and not status == 'OFFLINE':
                sip_extension = agent_data[0]
                member_name = agent_data[1]
                member_name = reemplazar_no_alfanumericos_por_guion(member_name)
                member_name = "{0}_{1}".format(agent_id, member_name)
                if status.startswith('PAUSE'):
                    pause = '1'
                queues = QueueMember.objects.obtener_queue_por_agent(agent_id)
                penalties = QueueMember.objects.obtener_penalty_por_agent(agent_id)
                interface = "PJSIP/" + str(sip_extension).strip('[]')
                agents_data.append([agent_id, member_name, interface, pause, queues, penalties])
        return Response(data=agents_data)


class NotifyAttendedMultinumCall(APIView):
    permission_classes = (AllowAny, )
    http_method_names = ['post', 'POST']
    renderer_classes = (JSONRenderer, )

    def post(self, request, *args, **kwargs):
        agent_id = request.data.get('agent_id')
        agente = AgenteProfile.objects.get(id=agent_id)
        phone = request.data.get('phone')
        AgentNotifier().notify_attended_multinum_call(agente.user_id, phone)
        return Response(data={'status': 'OK'})


class NotifyCallBlocked(APIView):
    """
    Endpoint para notificar al agente que una llamada fue bloqueada.
    Llamado desde el ACD cuando una llamada no pasa la validación de ruta.
    """
    permission_classes = (AllowAny, )
    http_method_names = ['post', 'POST']
    renderer_classes = (JSONRenderer, )

    def post(self, request, *args, **kwargs):
        try:
            agent_id = request.data.get('agent_id')
            phone_number = request.data.get('phone_number')
            campaign_id = request.data.get('campaign_id')
            reason = request.data.get(
                'reason',
                'El número no cumple con los patrones de discado configurados'
            )
            
            if not agent_id or not phone_number:
                return Response(
                    data={'status': 'ERROR', 'message': 'agent_id y phone_number son requeridos'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            agente = AgenteProfile.objects.get(id=agent_id)
            AgentNotifier().notify_call_blocked(
                agente.user_id,
                phone_number,
                campaign_id,
                reason
            )
            return Response(data={'status': 'OK'})
        except AgenteProfile.DoesNotExist:
            return Response(
                data={'status': 'ERROR', 'message': 'Agente no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error notificando llamada bloqueada: {e}", exc_info=True)
            return Response(
                data={'status': 'ERROR', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class HealthCheckView(APIView):
    """
    Health check endpoint para verificar el estado del servicio y la conexión a Redis.
    
    Respuestas:
    - 200: Servicio operativo y Redis conectado
    - 500: Servicio degradado (Redis desconectado)
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['get']

    def get(self, request):
        try:
            r_client = create_redis_connection(db=0)
            r_client.ping()
            response_data = {
                "status": "up",
                "redis": "connected",
                "mode": "stream_producer_sidecar",
                "node_id": NODE_ID,
                "stream": STREAM_KEY
            }
            logger.info(f"Health check: OK - Redis conectado, NODE_ID={NODE_ID}")
            return Response(response_data, status=status.HTTP_200_OK)
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"🔌 Redis no disponible en health check: {e}")
            response_data = {
                "status": "degraded",
                "redis": "disconnected",
                "node_id": NODE_ID
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Error en health check: {e}", exc_info=True)
            response_data = {
                "status": "error",
                "error": str(e),
                "node_id": NODE_ID
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
