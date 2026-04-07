# -*- coding: utf-8 -*-
# Copyright (C) 2026 Freetech Solutions

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

import json
import logging
from time import time

from django.utils.translation import gettext as _

from ominicontacto_app.services.asterisk.asterisk_ami import AMIManagerConnector
from ominicontacto_app.services.asterisk.agent_activity import AgentActivityAmiManager
from ominicontacto_app.services.agent.presence import AgentPresenceManager
from ominicontacto_app.services.redis.connection import create_redis_connection
from ominicontacto_app.models import AgenteProfile

logger = logging.getLogger(__name__)

LONGITUD_MINIMA_HEADERS = 4

# Canal base Redis Pub/Sub para comandos ACD (acd:commands:{NODE_ID})
BASE_CHANNEL_KEY = "acd:commands"


class SupervisorActivityAmiManager(object):

    EXTENSIONES = ["AGENTLOGOUT", "AGENTUNPAUSE", "AGENTPAUSE", "CHANTAKECALL",
                   "CHANSPYWISHPER", "CHANSPY", "CHANCONFER"]

    def __init__(self, *args, **kwargs):
        self.manager = AMIManagerConnector()
        self.agent_activity = AgentActivityAmiManager()
        self.presence_manager = AgentPresenceManager()

    def _originate_call(self, originate_data):
        # Django no conecta a Asterisk; originate para otras extensiones deshabilitado
        logger.debug(
            "_originate_call: omitido (sin conexión AMI); usar Redis/ACD para acciones"
        )
        return None, True

    def _publish_spy_command(self, supervisor, agente_profile, whisper_mode):
        """
        Publica un comando de spy en Redis Pub/Sub para ser procesado por acd.py.
        Obtiene CALLID y NODE_ID de OML:AGENT:{agente_profile.id} (agente debe estar ONCALL).

        Args:
            supervisor: Objeto SupervisorProfile con sip_extension
            agente_profile: Objeto AgenteProfile con id
            whisper_mode: Modo whisper ('none' para CHANSPY, 'both' para CHANSPYWISHPER)

        Returns:
            None si tiene éxito, mensaje de error si falla
        """
        redis_client = create_redis_connection()
        if not redis_client:
            logger.error("Error: Redis no disponible para publicar comando spy")
            return _("Error: Redis no disponible")

        agent_key = "OML:AGENT:{}".format(agente_profile.id)
        agent_data = redis_client.hgetall(agent_key)
        if not agent_data:
            logger.warning("spy: agente %s sin datos en Redis", agente_profile.id)
            return _("El agente no está en llamada")

        call_id = agent_data.get(b"CALLID") or agent_data.get("CALLID")
        node_id = agent_data.get(b"NODE_ID") or agent_data.get("NODE_ID")
        if call_id is not None:
            call_id = call_id.decode("utf-8") if isinstance(call_id, bytes) else str(call_id)
        if node_id is not None:
            node_id = node_id.decode("utf-8") if isinstance(node_id, bytes) else str(node_id)

        if not call_id or not str(call_id).strip():
            logger.warning("spy: agente %s sin CALLID", agente_profile.id)
            return _("El agente no está en llamada")
        if not node_id or not str(node_id).strip():
            logger.warning("spy: agente %s sin NODE_ID", agente_profile.id)
            return _("No hay llamada activa gestionada por el ACD")

        channel = "{}:{}".format(BASE_CHANNEL_KEY, node_id.strip())
        payload = {
            "action": "spy",
            "supervisor_sip": str(supervisor.sip_extension),
            "callid": call_id.strip(),
            "whisper": whisper_mode
        }
        try:
            redis_client.publish(channel, json.dumps(payload))
            logger.info(
                "Spy command published: supervisor_sip=%s, callid=%s, whisper=%s, channel=%s",
                supervisor.sip_extension, call_id, whisper_mode, channel,
            )
            return None
        except Exception as e:
            logger.error("Error publishing spy command to Redis Pub/Sub: %s", e)
            return _("Error al publicar comando en Redis")

    def _publish_three_way_command(self, supervisor, agente_profile):
        """
        Publica un comando three_way_add en Redis Pub/Sub para conferencia 3-way.
        Obtiene CALLID y NODE_ID de OML:AGENT:{agente_profile.id} (agente ONCALL).
        El tercero en la conferencia es el supervisor (debe tener perfil de agente).

        Returns:
            None si tiene éxito, mensaje de error traducido si falla.
        """
        redis_client = create_redis_connection()
        if not redis_client:
            logger.error("Error: Redis no disponible para publicar comando three_way_add")
            return _("Error: Redis no disponible")

        agent_key = "OML:AGENT:{}".format(agente_profile.id)
        agent_data = redis_client.hgetall(agent_key)
        if not agent_data:
            logger.warning("three_way_add: agente %s sin datos en Redis", agente_profile.id)
            return _("El agente no está en llamada")

        call_id = agent_data.get(b"CALLID") or agent_data.get("CALLID")
        node_id = agent_data.get(b"NODE_ID") or agent_data.get("NODE_ID")
        if call_id is not None:
            call_id = call_id.decode("utf-8") if isinstance(call_id, bytes) else str(call_id)
        if node_id is not None:
            node_id = node_id.decode("utf-8") if isinstance(node_id, bytes) else str(node_id)

        if not call_id or not str(call_id).strip():
            logger.warning("three_way_add: agente %s sin CALLID", agente_profile.id)
            return _("El agente no está en llamada")
        if not node_id or not str(node_id).strip():
            logger.warning("three_way_add: agente %s sin NODE_ID", agente_profile.id)
            return _("No hay llamada activa gestionada por el ACD")

        supervisor_agente = None
        if getattr(supervisor, "user", None):
            supervisor_agente = supervisor.user.get_agente_profile()
        if not supervisor_agente:
            logger.warning("three_way_add: supervisor sin perfil de agente")
            return _("El supervisor debe tener perfil de agente para realizar conferencia de tres vías")

        channel = "acd:commands:{}".format(node_id.strip())
        payload = {
            "action": "three_way_add",
            "call_id": call_id.strip(),
            "agent_id": str(supervisor_agente.id),
        }
        try:
            redis_client.publish(channel, json.dumps(payload))
            logger.info(
                "Three-way command published: call_id=%s, agent_id=%s, channel=%s",
                call_id, supervisor_agente.id, channel,
            )
            return None
        except Exception as e:
            logger.error("Error publishing three_way_add command to Redis: %s", e)
            return _("Error al publicar comando en Redis")

    def _publish_take_call_command(self, supervisor, agente_profile):
        """
        Publica un comando take_call en Redis Pub/Sub para ser procesado por el ACD (ARI).
        Obtiene CALLID y NODE_ID de OML:AGENT:{agente_profile.id} (agente debe estar ONCALL).
        El supervisor toma la llamada del agente (originate por ARI + bridge + hangup agente).

        Returns:
            None si tiene éxito, mensaje de error traducido si falla.
        """
        redis_client = create_redis_connection()
        if not redis_client:
            logger.error("Error: Redis no disponible para publicar comando take_call")
            return _("Error: Redis no disponible")

        agent_key = "OML:AGENT:{}".format(agente_profile.id)
        agent_data = redis_client.hgetall(agent_key)
        if not agent_data:
            logger.warning("take_call: agente %s sin datos en Redis", agente_profile.id)
            return _("El agente no está en llamada")

        call_id = agent_data.get(b"CALLID") or agent_data.get("CALLID")
        node_id = agent_data.get(b"NODE_ID") or agent_data.get("NODE_ID")
        if call_id is not None:
            call_id = call_id.decode("utf-8") if isinstance(call_id, bytes) else str(call_id)
        if node_id is not None:
            node_id = node_id.decode("utf-8") if isinstance(node_id, bytes) else str(node_id)

        if not call_id or not str(call_id).strip():
            logger.warning("take_call: agente %s sin CALLID", agente_profile.id)
            return _("El agente no está en llamada")
        if not node_id or not str(node_id).strip():
            logger.warning("take_call: agente %s sin NODE_ID", agente_profile.id)
            return _("No hay llamada activa gestionada por el ACD")

        channel = "{}:{}".format(BASE_CHANNEL_KEY, node_id.strip())
        payload = {
            "action": "take_call",
            "callid": call_id.strip(),
            "supervisor_sip": str(supervisor.sip_extension),
        }
        try:
            redis_client.publish(channel, json.dumps(payload))
            logger.info(
                "Take call command published: supervisor_sip=%s, callid=%s, channel=%s",
                supervisor.sip_extension, call_id, channel,
            )
            return None
        except Exception as e:
            logger.error("Error publishing take_call command to Redis: %s", e)
            return _("Error al publicar comando en Redis")

    def obtener_agentes_activos(self):
        agentes_activos = []
        redis_connection = create_redis_connection()
        # TODO: cambiar a usar el metodo 'scan' que es mas eficiente con datos muy grandes
        # y realiza una especie de paginación
        keys_agentes = redis_connection.keys('OML:AGENT:*')
        agentes_activos = []
        for key in keys_agentes:
            agente_info = redis_connection.hgetall(key)
            status = agente_info.get('STATUS', '')
            id_agente = key.split(':')[-1]
            if status != '' and len(agente_info) >= LONGITUD_MINIMA_HEADERS:
                agente_info['nombre'] = agente_info['NAME']
                agente_info['status'] = status
                agente_info['sip'] = agente_info['SIP']
                agente_info['pause_id'] = agente_info.get('PAUSE_ID', '')
                agente_info['campana_llamada'] = agente_info.get('CAMPAIGN', '')
                agente_info['contacto'] = agente_info.get('CONTACT_NUMBER', '')
                tiempo_actual = int(time())
                tiempo_estado = tiempo_actual - int(agente_info['TIMESTAMP'])
                agente_info['tiempo'] = tiempo_estado
                del agente_info['NAME']
                del agente_info['STATUS']
                del agente_info['TIMESTAMP']
                del agente_info['SIP']
                agente_info['id'] = int(id_agente)
                agentes_activos.append(agente_info)
        return agentes_activos

    def ejecutar_accion_sobre_agente(self, supervisor, agente_profile, exten):
        if exten not in self.EXTENSIONES:
            return _("La acción indicada no existe")
        channel = "PJSIP/{0}".format(supervisor.sip_extension)
        channel_vars = {'OMLAGENTID': str(agente_profile.id), }
        originate_data = [channel, exten, 'oml-sup-actions', channel_vars]
        # Genero la llamada via originate por AMI
        if exten == "AGENTLOGOUT":
            agente_profile.force_logout()
            self.agent_activity.logout_agent(agente_profile, manage_connection=True)
            # TODO: Todo el logout deberia manejarse desde AgentPresenceManager.logout
            self.presence_manager.logout(agente_profile)
        elif exten == "AGENTPAUSE":
            self.agent_activity.pause_agent(
                agente_profile, '00', manage_connection=True, supervisor=True)
            # TODO: Todo el proceso de pausa deberia manejarse desde AgentPresenceManager.pause
            presence_manager = AgentPresenceManager()
            presence_manager.pause(agente_profile, '00')
        elif exten == "AGENTUNPAUSE":
            self.agent_activity.unpause_agent(
                agente_profile, '00', manage_connection=True, supervisor=True)
        elif exten == "CHANSPY":
            # Publicar comando spy en Redis Pub/Sub
            return self._publish_spy_command(supervisor, agente_profile, whisper_mode="none")
        elif exten == "CHANSPYWISHPER":
            # Publicar comando spy en Redis Pub/Sub
            return self._publish_spy_command(supervisor, agente_profile, whisper_mode="both")
        elif exten == "CHANCONFER":
            # Nueva arquitectura: Publicar comando three_way_add en Redis Pub/Sub
            return self._publish_three_way_command(supervisor, agente_profile)
        elif exten == "CHANTAKECALL":
            # Tomar llamada: publicar comando take_call en Redis para que el ACD use ARI
            return self._publish_take_call_command(supervisor, agente_profile)
        else:
            # Otras extensiones mantienen el flujo AMI original
            self._originate_call(originate_data)

    def escribir_estado_agentes_unavailable(self):
        """Sin conexión AMI; ya no se consulta queue show en Asterisk."""
        pass
