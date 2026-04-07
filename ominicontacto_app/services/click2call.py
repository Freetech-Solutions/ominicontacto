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

from __future__ import unicode_literals

from django.utils.translation import gettext as _
from django.conf import settings
import gearman
import json

import logging as _logging


logger = _logging.getLogger(__name__)


class Click2CallOriginator(object):
    AGENT = 'AGENT'
    EXTERNAL = 'EXTERNAL'
    
    # Nombre de la cola Gearman para click2call
    GEARMAN_QUEUE_NAME = getattr(settings, 'GEARMAN_QUEUE_CALL', 'acd-call-originator')
    
    def __init__(self):
        """Inicializa el cliente Gearman."""
        self.gearman_client = None
        self._init_gearman_client()
    
    def _init_gearman_client(self):
        """
        Inicializa el cliente Gearman usando la configuración de settings.
        
        Lee GEARMAN_JOB_SERVERS desde settings y crea un GearmanClient.
        Si no hay servidores configurados, gearman_client será None.
        """
        try:
            if not hasattr(settings, 'GEARMAN_JOB_SERVERS') or not settings.GEARMAN_JOB_SERVERS:
                logger.warning("GEARMAN_JOB_SERVERS no está configurado en settings")
                self.gearman_client = None
                return
            
            # GEARMAN_JOB_SERVERS es una lista de servidores (ej: ['gearman:4730'])
            self.gearman_client = gearman.GearmanClient(settings.GEARMAN_JOB_SERVERS)
            logger.debug(
                "Cliente Gearman inicializado con servidores: {0}".format(
                    settings.GEARMAN_JOB_SERVERS
                )
            )
        except Exception as e:
            logger.error(
                "Error inicializando cliente Gearman: {0}".format(e),
                exc_info=True
            )
            self.gearman_client = None
    
    def _submit_gearman_job(self, payload):
        """
        Envía un job a la cola Gearman de forma segura.
        
        Args:
            payload: Diccionario con los datos del job (será serializado a JSON)
            
        Returns:
            None si el job se envió exitosamente, mensaje de error en caso contrario
        """
        if not self.gearman_client:
            error = _("Cliente Gearman no está disponible. Verifique la configuración de GEARMAN_JOB_SERVERS")
            logger.error(error)
            return error
        
        try:
            # Serializar payload a JSON
            job_data = json.dumps(payload)
            
            # Enviar job a la cola en modo background (no bloqueante)
            job_request = self.gearman_client.submit_job(
                self.GEARMAN_QUEUE_NAME,
                job_data.encode('utf-8'),
                background=True,
                wait_until_complete=False
            )
            
            # Verificar que el job se envió correctamente
            # En modo background, submit_job retorna inmediatamente
            logger.info(
                "Job Gearman enviado exitosamente a cola '{0}': {1}".format(
                    self.GEARMAN_QUEUE_NAME, payload
                )
            )
            return None
            
        except Exception as e:
            error = _("Error al enviar job a Gearman: {0}".format(e))
            logger.exception(error)
            return error

    def call_originate(self, agente, campana_id, tipo_campana,
                       contacto_id, telefono,
                       click2call_type):
        """
        Realiza una llamada manual usando Gearman.
        
        Envía un job a la cola 'acd_call_originator' con metadata directo
        para que el ACD procese la llamada.
        """
        try:
            # Validar campos requeridos
            if not agente or not agente.id:
                error = _("Agente no válido")
                logger.error(error)
                return error
            
            if not campana_id:
                error = _("ID de campaña no válido")
                logger.error(error)
                return error
            
            if not telefono:
                error = _("Teléfono no válido")
                logger.error(error)
                return error
            
            # Construir payload con formato correcto esperado por el ACD
            payload = {
                "command": "dial",
                "number": telefono,
                "campaign_id": campana_id,
                "contact_id": contacto_id or 0,
                "agent_id": agente.id,
                "metadata": {
                    "call_type": "1",  # Manual call
                    "channel_type": "to_pstn"
                }
            }
            
            # Enviar job a Gearman
            error = self._submit_gearman_job(payload)
            if error:
                return error
            
            logger.info(
                "Click2Call encolado exitosamente - agente: {0}, campana: {1}, telefono: {2}".format(
                    agente.id, campana_id, telefono
                )
            )
            return None
            
        except Exception as e:
            error = _("Error inesperado al realizar click2call: {0} - contacto: {1}".format(e, telefono))
            logger.exception(error)
            return error

    def call_agent(self, agente_origen, agente_destino):
        """
        Realiza una llamada interna entre agentes usando Gearman.
        
        Envía un job a la cola 'acd_call_originator' con metadata para
        llamada agent2agent.
        """
        try:
            # Validar campos requeridos
            if not agente_origen or not agente_origen.id:
                error = _("Agente origen no válido")
                logger.error(error)
                return error
            
            if not agente_destino or not agente_destino.id:
                error = _("Agente destino no válido")
                logger.error(error)
                return error
            
            # Construir payload para llamada agent2agent con formato correcto
            # Para agent2agent, usamos el ID del agente destino como number
            # y campaign_id=0 para indicar que es fuera de campaña
            # call_type=5 es específico para llamadas agent2agent
            payload = {
                "command": "dial",
                "number": str(agente_destino.id),  # ID del agente destino como número
                "campaign_id": 0,  # Llamada fuera de campaña
                "contact_id": 0,
                "agent_id": agente_origen.id,
                "metadata": {
                    "call_type": "5",  # Agent2agent call
                    "channel_type": "to_agent"  # Llamada a agente
                }
            }
            
            # Enviar job a Gearman
            error = self._submit_gearman_job(payload)
            if error:
                return error
            
            logger.info(
                "Click2Call agent2agent encolado exitosamente - agente_origen: {0}, agente_destino: {1}".format(
                    agente_origen.id, agente_destino.id
                )
            )
            return None
            
        except Exception as e:
            error = _("Error inesperado al realizar llamada agent2agent: {0} - agente_origen: {1} - agente_destino: {2}".format(
                e, agente_origen.id, agente_destino.id))
            logger.exception(error)
            return error

    def call_external(self, agente, numero):
        """
        Realiza una llamada externa fuera de campaña usando Gearman.
        
        Envía un job a la cola 'acd_call_originator' con metadata para
        llamada externa sin campaña.
        """
        return self._call_without_campaign(agente, self.EXTERNAL, numero)

    def _call_without_campaign(self, agente, tipo_destino, numero):
        """
        Realiza llamadas fuera de campaña (internas entre agentes o externas)
        usando Gearman.
        
        Args:
            agente: Instancia del agente que realiza la llamada
            tipo_destino: Tipo de destino (AGENT o EXTERNAL)
            numero: Número de teléfono o ID de agente destino
        """
        try:
            # Validar campos requeridos
            if not agente or not agente.id:
                error = _("Agente no válido")
                logger.error(error)
                return error
            
            if not numero:
                error = _("Número de destino no válido")
                logger.error(error)
                return error
            
            # Determinar channel_type y call_type según el tipo de destino
            if tipo_destino == self.AGENT:
                # Llamada interna a agente
                channel_type = "to_agent"
                call_type = "5"  # Agent2agent call
            else:
                # Llamada externa a PSTN
                channel_type = "to_pstn"
                call_type = "1"  # Manual call
            
            # Construir payload para llamada fuera de campaña con formato correcto
            # campaign_id=0 indica que es fuera de campaña
            payload = {
                "command": "dial",
                "number": str(numero),
                "campaign_id": 0,  # Llamada fuera de campaña
                "contact_id": 0,
                "agent_id": agente.id,
                "metadata": {
                    "call_type": call_type,
                    "channel_type": channel_type
                }
            }
            
            # Enviar job a Gearman
            error = self._submit_gearman_job(payload)
            if error:
                return error
            
            tipo_llamada = "interna" if tipo_destino == self.AGENT else "externa"
            logger.info(
                "Click2Call {0} encolado exitosamente - agente: {1}, destino: {2}".format(
                    tipo_llamada, agente.id, numero
                )
            )
            return None
            
        except Exception as e:
            error = _("Error inesperado al realizar llamada fuera de campaña: {0} - tipo_destino: {1} - numero: {2}".format(
                e, tipo_destino, numero))
            logger.exception(error)
            return error
