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

import os
import logging
import json

from django.conf import settings
from django.utils.translation import gettext as _
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_200_OK,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN
)
from rest_framework.views import APIView

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.models import (
    Contacto, Campana, OpcionCalificacion, NombreCalificacion,
    CalificacionCliente, AgenteProfile
)

logger = logging.getLogger(__name__)

# Nombre de la calificación por defecto para Verloop (debe coincidir con disposition options de la campaña)
VERLOOP_CALIFICACION_NOMBRE = 'GESTION_BOT'


class VerloopWebhookView(APIView):
    """
    Vista que procesa webhooks de Verloop y los convierte en llamadas
    al endpoint de disposition interno.
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def _obtener_o_crear_calificacion_verloop(self, customer_id, campana_id=None):
        """
        Obtiene o crea la calificación "GESTION_BOT" para la campaña del contacto.
        Similar a como se maneja CALIFICACION_REAGENDA en el modelo Campana.
        
        Args:
            customer_id: ID del contacto
            campana_id: ID de la campaña (opcional, desde body o header X-Verloop-CampID)
            
        Returns:
            int: ID de la OpcionCalificacion "GESTION_BOT"
            
        Raises:
            Contacto.DoesNotExist: Si el contacto no existe
            Campana.DoesNotExist: Si no se encuentra una campaña para el contacto
        """
        # Obtener el contacto
        contacto = Contacto.objects.get(pk=customer_id)
        
        # Intentar obtener la campaña desde el body o header X-Verloop-CampID si está disponible
        # Esto es más preciso ya que un contacto puede estar en múltiples campañas
        campana = None
        
        if campana_id:
            try:
                campana_id_int = int(campana_id)
                # Verificar que la campaña pertenezca a la misma base de datos del contacto
                campana = contacto.bd_contacto.campanas.filter(
                    pk=campana_id_int
                ).first()
                
                if not campana:
                    logger.warning(
                        f'Campaign {campana_id_int} does not belong to '
                        f'contact {customer_id} database. Falling back to default campaign.'
                    )
            except (ValueError, TypeError):
                logger.warning(
                    f'Invalid campaign ID in X-Verloop-CampID: {campana_id}. '
                    f'Falling back to default campaign.'
                )
        
        # Si no se pudo obtener desde el header, obtener desde la base de datos del contacto
        if not campana:
            # Un contacto pertenece a una BaseDatosContacto, y una BaseDatosContacto
            # puede tener múltiples campañas. Buscamos una campaña activa.
            campanas = contacto.bd_contacto.campanas.filter(
                estado__in=[Campana.ESTADO_ACTIVA, Campana.ESTADO_PAUSADA]
            ).order_by('-id')
            
            if not campanas.exists():
                # Si no hay campañas activas, buscar cualquier campaña
                campanas = contacto.bd_contacto.campanas.all().order_by('-id')
            
            if not campanas.exists():
                raise Campana.DoesNotExist(
                    f'No campaign found for contact {customer_id}'
                )
            
            campana = campanas.first()
        
        # Crear o obtener el nombre de calificación "GESTION_BOT"
        nombre_calif, _ = NombreCalificacion.objects.get_or_create(
            nombre=VERLOOP_CALIFICACION_NOMBRE,
            defaults={'subcalificaciones': []}
        )
        
        # Crear o obtener la opción de calificación para esta campaña
        opcion, created = OpcionCalificacion.objects.get_or_create(
            campana=campana,
            nombre=VERLOOP_CALIFICACION_NOMBRE,
            defaults={
                'tipo': OpcionCalificacion.GESTION,
                'oculta': False,
                'positiva': False,
                'interaccion_crm': False
            }
        )
        
        if created:
            logger.info(
                f'Created "{VERLOOP_CALIFICACION_NOMBRE}" disposition option (ID: {opcion.id}) '
                f'for campaign {campana.id} (contact {customer_id})'
            )
        else:
            logger.debug(
                f'Using existing "{VERLOOP_CALIFICACION_NOMBRE}" disposition option (ID: {opcion.id}) '
                f'for campaign {campana.id} (contact {customer_id})'
            )
        
        return opcion.id

    def post(self, request):
        """
        Procesa el POST request de Verloop y crea una disposition.
        
        Extrae:
        - call_summary del body con prioridad: call_summary (raíz) > analysis.user_defined.call_summary
        - X-Verloop-customerID del body o del header
        - X-Verloop-CampID del body o del header (opcional)
        - X-Verloop-Disposition del body o del header (ID de la opción de calificación a usar)
        
        Luego crea la calificación directamente en la base de datos usando el ID de calificación
        especificado en X-Verloop-Disposition.
        """
        # Log detallado de todos los parámetros recibidos
        print("=" * 80)
        print("VERLOOP WEBHOOK - PARÁMETROS RECIBIDOS")
        print("=" * 80)
        
        # Información básica del request
        print(f"\n[REQUEST INFO]")
        print(f"  Method: {request.method}")
        print(f"  Path: {request.path}")
        print(f"  User: {getattr(request.user, 'username', 'anonymous')}")
        print(f"  IP: {request.META.get('REMOTE_ADDR', 'unknown')}")
        print(f"  Content-Type: {request.META.get('CONTENT_TYPE', 'unknown')}")
        
        # Headers completos
        print(f"\n[HEADERS]")
        for key, value in request.headers.items():
            print(f"  {key}: {value}")
        
        # Query parameters
        print(f"\n[QUERY PARAMETERS]")
        if request.GET:
            for key, value in request.GET.items():
                print(f"  {key}: {value}")
        else:
            print("  (ninguno)")
        
        # Body raw (si está disponible)
        print(f"\n[BODY RAW]")
        try:
            body_raw = request.body.decode('utf-8') if request.body else None
            if body_raw:
                print(f"  {body_raw[:1000]}")  # Primeros 1000 caracteres
                if len(body_raw) > 1000:
                    print(f"  ... (truncado, total: {len(body_raw)} caracteres)")
            else:
                print("  (vacío)")
        except Exception as e:
            print(f"  (error al leer body raw: {e})")
        
        # Body parseado
        print(f"\n[BODY PARSED]")
        try:
            body_data = request.data if hasattr(request, 'data') else json.loads(request.body) if request.body else {}
            print(json.dumps(body_data, indent=2, ensure_ascii=False, default=str))
        except Exception as e:
            print(f"  (error al parsear body: {e})")
        
        # META información relevante
        print(f"\n[META INFO RELEVANTE]")
        relevant_meta = ['HTTP_X_VERLOOP_CUSTOMERID', 'HTTP_X_VERLOOP_CAMPID', 
                        'HTTP_X_VERLOOP_DISPOSITION', 'HTTP_X_VERLOOP_UNIQUEID',
                        'HTTP_X_VERLOOP_CALLID', 'HTTP_AUTHORIZATION']
        for meta_key in relevant_meta:
            value = request.META.get(meta_key)
            if value:
                print(f"  {meta_key}: {value}")
        
        print("=" * 80)
        print()
        
        # También loguear con logger para que aparezca en los logs del sistema
        logger.info(
            f'Verloop webhook received - User: {getattr(request.user, "username", "anonymous")}, '
            f'IP: {request.META.get("REMOTE_ADDR", "unknown")}, '
            f'Path: {request.path}'
        )
        logger.info(f'Request headers: {dict(request.headers)}')
        if hasattr(request, 'data'):
            logger.info(f'Request body (parsed): {json.dumps(request.data, default=str)}')
        if request.body:
            try:
                logger.info(f'Request body (raw): {request.body.decode("utf-8")[:500]}')
            except:
                logger.info(f'Request body (raw): {request.body[:500]}')
        
        try:
            # Validar que el body sea JSON válido
            try:
                body_data = request.data if hasattr(request, 'data') else json.loads(request.body)
                logger.debug(f'Request body parsed successfully: {type(body_data)}')
                if isinstance(body_data, dict):
                    logger.debug(f'Request body keys: {list(body_data.keys())}')
                    logger.debug(f'X-Verloop-Disposition value: {body_data.get("X-Verloop-Disposition")} (type: {type(body_data.get("X-Verloop-Disposition"))})')
                    logger.debug(f'Full body_data: {json.dumps(body_data, default=str)[:500]}')  # Primeros 500 chars para no saturar logs
                else:
                    logger.warning(f'Request body is not a dict, got: {type(body_data)}')
            except json.JSONDecodeError as e:
                logger.error(f'Invalid JSON body received: {str(e)}')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Invalid JSON body'),
                        'errors': {'json': _('The request body must be valid JSON')}
                    },
                    status=HTTP_400_BAD_REQUEST
                )
            except (AttributeError, TypeError) as e:
                logger.error(f'Error accessing request body: {str(e)}')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Invalid request body'),
                        'errors': {'body': _('Unable to parse request body')}
                    },
                    status=HTTP_400_BAD_REQUEST
                )

            # Extraer call_summary del body
            # Prioridad: call_summary (raíz) > Call_Summary (raíz) > analysis.user_defined.call_summary > analysis.user_defined.Call_Summary
            # Nota: call_summary es opcional, puede estar vacío
            call_summary = None
            try:
                # Primero intentar obtener call_summary en la raíz del body
                call_summary_raw = body_data.get('call_summary')
                if call_summary_raw is not None:
                    # Convertir a string (usar is not None para permitir valores como 0 o "")
                    call_summary = str(call_summary_raw)
                    logger.debug(f'Extracted call_summary from root level in body: {call_summary}')
                
                # Si no se obtuvo, intentar Call_Summary (con mayúscula) en la raíz
                if not call_summary:
                    call_summary_raw = body_data.get('Call_Summary')
                    if call_summary_raw is not None:
                        call_summary = str(call_summary_raw)
                        logger.debug(f'Extracted Call_Summary from root level in body: {call_summary}')
                
                # Si no se obtuvo desde la raíz, intentar desde analysis.user_defined
                if not call_summary:
                    analysis = body_data.get('analysis', {})
                    if not isinstance(analysis, dict):
                        logger.warning(f'Expected analysis to be a dict, got {type(analysis)}')
                        analysis = {}
                    
                    user_defined = analysis.get('user_defined', {})
                    if not isinstance(user_defined, dict):
                        logger.warning(f'Expected user_defined to be a dict, got {type(user_defined)}')
                        user_defined = {}
                    
                    # Intentar call_summary (minúscula) primero
                    call_summary_raw = user_defined.get('call_summary')
                    if call_summary_raw is not None:
                        # Convertir a string (usar is not None para permitir valores como 0 o "")
                        call_summary = str(call_summary_raw)
                        logger.debug(f'Extracted call_summary from analysis.user_defined.call_summary: {call_summary}')
                    
                    # Si no se obtuvo, intentar Call_Summary (con mayúscula)
                    if not call_summary:
                        call_summary_raw = user_defined.get('Call_Summary')
                        if call_summary_raw is not None:
                            call_summary = str(call_summary_raw)
                            logger.debug(f'Extracted Call_Summary from analysis.user_defined.Call_Summary: {call_summary}')
                    
            except (AttributeError, KeyError, TypeError) as e:
                logger.warning(f'Error extracting call_summary from body: {str(e)}', exc_info=True)
                call_summary = None

            # call_summary es opcional, pero si está presente no debe ser "None" como string
            logger.debug(f'call_summary value after extraction: {call_summary} (type: {type(call_summary)})')
            
            # Si call_summary está presente, validar que no sea "None" como string
            if call_summary and isinstance(call_summary, str) and call_summary.strip().lower() == 'none':
                logger.error('call_summary is "None" string, which is invalid')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('call_summary cannot be "None"'),
                        'errors': {
                            'call_summary': _('The call_summary field cannot be "None"')
                        }
                    },
                    status=HTTP_400_BAD_REQUEST
                )
            
            # Asegurar que call_summary sea una cadena si está presente
            if call_summary and not isinstance(call_summary, str):
                call_summary = str(call_summary)
                logger.debug(f'Converted call_summary to string: {call_summary}')
            
            # Función auxiliar para construir las observaciones con todos los campos solicitados
            def construir_observaciones(body_data, call_summary):
                """
                Construye las observaciones concatenando:
                name + Call_Summary + PlanId + PlanCost + PlanUsage + companyName
                """
                partes = []
                
                # name
                name = body_data.get('name')
                if name:
                    partes.append(f"Nombre: {name}")
                
                # Call_Summary
                if call_summary:
                    partes.append(f"Resumen: {call_summary}")
                
                # PlanId
                plan_id = body_data.get('PlanId')
                if plan_id:
                    partes.append(f"Plan: {plan_id}")
                
                # PlanCost
                plan_cost = body_data.get('PlanCost')
                if plan_cost:
                    partes.append(f"Costo: {plan_cost}")
                
                # PlanUsage
                plan_usage = body_data.get('PlanUsage')
                if plan_usage:
                    partes.append(f"Uso: {plan_usage}")
                
                # companyName
                company_name = body_data.get('companyName')
                if company_name:
                    partes.append(f"Empresa: {company_name}")
                
                observaciones = " | ".join(partes)
                logger.debug(f'Observaciones construidas: {observaciones}')
                return observaciones

            # Extraer X-Verloop-customerID del body o del header (prioridad: body > header)
            customer_id = body_data.get('X-Verloop-customerID')
            if not customer_id:
                customer_id = request.headers.get('X-Verloop-customerID')
            
            if not customer_id:
                logger.error('X-Verloop-customerID is missing in both body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-customerID is required'),
                        'errors': {
                            'X-Verloop-customerID': _('The X-Verloop-customerID must be provided either in the request body or as a header')
                        }
                    },
                    status=HTTP_400_BAD_REQUEST
                )
            
            # Validar que customer_id sea un entero válido
            try:
                customer_id_int = int(customer_id)
                if customer_id_int <= 0:
                    raise ValueError('Customer ID must be positive')
                logger.debug(f'Validated customer_id: {customer_id_int}')
            except (ValueError, TypeError) as e:
                logger.error(f'Invalid customer_id format: {customer_id} - {str(e)}')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-customerID must be a valid positive integer'),
                        'errors': {
                            'X-Verloop-customerID': _('The customer ID must be a valid positive integer')
                        }
                    },
                    status=HTTP_400_BAD_REQUEST
                )

            # Extraer X-Verloop-Disposition del body o del header (prioridad: body > header)
            # Este campo contiene el ID de la opción de calificación a usar
            disposition_id = (
                body_data.get('X-Verloop-Disposition') or
                body_data.get('X_Verloop_Disposition') or
                body_data.get('x-verloop-disposition') or
                request.headers.get('X-Verloop-Disposition')
            )
            
            # Logging detallado para debug
            logger.info(f'[DEBUG] Extrayendo X-Verloop-Disposition')
            logger.info(f'[DEBUG] body_data type: {type(body_data)}')
            if isinstance(body_data, dict):
                logger.info(f'[DEBUG] body_data keys: {list(body_data.keys())}')
                logger.info(f'[DEBUG] body_data.get("X-Verloop-Disposition"): {body_data.get("X-Verloop-Disposition")} (type: {type(body_data.get("X-Verloop-Disposition"))})')
                logger.info(f'[DEBUG] body_data.get("X_Verloop_Disposition"): {body_data.get("X_Verloop_Disposition")}')
                logger.info(f'[DEBUG] body_data.get("x-verloop-disposition"): {body_data.get("x-verloop-disposition")}')
            logger.info(f'[DEBUG] request.headers.get("X-Verloop-Disposition"): {request.headers.get("X-Verloop-Disposition")}')
            logger.info(f'[DEBUG] disposition_id extraído: {disposition_id} (type: {type(disposition_id)})')
            
            if not disposition_id:
                logger.error('X-Verloop-Disposition is missing in both body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-Disposition is required'),
                        'errors': {
                            'X-Verloop-Disposition': _('The X-Verloop-Disposition (disposition option ID) must be provided either in the request body or as a header')
                        }
                    },
                    status=HTTP_400_BAD_REQUEST
                )
            
            # Validar que disposition_id sea un entero válido
            try:
                # Asegurar que sea string antes de convertir a int
                if isinstance(disposition_id, str):
                    disposition_id = disposition_id.strip()
                id_disposition_option = int(disposition_id)
                if id_disposition_option <= 0:
                    raise ValueError('Disposition option ID must be positive')
                logger.info(f'[DEBUG] Validated disposition option ID: {id_disposition_option} (from raw value: {disposition_id})')
            except (ValueError, TypeError) as e:
                logger.error(f'Invalid X-Verloop-Disposition format: {disposition_id} - {str(e)}')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-Disposition must be a valid positive integer'),
                        'errors': {
                            'X-Verloop-Disposition': _('The disposition option ID must be a valid positive integer')
                        }
                    },
                    status=HTTP_400_BAD_REQUEST
                )
            
            # Verificar que el contacto existe
            try:
                contacto = Contacto.objects.get(pk=customer_id_int)
            except Contacto.DoesNotExist:
                logger.error(f'Contact {customer_id_int} not found')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Contact not found'),
                        'errors': {
                            'contact': _('The contact with the provided ID does not exist')
                        }
                    },
                    status=HTTP_404_NOT_FOUND
                )
            
            # Verificar que la opción de calificación existe
            try:
                opcion_calificacion = OpcionCalificacion.objects.get(pk=id_disposition_option)
                logger.info(f'[DEBUG] Opción de calificación encontrada: ID={opcion_calificacion.id}, Nombre={opcion_calificacion.nombre}, Campaña={opcion_calificacion.campana.id}')
            except OpcionCalificacion.DoesNotExist:
                logger.error(f'Disposition option {id_disposition_option} not found')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Disposition option not found'),
                        'errors': {
                            'X-Verloop-Disposition': _('The disposition option with the provided ID does not exist')
                        }
                    },
                    status=HTTP_404_NOT_FOUND
                )
            
            # Verificar que el contacto pertenezca a la misma base de datos de la campaña de la opción de calificación
            if contacto.bd_contacto_id != opcion_calificacion.campana.bd_contacto_id:
                logger.error(
                    f'Contact {customer_id_int} does not belong to campaign '
                    f'{opcion_calificacion.campana.id} database'
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Contact does not belong to campaign database'),
                        'errors': {
                            'contact': _('The contact does not belong to the campaign database of the specified disposition option')
                        }
                    },
                    status=HTTP_400_BAD_REQUEST
                )
            
            logger.debug(f'Using disposition option ID: {id_disposition_option} ({opcion_calificacion.nombre})')

            # Extraer call_id una vez (body o headers) para calificación y para comando Redis
            # callid de negocio (4º parámetro) permite proseguir la transferencia por Pub/Sub
            call_id_verloop = (
                body_data.get('callid') or
                body_data.get('call_id') or
                body_data.get('X-Verloop-UniqueID') or
                body_data.get('X-Verloop-callID') or
                request.headers.get('X-Verloop-UniqueID') or
                request.headers.get('X-Verloop-callID')
            )
            if call_id_verloop:
                call_id_verloop = str(call_id_verloop).strip()

            try:
                # Verificar si ya existe una calificación para este contacto en esta campaña
                # Si existe, actualizarla en lugar de crear una nueva
                campana = opcion_calificacion.campana
                calificacion_existente = CalificacionCliente.objects.filter(
                    contacto=contacto,
                    opcion_calificacion__campana=campana
                ).first()
                
                if calificacion_existente:
                    logger.info(
                        f'Existing disposition found (ID: {calificacion_existente.id}) for contact {customer_id_int} '
                        f'in campaign {campana.id}. Updating instead of creating new one.'
                    )
                    # Actualizar la calificación existente
                    calificacion_existente.opcion_calificacion = opcion_calificacion
                    observaciones = construir_observaciones(body_data, call_summary)
                    calificacion_existente.observaciones = observaciones
                    if call_id_verloop:
                        calificacion_existente.callid = call_id_verloop
                    # No actualizar el agente ni la fecha para mantener el histórico
                    calificacion_existente.save()
                    calificacion = calificacion_existente
                    
                    # Verificar que se guardó correctamente
                    calificacion.refresh_from_db()
                    logger.info(f'[DEBUG] Calificación actualizada: ID={calificacion.id}, opcion_calificacion_id={calificacion.opcion_calificacion.id}, opcion_calificacion_nombre={calificacion.opcion_calificacion.nombre}')
                else:
                    # Crear la calificación directamente en lugar de hacer llamada HTTP
                    # Esto evita problemas de conexión y es más eficiente
                    logger.info(
                        f'Creating new disposition for contact {customer_id_int} '
                        f'with disposition option {id_disposition_option}'
                    )
                    
                    # Obtener el agente del usuario autenticado
                    # Si el usuario no es un agente, intentar obtener un agente de la campaña
                    try:
                        agente = request.user.agenteprofile
                    except AttributeError:
                        # Si el usuario no es un agente, obtener el primer agente de la campaña
                        logger.warning(
                            f'User {request.user.username} is not an agent. '
                            f'Attempting to get agent from campaign {opcion_calificacion.campana.id}'
                        )
                        agentes_campana = opcion_calificacion.campana.obtener_agentes()
                        if agentes_campana.exists():
                            agente = agentes_campana.first()
                            logger.info(f'Using agent {agente.id} from campaign')
                        else:
                            # Si no hay agentes en la campaña, buscar cualquier agente activo
                            agente = AgenteProfile.objects.filter(user__is_active=True).first()
                            if not agente:
                                raise ValueError('No agent available for creating disposition')
                            logger.warning(
                                f'No agents in campaign. Using first available agent: {agente.id}'
                            )
                    
                    # Crear la calificación directamente
                    # Construir observaciones con todos los campos solicitados
                    observaciones = construir_observaciones(body_data, call_summary)
                    
                    logger.info(f'[DEBUG] Creando calificación con: opcion_calificacion_id={opcion_calificacion.id}, contacto_id={contacto.id}, agente_id={agente.id}')
                    
                    calificacion = CalificacionCliente.objects.create(
                        contacto=contacto,
                        opcion_calificacion=opcion_calificacion,
                        observaciones=observaciones,
                        agente=agente,
                        es_calificacion_manual=False,
                        callid=call_id_verloop  # Para LlamadaResumenService y trazabilidad
                    )
                    
                    # Verificar que se guardó correctamente
                    calificacion.refresh_from_db()
                    logger.info(f'[DEBUG] Calificación creada: ID={calificacion.id}, opcion_calificacion_id={calificacion.opcion_calificacion.id}, opcion_calificacion_nombre={calificacion.opcion_calificacion.nombre}')
                    
                    if calificacion.opcion_calificacion.id != id_disposition_option:
                        logger.error(
                            f'[ERROR] DISCREPANCIA: Se solicitó opción {id_disposition_option} pero se creó con opción {calificacion.opcion_calificacion.id}'
                        )
                
                logger.info(
                    f'Disposition {"updated" if calificacion_existente else "created"} successfully for contact {customer_id_int}. '
                    f'Calificacion ID: {calificacion.id}, Agent: {calificacion.agente.id}'
                )
                
                # Preparar respuesta similar a la del serializer
                response_data = {
                    'id': calificacion.id,
                    'idContact': calificacion.contacto.id,
                    'idDispositionOption': calificacion.opcion_calificacion.id,
                    'comments': calificacion.observaciones,
                    'fecha': calificacion.fecha.isoformat() if calificacion.fecha else None
                }
                
                # --- Enviar comando por Redis Pub/Sub solo si la calificación es GESTION_BOT ---
                # El ACD espera action "voicebot_transfer_proceed" y call_id/callid (CommandDispatcher).
                if call_id_verloop and opcion_calificacion.nombre == VERLOOP_CALIFICACION_NOMBRE:
                    print(f"[Verloop] Enviando voicebot_transfer_proceed a Redis Pub/Sub, call_id={call_id_verloop}")
                    try:
                        from ominicontacto_app.services.redis.connection import create_redis_connection

                        # El ACD escucha acd:commands:global; el voicebot no conoce NODE_ID.
                        channel = "acd:commands:global"

                        r_client = create_redis_connection(db=0)

                        payload = {
                            "action": "voicebot_transfer_proceed",
                            "call_id": call_id_verloop,
                        }
                        message = json.dumps(payload)
                        r_client.publish(channel, message)

                        print(
                            f"[Verloop] ✅ Comando voicebot_transfer_proceed publicado en {channel} "
                            f"para call_id={call_id_verloop}"
                        )
                        logger.info(
                            f'✅ Comando voicebot_transfer_proceed enviado por Pub/Sub al canal {channel} '
                            f'para call_id={call_id_verloop}'
                        )
                    except Exception as e:
                        print(f"[Verloop] ⚠️ Error enviando voicebot_transfer_proceed por Pub/Sub: {e}")
                        logger.error(
                            f'⚠️ Error enviando comando voicebot_transfer_proceed por Pub/Sub: {e}',
                            exc_info=True
                        )
                elif call_id_verloop:
                    logger.info(
                        f'Disposition "{opcion_calificacion.nombre}" (ID {opcion_calificacion.id}) is not '
                        f'{VERLOOP_CALIFICACION_NOMBRE}. Skipping voicebot_transfer_proceed.'
                    )
                else:
                    print(
                        "[Verloop] ⚠️ No se encontró X-Verloop-UniqueID ni X-Verloop-callID. "
                        "No se enviará comando voicebot_transfer_proceed."
                    )
                    logger.warning(
                        '⚠️ No se encontró X-Verloop-UniqueID ni X-Verloop-callID en request. '
                        'No se enviará comando voicebot_transfer_proceed.'
                    )
                
                return Response(
                    data={
                        'status': 'SUCCESS',
                        'message': _('Disposition updated successfully') if calificacion_existente else _('Disposition created successfully'),
                        'data': response_data
                    },
                    status=HTTP_200_OK
                )

            except Contacto.DoesNotExist:
                logger.error(f'Contact {customer_id_int} not found')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Contact not found'),
                        'errors': {
                            'contact': _('The contact with the provided ID does not exist')
                        }
                    },
                    status=HTTP_404_NOT_FOUND
                )
            except OpcionCalificacion.DoesNotExist:
                logger.error(f'Disposition option {id_disposition_option} not found')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Disposition option not found'),
                        'errors': {
                            'idDispositionOption': _('The disposition option does not exist')
                        }
                    },
                    status=HTTP_404_NOT_FOUND
                )
            except ValueError as e:
                logger.error(
                    f'Value error creating disposition for contact {customer_id_int}: {e}',
                    exc_info=True
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': str(e),
                        'errors': {
                            'validation': str(e)
                        }
                    },
                    status=HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                logger.error(
                    f'Error creating disposition for contact {customer_id_int}: {e}',
                    exc_info=True
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Error creating disposition'),
                        'errors': {
                            'internal': _('An error occurred while creating the disposition')
                        }
                    },
                    status=HTTP_500_INTERNAL_SERVER_ERROR
                )

        except ValueError as e:
            # Errores de validación de tipos
            logger.error(f'Value error in VerloopWebhookView: {e}', exc_info=True)
            return Response(
                data={
                    'status': 'ERROR',
                    'message': _('Invalid value in request'),
                    'errors': {
                        'validation': str(e)
                    }
                },
                status=HTTP_400_BAD_REQUEST
            )
        
        except TypeError as e:
            # Errores de tipo
            logger.error(f'Type error in VerloopWebhookView: {e}', exc_info=True)
            return Response(
                data={
                    'status': 'ERROR',
                    'message': _('Type error in request processing'),
                    'errors': {
                        'type': str(e)
                    }
                },
                status=HTTP_400_BAD_REQUEST
            )
        
        except Exception as e:
            # Capturar cualquier otro error inesperado
            logger.exception(
                f'Unexpected error in VerloopWebhookView: {e}. '
                f'Request user: {getattr(request.user, "username", "unknown")}, '
                f'IP: {request.META.get("REMOTE_ADDR", "unknown")}'
            )
            return Response(
                data={
                    'status': 'ERROR',
                    'message': _('Unexpected error processing webhook'),
                    'errors': {
                        'internal': _('An unexpected error occurred. Please contact support if this persists.')
                    }
                },
                status=HTTP_500_INTERNAL_SERVER_ERROR
            )
