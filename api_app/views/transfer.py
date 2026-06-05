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

from __future__ import unicode_literals

import os
import logging
import re
import json
import redis
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.authentication import SessionAuthentication

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.models import SupervisorProfile
from ominicontacto_app.services.redis.connection import create_redis_connection
from supervision_app.services.voicebot_calls import get_voicebot_call_from_hash
from reportes_app.agent_activity_dual_write import write_hold_activity_event_v2
from reportes_app.models import AgentActivityEventV2

logger = logging.getLogger(__name__)

# NODE_ID lógico de este nodo (DEBE matchear con el NODE_ID del acd.py)
NODE_ID = os.getenv('NODE_ID', 'acd01')
# Canal Pub/Sub para este nodo
CHANNEL_KEY = f"acd:commands:{NODE_ID}"
# Base para canales de broadcast o específicos
BASE_CHANNEL_KEY = "acd:commands"


def _get_redis_client():
    """
    Obtiene una conexión a Redis.
    """
    try:
        r_client = create_redis_connection(db=0)
        r_client.ping()
        return r_client
    except Exception as e:
        logger.error(f"Error conectando a Redis: {e}")
        return None


def _safe_int(value, default=0):
    """Convierte un valor a int de forma segura."""
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


def _resolve_channel(r_client, agent_id=None):
    """
    Resuelve el canal de Redis al cual enviar el comando.
    
    Si se proporciona agent_id, intenta buscar en qué nodo (NODE_ID)
    está logueado el agente y devuelve el canal específico de ese nodo.
    
    Si no se encuentra el agente o no tiene NODE_ID, devuelve el canal 
    configurado localmente (CHANNEL_KEY).
    """
    if not agent_id:
        return CHANNEL_KEY
    
    try:
        # Buscar NODE_ID del agente
        # El hash OML:AGENT:{id} contiene un campo NODE_ID si está logueado
        agent_key = f"OML:AGENT:{agent_id}"
        agent_node = r_client.hget(agent_key, "NODE_ID")
        
        if agent_node:
            # Normalizar a string por si acaso
            node_str = str(agent_node)
            target_channel = f"{BASE_CHANNEL_KEY}:{node_str}"
            logger.debug(f"🎯 Agente {agent_id} en nodo {node_str} -> Canal {target_channel}")
            return target_channel
        
    except Exception as e:
        logger.warning(f"⚠️ Error resolviendo nodo para agente {agent_id}: {e}")
            
    # Fallback al canal local si no se encuentra
    logger.debug(f"⚠️ Agente {agent_id} no tiene NODE_ID o error -> Fallback local {CHANNEL_KEY}")
    return CHANNEL_KEY


def _normalize_id(value):
    """
    Sanitiza IDs para evitar errores de búsqueda.
    Elimina caracteres no válidos (solo permite alfanuméricos, puntos, guiones, guiones bajos).
    Ej: 12345 -> "12345", " 1001 " -> "1001", None -> ""
    """
    if value is None:
        return ""
    cleaned = str(value).strip()
    # Eliminar caracteres no válidos (solo permitir alfanuméricos, puntos, guiones, guiones bajos)
    cleaned = re.sub(r'[^a-zA-Z0-9._-]', '', cleaned)
    return cleaned


def _get_campaign_cfg(r_client, camp_id):
    """Recupera la configuración de la campaña desde Redis."""
    data = r_client.hgetall(f"OML:CAMP:{camp_id}") or {}
    
    return {
        "strategy": data.get("STRATEGY", "random"),
        "queuetime": _safe_int(data.get("QUEUETIME"), 30),
        "ringtime": _safe_int(data.get("RINGTIME"), 15),
    }


def _get_sorted_agents(r_client, camp_id, strategy, exclude_set):
    """
    Obtiene agentes READY de la campaña ordenados según la estrategia.
    Retorna lista de dicts con 'id', 'sip', 'calls', 'last_change'.
    """
    import random
    
    # Obtener agentes de la campaña desde Redis
    key_members = f"OML:CAMPAIGN-AGENTS:{camp_id}"
    agent_ids = list(r_client.smembers(key_members))
    
    if not agent_ids:
        logger.debug(f"⚠️ No hay agentes asignados en {key_members}")
        return []
    
    # Filtrar agentes excluidos
    valid_query_ids = [aid for aid in agent_ids if aid not in exclude_set]
    
    if not valid_query_ids:
        return []
    
    # Usar pipeline para obtener múltiples valores eficientemente
    pipe = r_client.pipeline()
    for aid in valid_query_ids:
        key = f"OML:AGENT:{aid}"
        pipe.hget(key, "STATUS")
        pipe.hget(key, "SIP")
        pipe.hget(key, "sys_class")
        pipe.hget(key, "calls_count")
        pipe.hget(key, "last_state_change")
    
    results = pipe.execute()
    candidates = []
    step = 5
    
    for i, aid in enumerate(valid_query_ids):
        base = i * step
        status_val = results[base]
        sip_val = results[base + 1]
        sys_class_val = results[base + 2]
        calls_count = results[base + 3]
        last_change = results[base + 4]
        
        # Usar SIP o sys_class como fallback
        sip = sip_val if sip_val else sys_class_val
        
        if status_val == "READY" and sip:
            candidates.append({
                'id': aid,
                'sip': sip,
                'calls': _safe_int(calls_count, 0),
                'last_change': float(last_change) if last_change else 0.0
            })
    
    if not candidates:
        return []
    
    # Aplicar estrategia de ordenamiento
    if strategy == 'random' or strategy == 'ringall':
        random.shuffle(candidates)
    elif strategy == 'fewestcalls':
        candidates.sort(key=lambda x: x['calls'])
    elif strategy == 'leastrecent':
        candidates.sort(key=lambda x: x['last_change'])
    elif strategy == 'rrmemory':
        candidates.sort(key=lambda x: int(x['id']))
        last_agent_id = r_client.get(f"OML:CAMP:{camp_id}:RR_PTR")
        if last_agent_id:
            try:
                last_id = int(last_agent_id)
                rotated = []
                found = False
                for idx, cand in enumerate(candidates):
                    if int(cand['id']) > last_id:
                        rotated = candidates[idx:] + candidates[:idx]
                        found = True
                        break
                if found:
                    candidates = rotated
            except ValueError:
                pass
    
    return candidates


def _find_ready_agent_in_campaign(r_client, camp_id, exclude_agent_id=None):
    """
    Busca un agente READY en la campaña usando la estrategia configurada.
    Retorna el ID del agente seleccionado o None si no hay disponibles.
    """
    cfg = _get_campaign_cfg(r_client, camp_id)
    strategy = cfg.get("strategy", "random")
    
    exclude_set = set()
    if exclude_agent_id:
        exclude_set.add(str(exclude_agent_id))
    
    candidates = _get_sorted_agents(r_client, camp_id, strategy, exclude_set)
    
    if not candidates:
        return None
    
    # Retornar el primer candidato (ya está ordenado según la estrategia)
    return candidates[0]['id']


class TransferBlindAgentView(APIView):
    """
    Blind transfer hacia un agente lógico (target_agent_id).
    El endpoint SIP/PJSIP se resolverá del lado del ACD usando Redis
    (OML:AGENT:STATUS:<target_agent_id>).
    
    Espera:
      - call_id: OMLUNIQUEID de la llamada
      - target_agent_id: ID lógico del agente destino
      - agent_id: (opcional) ID del agente que inicia la transferencia
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            unique_id = data.get("call_id")
            target_agent_id = data.get("target_agent_id")
            agent_id = data.get("agent_id", "")

            if not unique_id or not target_agent_id:
                return Response(
                    {"error": "Faltan parámetros: call_id, target_agent_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Redis Pub/Sub espera un string (JSON)
            payload = {
                "action": "blind_to_agent",
                "call_id": str(unique_id),
                "target_agent_id": str(target_agent_id),
                "agent_id": str(agent_id)
            }

            # Resolver canal destino
            channel = _resolve_channel(r_client, agent_id)

            # Publicamos en el canal resuelto
            subscribers = r_client.publish(channel, json.dumps(payload))

            logger.info(
                f"📨 Blind transfer ({unique_id} -> agent {target_agent_id}) enviado a {channel}. "
                f"Agent initiator: {agent_id}. Subscribers: {subscribers}"
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": NODE_ID
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en blind-agent: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TransferBlindEndpointView(APIView):
    """
    Blind transfer hacia un endpoint SIP/PJSIP, para la llamada identificada
    por call_id (OMLUNIQUEID).
    Este API side-car SIEMPRE publica en el stream del NODE_ID local.
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            unique_id = data.get("call_id")
            endpoint = data.get("endpoint")
            agent_id = data.get("agent_id", "")

            if not unique_id or not endpoint:
                return Response(
                    {"error": "Faltan parámetros: call_id, endpoint"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Redis Pub/Sub espera un string (JSON)
            payload = {
                "action": "blind_to_endpoint",
                "call_id": str(unique_id),
                "endpoint": str(endpoint),
                "agent_id": str(agent_id)
            }

            # Resolver canal destino
            channel = _resolve_channel(r_client, agent_id)

            # Publicamos
            subscribers = r_client.publish(channel, json.dumps(payload))

            logger.info(
                f"📨 Transferencia {unique_id}->{endpoint} enviada a {channel}. "
                f"Agent initiator: {agent_id}. Subscribers: {subscribers}"
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": NODE_ID
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en blind-endpoint: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TransferBlindCampaignView(APIView):
    """
    Blind transfer hacia otra campaña (re-encolar).
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            unique_id = data.get("call_id")
            target_camp = data.get("target_campaign_id")
            agent_id = data.get("agent_id", "")

            if not unique_id or not target_camp:
                return Response(
                    {"error": "Faltan parámetros: call_id, target_campaign_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            payload = {
                "action": "blind_to_campaign",
                "call_id": str(unique_id),
                "target_campaign_id": str(target_camp),
                "agent_id": str(agent_id)
            }

            channel = _resolve_channel(r_client, agent_id)
            subscribers = r_client.publish(channel, json.dumps(payload))
            
            logger.info(
                f"📨 Transferencia a Campaña {target_camp} enviada a {channel} "
                f"para {unique_id}. Agent: {agent_id} Subscribers: {subscribers}"
            )

            return Response({
                "status": "queued",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": NODE_ID
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en blind-campaign: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TransferBlindCampaignAgentView(APIView):
    """
    Blind transfer a cualquier agente READY de la propia campaña.
    
    Busca automáticamente un agente disponible en la campaña de la llamada
    usando la estrategia configurada (random, fewestcalls, leastrecent, rrmemory).
    
    Si no se proporciona campaign_id, intentará obtenerlo de la llamada activa
    (requiere que la información esté disponible en Redis).
    
    Espera:
      - call_id: OMLUNIQUEID de la llamada (obligatorio)
      - campaign_id: ID de la campaña (opcional, se intentará obtener automáticamente)
      - agent_id: (opcional) ID del agente que inicia la transferencia (se excluirá de la búsqueda)
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            unique_id = _normalize_id(data.get("call_id"))
            campaign_id = _normalize_id(data.get("campaign_id"))
            agent_id = _normalize_id(data.get("agent_id"))

            if not unique_id:
                return Response(
                    {"error": "Falta parámetro obligatorio: call_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not campaign_id:
                return Response(
                    {"error": "campaign_id es requerido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Buscar un agente READY en la campaña
            exclude_agent_id = agent_id if agent_id else None
            target_agent_id = _find_ready_agent_in_campaign(
                r_client, 
                campaign_id, 
                exclude_agent_id=exclude_agent_id
            )

            if not target_agent_id:
                return Response(
                    {
                        "error": f"No hay agentes READY disponibles en la campaña {campaign_id}",
                        "campaign_id": campaign_id
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            # Normalizar target_agent_id para asegurar consistencia con Flask
            target_agent_id = _normalize_id(target_agent_id)

            payload = {
                "action": "blind_to_agent",
                "call_id": unique_id,
                "target_agent_id": target_agent_id,
                "agent_id": agent_id
            }

            channel = _resolve_channel(r_client, agent_id)
            subscribers = r_client.publish(channel, json.dumps(payload))

            logger.info(
                f"📨 Blind transfer a agente de campaña: {unique_id} -> agent {target_agent_id} "
                f"(campaña {campaign_id}). Enviado a {channel}. Subscribers: {subscribers}"
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": NODE_ID,
                "target_agent_id": target_agent_id,
                "campaign_id": campaign_id
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en blind-campaign-agent: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class Transfer3WayView(APIView):
    """
    Agrega un tercer participante (3-way conference) a la llamada.
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            unique_id = data.get("call_id")
            endpoint = data.get("endpoint")

            if not unique_id or not endpoint:
                return Response(
                    {"error": "Faltan parámetros: call_id, endpoint"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            payload = {
                "action": "add_third_party",
                "call_id": str(unique_id),
                "endpoint": str(endpoint)
            }

            subscribers = r_client.publish(CHANNEL_KEY, json.dumps(payload))
            logger.info(
                f"📨 3-Way {unique_id}+{endpoint} enviada. "
                f"Subscribers: {subscribers} Channel: {CHANNEL_KEY}"
            )

            return Response({
                "status": "queued",
                "subscribers": subscribers,
                "channel": CHANNEL_KEY,
                "node_id": NODE_ID
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en 3way: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class HangupLegView(APIView):
    """
    Endpoint para cortar una llamada con lógica dual:
    1. Si el ID es un CallID/UniqueID de negocio -> Termina la sesión completa (Cliente + Agente)
    2. Si el ID es un Channel ID específico -> Termina solo ese canal
    
    Parámetros (al menos uno es obligatorio):
    - call_id: ID único de la llamada (CallID de negocio o UniqueID técnico)
    - asterisk_id: ID técnico de Asterisk (alternativa a call_id)
    - unique_id: ID único de Asterisk (alternativa a call_id)
    - channel_id: ID específico del canal a cortar (modo precisión)
    
    La función determina automáticamente el modo según el ID proporcionado.
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            
            # Obtener el ID objetivo (puede venir como call_id, asterisk_id, unique_id o channel_id)
            target_id = _normalize_id(
                data.get("call_id") or 
                data.get("asterisk_id") or 
                data.get("unique_id") or 
                data.get("channel_id")
            )

            if not target_id:
                return Response(
                    {
                        "error": "Debe proporcionar al menos uno de los siguientes parámetros: call_id, asterisk_id, unique_id o channel_id"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Construir payload con la acción hangup_call (usada por _handle_hangup_call)
            payload = {
                "action": "hangup_call"
            }

            # Agregar el ID objetivo usando los campos que espera _handle_hangup_call
            # Prioridad: asterisk_id > unique_id > channel_id
            if data.get("asterisk_id"):
                payload["asterisk_id"] = target_id
            elif data.get("unique_id"):
                payload["unique_id"] = target_id
            elif data.get("channel_id"):
                payload["channel_id"] = target_id
            else:
                # Si solo viene call_id, lo enviamos como unique_id (compatibilidad)
                payload["unique_id"] = target_id

            subscribers = r_client.publish(CHANNEL_KEY, json.dumps(payload))
            
            logger.info(
                f"📨 Hangup call {target_id} enviada. "
                f"Subscribers: {subscribers} Channel: {CHANNEL_KEY}"
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": CHANNEL_KEY,
                "node_id": NODE_ID,
                "target_id": target_id,
                "mode": "auto"  # La función determinará automáticamente el modo (nuclear o precisión)
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en hangup-leg: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


def _decode_redis_value(value):
    """Decodifica valor de Redis (bytes o str) a str."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


class SpyChannelView(APIView):
    """
    Endpoint para iniciar channel spy (monitoreo de llamadas de agentes por supervisores).

    Publica en Redis Pub/Sub en el canal acd:commands:{NODE_ID}, donde NODE_ID
    se obtiene del hash OML:AGENT:{id_agente} del agente a espiar (debe estar ONCALL).

    El mensaje enviado al ACD sigue el formato:
    {"action": "spy", "supervisor_sip": "<sip_number>", "callid": "<callid>", "whisper": "none"}

    Parámetros:
    - supervisor_id (obligatorio): ID del supervisor que va a espiar (se resuelve a SIP para el mensaje)
    - agent_id (obligatorio): ID del agente a espiar (debe estar en llamada ONCALL)
    - whisper (opcional): Modo whisper ('none', 'out', 'both', 'in'). Default: 'none'
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            supervisor_id = data.get("supervisor_id")
            agent_id = data.get("agent_id")
            call_id_param = data.get("call_id")
            whisper = data.get("whisper", "none")

            # Inferir supervisor_id del usuario autenticado si no viene en el body
            if supervisor_id is None or str(supervisor_id).strip() == "":
                if request.user and getattr(request.user, "get_supervisor_profile", None):
                    try:
                        profile = request.user.get_supervisor_profile()
                        if profile is not None:
                            supervisor_id = getattr(profile, "id", None)
                    except Exception:
                        pass

            # Validar parámetros obligatorios
            if supervisor_id is None or str(supervisor_id).strip() == "":
                return Response(
                    {"error": "Falta parámetro obligatorio: supervisor_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not agent_id:
                return Response(
                    {"error": "Falta parámetro obligatorio: agent_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validar que whisper sea uno de los valores permitidos
            valid_whisper_modes = ['none', 'out', 'both', 'in']
            whisper_str = str(whisper).strip() if whisper else "none"
            if whisper_str not in valid_whisper_modes:
                return Response(
                    {
                        "error": f"whisper debe ser uno de: {', '.join(valid_whisper_modes)}",
                        "received": whisper
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Normalizar agent_id para consistencia
            agent_id_normalized = _normalize_id(agent_id)
            supervisor_id_str = str(supervisor_id).strip()

            # Resolver SIP del supervisor para incluir en el mensaje al ACD
            try:
                supervisor_pk = int(supervisor_id_str)
            except (ValueError, TypeError):
                return Response(
                    {"error": "supervisor_id debe ser un entero válido"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            supervisor = SupervisorProfile.objects.filter(id=supervisor_pk).first()
            if not supervisor:
                return Response(
                    {"error": "Supervisor no encontrado"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            supervisor_sip = str(supervisor.sip_extension)

            call_id = None
            node_id = None
            status_val = None

            if call_id_param:
                voicebot_call = get_voicebot_call_from_hash(
                    r_client, agent_id_normalized, call_id_param,
                )
                if not voicebot_call:
                    return Response(
                        {"error": "La llamada voicebot no está activa"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                call_id = voicebot_call.get('call_id')
                node_id = voicebot_call.get('node_id')
                status_val = voicebot_call.get('status')
            else:
                # Leer OML:AGENT:{agent_id} para obtener CALLID, NODE_ID y validar ONCALL
                agent_key = f"OML:AGENT:{agent_id_normalized}"
                agent_data = r_client.hgetall(agent_key)
                if not agent_data:
                    return Response(
                        {"error": "El agente no está en llamada"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Soporte para claves/valores en bytes (Redis sin decode_responses)
                def _get_agent_field(name):
                    raw = agent_data.get(name)
                    if raw is None and isinstance(name, str):
                        raw = agent_data.get(name.encode("utf-8"))
                    return _decode_redis_value(raw)

                status_val = _get_agent_field("STATUS")
                call_id = _get_agent_field("CALLID")
                node_id = _get_agent_field("NODE_ID")

            if call_id is not None:
                call_id = call_id.strip()
            if node_id is not None:
                node_id = node_id.strip()

            if not call_id:
                return Response(
                    {"error": "El agente no está en llamada"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not node_id:
                return Response(
                    {"error": "No hay llamada activa gestionada por el ACD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if status_val and status_val.upper() != "ONCALL":
                return Response(
                    {"error": "El agente no está en llamada"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Canal acd:commands:{NODE_ID}
            channel = f"{BASE_CHANNEL_KEY}:{node_id}"

            # Payload estándar esperado por el ACD CommandDispatcher: action, supervisor_sip, callid, whisper
            payload = {
                "action": "spy",
                "supervisor_sip": supervisor_sip,
                "callid": call_id,
                "whisper": whisper_str
            }

            subscribers = r_client.publish(channel, json.dumps(payload))

            logger.info(
                f"📨 Spy channel enviado: supervisor_sip={supervisor_sip}, callid={call_id}, "
                f"whisper={whisper_str}. Canal: {channel} Subscribers: {subscribers}"
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": node_id,
                "callid": call_id,
                "supervisor_id": supervisor_id_str,
                "supervisor_sip": supervisor_sip,
                "whisper": whisper_str
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en spy-channel: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VoicebotHangupView(APIView):
    """
    Cuelga una llamada voicebot específica resolviendo node_id desde
    OML:VOICEBOT-ACTIVE-CALLS:{agent_id}.
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            agent_id = data.get("agent_id")
            call_id = data.get("call_id")

            if not agent_id or not call_id:
                return Response(
                    {"error": "Faltan parámetros obligatorios: agent_id, call_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            agent_id_normalized = _normalize_id(agent_id)
            voicebot_call = get_voicebot_call_from_hash(
                r_client, agent_id_normalized, call_id,
            )
            if not voicebot_call:
                return Response(
                    {"error": "La llamada voicebot no está activa"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            resolved_call_id = voicebot_call.get('call_id')
            node_id = voicebot_call.get('node_id')
            status_val = voicebot_call.get('status')

            if not resolved_call_id or not node_id:
                return Response(
                    {"error": "No hay llamada activa gestionada por el ACD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if status_val and status_val.upper() != "ONCALL":
                return Response(
                    {"error": "La llamada voicebot no está activa"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            channel = f"{BASE_CHANNEL_KEY}:{node_id}"
            payload = {
                "action": "HANGUP",
                "callid": resolved_call_id,
            }
            subscribers = r_client.publish(channel, json.dumps(payload))

            logger.info(
                "Voicebot hangup enviado: agent_id=%s callid=%s canal=%s subscribers=%s",
                agent_id_normalized,
                resolved_call_id,
                channel,
                subscribers,
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": node_id,
                "callid": resolved_call_id,
                "agent_id": agent_id_normalized,
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en voicebot-hangup: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class HoldCallView(APIView):
    """
    Endpoint para hold/unhold de la llamada actual del agente.

    Registra el evento hold/unhold solo en AgentActivityEventV2 y publica comando
    hold/unhold en Redis (acd:commands:{NODE_ID}) para que el ACD inicie/detenga MOH en el bridge.
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            agente = request.user.get_agente_profile()
        except Exception:
            return Response(
                {"error": "Usuario sin perfil de agente"},
                status=status.HTTP_403_FORBIDDEN
            )

        data = getattr(request, 'data', None) or request.POST
        call_id = (data.get('callid') or data.get('call_id') or '').strip()
        if not call_id:
            agent_key = f"OML:AGENT:{agente.id}"
            call_id_raw = r_client.hget(agent_key, "CALLID")
            if call_id_raw:
                call_id = str(call_id_raw).strip()
        if not call_id:
            return Response(
                {"error": "Falta callid o call_id, o el agente no tiene llamada activa"},
                status=status.HTTP_400_BAD_REQUEST
            )

        last_hold = AgentActivityEventV2.objects.filter(
            agente_id=agente.id,
            metadata__callid=call_id,
            event_type__in=[
                AgentActivityEventV2.EventType.STATE_ON_HOLD,
                AgentActivityEventV2.EventType.STATE_OFF_HOLD,
            ],
        ).order_by('-ts').first()

        if last_hold and last_hold.event_type == AgentActivityEventV2.EventType.STATE_ON_HOLD:
            action = 'unhold'
            hold_event_type = AgentActivityEventV2.EventType.STATE_OFF_HOLD
        else:
            action = 'hold'
            hold_event_type = AgentActivityEventV2.EventType.STATE_ON_HOLD

        ts = timezone.now()
        write_hold_activity_event_v2(
            agente_id=agente.id,
            ts=ts,
            event_type=hold_event_type,
            callid=call_id,
        )

        channel = _resolve_channel(r_client, agent_id=agente.id)
        payload = {"action": action, "call_id": call_id}
        subscribers = r_client.publish(channel, json.dumps(payload))

        logger.info(
            f"Hold call: action={action} call_id={call_id} agente={agente.id} "
            f"channel={channel} subscribers={subscribers}"
        )

        return Response({
            "status": "queued",
            "subscribers": subscribers,
            "channel": channel,
            "node_id": NODE_ID,
        }, status=status.HTTP_202_ACCEPTED)


class ThreeWayConfView(APIView):
    """
    Endpoint para solicitar conferencia 3-way (añadir supervisor como tercer participante).

    Publica en Redis Pub/Sub en el canal acd:commands:{NODE_ID}, donde NODE_ID
    se obtiene del hash OML:AGENT:{id_agente} del agente en llamada (debe estar ONCALL).

    El mensaje enviado al ACD sigue el formato:
    {"action": "three_way_conf", "call_id": "<callid>", "sip_number": "<sip_supervisor>"}

    Parámetros:
    - supervisor_id (obligatorio): ID del supervisor que se une a la conferencia (se resuelve a SIP)
    - agent_id (obligatorio): ID del agente en llamada (debe estar ONCALL)
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            supervisor_id = data.get("supervisor_id")
            agent_id = data.get("agent_id")

            if supervisor_id is None or str(supervisor_id).strip() == "":
                if request.user and getattr(request.user, "get_supervisor_profile", None):
                    try:
                        profile = request.user.get_supervisor_profile()
                        if profile is not None:
                            supervisor_id = getattr(profile, "id", None)
                    except Exception:
                        pass

            if supervisor_id is None or str(supervisor_id).strip() == "":
                return Response(
                    {"error": "Falta parámetro obligatorio: supervisor_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not agent_id:
                return Response(
                    {"error": "Falta parámetro obligatorio: agent_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            agent_id_normalized = _normalize_id(agent_id)
            supervisor_id_str = str(supervisor_id).strip()

            try:
                supervisor_pk = int(supervisor_id_str)
            except (ValueError, TypeError):
                return Response(
                    {"error": "supervisor_id debe ser un entero válido"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            supervisor = SupervisorProfile.objects.filter(id=supervisor_pk).first()
            if not supervisor:
                return Response(
                    {"error": "Supervisor no encontrado"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            supervisor_sip = str(supervisor.sip_extension)

            agent_key = f"OML:AGENT:{agent_id_normalized}"
            agent_data = r_client.hgetall(agent_key)
            if not agent_data:
                return Response(
                    {"error": "El agente no está en llamada"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            def _get_agent_field(name):
                raw = agent_data.get(name)
                if raw is None and isinstance(name, str):
                    raw = agent_data.get(name.encode("utf-8"))
                return _decode_redis_value(raw)

            status_val = _get_agent_field("STATUS")
            call_id = _get_agent_field("CALLID")
            node_id = _get_agent_field("NODE_ID")

            if call_id is not None:
                call_id = call_id.strip()
            if node_id is not None:
                node_id = node_id.strip()

            if not call_id:
                return Response(
                    {"error": "El agente no está en llamada"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not node_id:
                return Response(
                    {"error": "No hay llamada activa gestionada por el ACD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if status_val and status_val.upper() != "ONCALL":
                return Response(
                    {"error": "El agente no está en llamada"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            channel = f"{BASE_CHANNEL_KEY}:{node_id}"
            payload = {
                "action": "three_way_conf",
                "call_id": call_id,
                "sip_number": supervisor_sip
            }

            subscribers = r_client.publish(channel, json.dumps(payload))

            logger.info(
                f"Three-way-conf enviado: call_id={call_id}, sip_number={supervisor_sip}, "
                f"canal={channel}, subscribers={subscribers}"
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": node_id,
                "call_id": call_id,
                "sip_number": supervisor_sip
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en three-way-conf: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TransferConsultStartView(APIView):
    """
    Inicia una transferencia consultativa.
    
    El agente A inicia una consulta con el agente B mientras el cliente queda en hold.
    El agente A y B hablan en un bridge privado, y luego el agente A puede confirmar
    o cancelar la transferencia.
    
    Espera:
      - call_id: OMLUNIQUEID de la llamada (obligatorio)
      - endpoint: Endpoint SIP/PJSIP del agente destino (opcional si se proporciona target_agent_id)
      - target_agent_id: ID lógico del agente destino (opcional si se proporciona endpoint)
      - agent_id: (opcional) ID del agente que inicia la transferencia
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            unique_id = _normalize_id(data.get("call_id"))
            endpoint = data.get("endpoint")
            target_agent_id = _normalize_id(data.get("target_agent_id"))
            agent_id = _normalize_id(data.get("agent_id", ""))

            if not unique_id:
                return Response(
                    {"error": "Falta parámetro obligatorio: call_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not endpoint and not target_agent_id:
                return Response(
                    {"error": "Debe proporcionar endpoint o target_agent_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Construir payload para Redis Stream
            payload = {
                "action": "consult_start",
                "call_id": unique_id,
                "agent_id": agent_id
            }

            # Agregar endpoint o target_agent_id según lo que se haya proporcionado
            if endpoint:
                payload["endpoint"] = str(endpoint)
            if target_agent_id:
                payload["target_agent_id"] = target_agent_id

            # Publicar comando en Redis Pub/Sub
            channel = _resolve_channel(r_client, agent_id)
            subscribers = r_client.publish(channel, json.dumps(payload))

            logger.info(
                f"📨 Consult start {unique_id} enviada a {channel}. "
                f"endpoint={endpoint}, target_agent_id={target_agent_id}, "
                f"Subscribers: {subscribers}"
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": NODE_ID
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en consult-start: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TransferConsultCompleteView(APIView):
    """
    Completa una transferencia consultativa (Agente A confirma).
    
    El agente A confirma la transferencia después de consultar con el agente B.
    El agente A se cuelga y el agente B queda con el cliente.
    
    Espera:
      - call_id: OMLUNIQUEID de la llamada (obligatorio)
      - agent_id: (opcional) ID del agente que confirma la transferencia
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            unique_id = _normalize_id(data.get("call_id"))
            agent_id = _normalize_id(data.get("agent_id", ""))

            if not unique_id:
                return Response(
                    {"error": "Falta parámetro obligatorio: call_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Construir payload para Redis Stream
            payload = {
                "action": "consult_complete",
                "call_id": unique_id,
                "agent_id": agent_id
            }

            # Publicar comando en Redis Pub/Sub
            channel = _resolve_channel(r_client, agent_id)
            subscribers = r_client.publish(channel, json.dumps(payload))

            logger.info(
                f"📨 Consult complete {unique_id} enviada a {channel}. "
                f"Subscribers: {subscribers}"
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": NODE_ID
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en consult-complete: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TransferConsultCancelView(APIView):
    """
    Cancela una transferencia consultativa (Agente A cancela).
    
    El agente A cancela la transferencia después de consultar con el agente B.
    El agente B se cuelga y el agente A vuelve con el cliente.
    
    Espera:
      - call_id: OMLUNIQUEID de la llamada (obligatorio)
      - agent_id: (opcional) ID del agente que cancela la transferencia
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def post(self, request):
        r_client = _get_redis_client()
        if not r_client:
            return Response(
                {"error": "Redis no inicializado"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            data = request.data
            unique_id = _normalize_id(data.get("call_id"))
            agent_id = _normalize_id(data.get("agent_id", ""))

            if not unique_id:
                return Response(
                    {"error": "Falta parámetro obligatorio: call_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Construir payload para Redis Stream
            payload = {
                "action": "consult_cancel",
                "call_id": unique_id,
                "agent_id": agent_id
            }

            # Publicar comando en Redis Pub/Sub
            channel = _resolve_channel(r_client, agent_id)
            subscribers = r_client.publish(channel, json.dumps(payload))

            logger.info(
                f"📨 Consult cancel {unique_id} enviada a {channel}. "
                f"Subscribers: {subscribers}"
            )

            return Response({
                "status": "queued",
                "message": "Comando recibido",
                "subscribers": subscribers,
                "channel": channel,
                "node_id": NODE_ID
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"API Error en consult-cancel: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

