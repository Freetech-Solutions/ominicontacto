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

import json
import logging

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
)
from rest_framework.views import APIView

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.models import (
    Contacto, OpcionCalificacion, CalificacionCliente, AgenteProfile
)

logger = logging.getLogger(__name__)

# Nombre de la calificación que dispara el comando voicebot_transfer_proceed
# hacia el ACD. Se puede sobreescribir desde settings (VERLOOP_CALIFICACION_NOMBRE).
DEFAULT_VERLOOP_CALIFICACION_NOMBRE = 'GESTION_BOT'

# Canal Redis donde el CommandDispatcher del ACD escucha comandos globales.
ACD_GLOBAL_COMMANDS_CHANNEL = 'acd:commands:global'


def _calificacion_nombre_voicebot():
    """Nombre de OpcionCalificacion que indica fin de gestión del voicebot."""
    return getattr(
        settings, 'VERLOOP_CALIFICACION_NOMBRE', DEFAULT_VERLOOP_CALIFICACION_NOMBRE
    )


def _sanitize_headers_for_log(headers):
    """Devuelve un dict de headers con Authorization enmascarado para logs."""
    safe = {}
    for key, value in headers.items():
        if key.lower() == 'authorization':
            safe[key] = '***'
        else:
            safe[key] = value
    return safe


class VerloopWebhookView(APIView):
    """
    Vista que procesa webhooks de Verloop y crea/actualiza la calificación
    del contacto en la campaña correspondiente. Si la opción de calificación
    aplicada coincide con la configurada para fin de gestión del bot, además
    publica un comando voicebot_transfer_proceed en Redis para que el ACD
    pueda continuar la transferencia que quedó pendiente tras el REFER del
    voicebot.
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    @staticmethod
    def _extract_call_summary(body_data):
        """Extrae call_summary buscando en raíz y luego en analysis.user_defined.

        Acepta tanto `call_summary` como `Call_Summary`. Si el valor es la
        cadena literal "None" se considera inválido y se devuelve un sentinel.
        """
        candidate_keys = ('call_summary', 'Call_Summary')

        def _read(container):
            if not isinstance(container, dict):
                return None
            for k in candidate_keys:
                value = container.get(k)
                if value is not None:
                    return str(value)
            return None

        call_summary = _read(body_data)
        if not call_summary:
            analysis = body_data.get('analysis') if isinstance(body_data, dict) else None
            user_defined = analysis.get('user_defined') if isinstance(analysis, dict) else None
            call_summary = _read(user_defined)

        return call_summary

    @staticmethod
    def _construir_observaciones(body_data, call_summary):
        """
        Construye las observaciones concatenando:
        name + Call_Summary + PlanId + PlanCost + PlanUsage + companyName
        """
        partes = []
        if not isinstance(body_data, dict):
            body_data = {}

        campos = [
            ('Nombre', body_data.get('name')),
            ('Resumen', call_summary),
            ('Plan', body_data.get('PlanId')),
            ('Costo', body_data.get('PlanCost')),
            ('Uso', body_data.get('PlanUsage')),
            ('Empresa', body_data.get('companyName')),
        ]
        for etiqueta, valor in campos:
            if valor:
                partes.append(f"{etiqueta}: {valor}")
        return " | ".join(partes)

    @staticmethod
    def _resolver_agente(request, campana):
        """
        Selecciona el agente a asociar a la calificación, en este orden:
          1. request.user.agenteprofile (si el usuario autenticado es agente).
          2. settings.VERLOOP_BOT_AGENT_USERNAME → agente con ese username.
          3. Primer agente de la campaña.
          4. Primer AgenteProfile activo del sistema.
        Lanza ValueError si no se encuentra ninguno.
        """
        try:
            return request.user.agenteprofile
        except AttributeError:
            pass

        bot_username = getattr(settings, 'VERLOOP_BOT_AGENT_USERNAME', None)
        if bot_username:
            agente = AgenteProfile.objects.filter(
                user__username=bot_username, user__is_active=True
            ).first()
            if agente:
                logger.info(
                    'Verloop: usando agente BOT configurado "%s" (id=%s)',
                    bot_username, agente.id,
                )
                return agente
            logger.warning(
                'Verloop: VERLOOP_BOT_AGENT_USERNAME="%s" no corresponde a un agente activo',
                bot_username,
            )

        agentes_campana = campana.obtener_agentes()
        if agentes_campana.exists():
            agente = agentes_campana.first()
            logger.info(
                'Verloop: usando primer agente de la campaña %s (id=%s)',
                campana.id, agente.id,
            )
            return agente

        agente = AgenteProfile.objects.filter(user__is_active=True).first()
        if agente:
            logger.warning(
                'Verloop: sin agentes en la campaña %s, usando primer agente activo (id=%s)',
                campana.id, agente.id,
            )
            return agente

        raise ValueError('No agent available for creating disposition')

    @staticmethod
    def _publicar_voicebot_transfer_proceed(call_id):
        """Publica el comando voicebot_transfer_proceed en Redis para el ACD."""
        try:
            from ominicontacto_app.services.redis.connection import create_redis_connection

            r_client = create_redis_connection(db=0)
            payload = {
                'action': 'voicebot_transfer_proceed',
                'call_id': call_id,
            }
            r_client.publish(ACD_GLOBAL_COMMANDS_CHANNEL, json.dumps(payload))
            logger.info(
                'Verloop: comando voicebot_transfer_proceed publicado en %s para call_id=%s',
                ACD_GLOBAL_COMMANDS_CHANNEL, call_id,
            )
        except Exception:
            logger.exception(
                'Verloop: error publicando voicebot_transfer_proceed para call_id=%s',
                call_id,
            )

    def post(self, request):
        """
        Procesa el POST request de Verloop y crea/actualiza una calificación.

        Acepta en body JSON o en headers (prioridad body > header):
          - X-Verloop-customerID  (obligatorio)
          - X-Verloop-Disposition (obligatorio, id de OpcionCalificacion)
          - call_id / callid / X-Verloop-UniqueID / X-Verloop-callID (opcional)
          - call_summary / Call_Summary (raíz o en analysis.user_defined)
          - name, PlanId, PlanCost, PlanUsage, companyName (para observaciones)
        """
        logger.info(
            'Verloop webhook received - user=%s ip=%s',
            getattr(request.user, 'username', 'anonymous'),
            request.META.get('REMOTE_ADDR', 'unknown'),
        )
        debug_payload = bool(getattr(settings, 'VERLOOP_DEBUG_PAYLOAD', False))
        if debug_payload:
            logger.info(
                'Verloop DEBUG headers=%s',
                _sanitize_headers_for_log(request.headers),
            )
        elif logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                'Verloop webhook headers=%s',
                _sanitize_headers_for_log(request.headers),
            )

        try:
            try:
                body_data = request.data if hasattr(request, 'data') else json.loads(request.body)
            except json.JSONDecodeError as e:
                logger.error('Verloop: invalid JSON body received: %s', e)
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Invalid JSON body'),
                        'errors': {'json': _('The request body must be valid JSON')},
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            except (AttributeError, TypeError) as e:
                logger.error('Verloop: error accessing request body: %s', e)
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Invalid request body'),
                        'errors': {'body': _('Unable to parse request body')},
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            if not isinstance(body_data, dict):
                logger.warning('Verloop: request body is not a dict, got %s', type(body_data))
                body_data = {}

            if debug_payload:
                try:
                    body_dump = json.dumps(
                        body_data, indent=2, ensure_ascii=False, default=str,
                    )
                except (TypeError, ValueError):
                    body_dump = repr(body_data)
                logger.info('Verloop DEBUG body completo:\n%s', body_dump)
            elif logger.isEnabledFor(logging.DEBUG):
                logger.debug('Verloop body keys: %s', list(body_data.keys()))

            call_summary = self._extract_call_summary(body_data)
            if (
                call_summary
                and isinstance(call_summary, str)
                and call_summary.strip().lower() == 'none'
            ):
                logger.error('Verloop: call_summary is "None" string, which is invalid')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('call_summary cannot be "None"'),
                        'errors': {
                            'call_summary': _('The call_summary field cannot be "None"')
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            customer_id = (
                body_data.get('X-Verloop-customerID')
                or request.headers.get('X-Verloop-customerID')
            )
            if not customer_id:
                logger.error('Verloop: X-Verloop-customerID is missing in body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-customerID is required'),
                        'errors': {
                            'X-Verloop-customerID': _(
                                'The X-Verloop-customerID must be provided either in the '
                                'request body or as a header'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            try:
                customer_id_int = int(customer_id)
                if customer_id_int <= 0:
                    raise ValueError('Customer ID must be positive')
            except (ValueError, TypeError) as e:
                logger.error('Verloop: invalid customer_id format: %s - %s', customer_id, e)
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-customerID must be a valid positive integer'),
                        'errors': {
                            'X-Verloop-customerID': _(
                                'The customer ID must be a valid positive integer'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            disposition_id = (
                body_data.get('X-Verloop-Disposition')
                or body_data.get('X_Verloop_Disposition')
                or body_data.get('x-verloop-disposition')
                or request.headers.get('X-Verloop-Disposition')
            )
            if not disposition_id:
                logger.error('Verloop: X-Verloop-Disposition is missing in body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-Disposition is required'),
                        'errors': {
                            'X-Verloop-Disposition': _(
                                'The X-Verloop-Disposition (disposition option ID) must be '
                                'provided either in the request body or as a header'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            try:
                if isinstance(disposition_id, str):
                    disposition_id = disposition_id.strip()
                id_disposition_option = int(disposition_id)
                if id_disposition_option <= 0:
                    raise ValueError('Disposition option ID must be positive')
            except (ValueError, TypeError) as e:
                logger.error(
                    'Verloop: invalid X-Verloop-Disposition format: %s - %s',
                    disposition_id, e,
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-Disposition must be a valid positive integer'),
                        'errors': {
                            'X-Verloop-Disposition': _(
                                'The disposition option ID must be a valid positive integer'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            try:
                contacto = Contacto.objects.get(pk=customer_id_int)
            except Contacto.DoesNotExist:
                logger.error('Verloop: contact %s not found', customer_id_int)
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Contact not found'),
                        'errors': {
                            'contact': _('The contact with the provided ID does not exist')
                        },
                    },
                    status=HTTP_404_NOT_FOUND,
                )

            try:
                opcion_calificacion = OpcionCalificacion.objects.select_related(
                    'campana'
                ).get(pk=id_disposition_option)
            except OpcionCalificacion.DoesNotExist:
                logger.error(
                    'Verloop: disposition option %s not found', id_disposition_option
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Disposition option not found'),
                        'errors': {
                            'X-Verloop-Disposition': _(
                                'The disposition option with the provided ID does not exist'
                            )
                        },
                    },
                    status=HTTP_404_NOT_FOUND,
                )

            campana = opcion_calificacion.campana
            if contacto.bd_contacto_id != campana.bd_contacto_id:
                logger.error(
                    'Verloop: contact %s does not belong to campaign %s database',
                    customer_id_int, campana.id,
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Contact does not belong to campaign database'),
                        'errors': {
                            'contact': _(
                                'The contact does not belong to the campaign database of '
                                'the specified disposition option'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            call_id_verloop = (
                body_data.get('callid')
                or body_data.get('call_id')
                or body_data.get('X-Verloop-UniqueID')
                or body_data.get('X-Verloop-callID')
                or request.headers.get('X-Verloop-UniqueID')
                or request.headers.get('X-Verloop-callID')
            )
            if call_id_verloop:
                call_id_verloop = str(call_id_verloop).strip()

            try:
                observaciones = self._construir_observaciones(body_data, call_summary)

                calificacion_existente = CalificacionCliente.objects.filter(
                    contacto=contacto,
                    opcion_calificacion__campana=campana,
                ).first()

                if calificacion_existente:
                    logger.info(
                        'Verloop: actualizando calificación id=%s para contacto=%s en campaña=%s',
                        calificacion_existente.id, customer_id_int, campana.id,
                    )
                    calificacion_existente.opcion_calificacion = opcion_calificacion
                    calificacion_existente.observaciones = observaciones
                    if call_id_verloop:
                        calificacion_existente.callid = call_id_verloop
                    # No actualizamos agente ni fecha para preservar el histórico
                    calificacion_existente.save()
                    calificacion = calificacion_existente
                else:
                    logger.info(
                        'Verloop: creando nueva calificación para contacto=%s con opción=%s',
                        customer_id_int, id_disposition_option,
                    )
                    agente = self._resolver_agente(request, campana)
                    calificacion = CalificacionCliente.objects.create(
                        contacto=contacto,
                        opcion_calificacion=opcion_calificacion,
                        observaciones=observaciones,
                        agente=agente,
                        es_calificacion_manual=False,
                        callid=call_id_verloop,
                    )

                response_data = {
                    'id': calificacion.id,
                    'idContact': calificacion.contacto.id,
                    'idDispositionOption': calificacion.opcion_calificacion.id,
                    'comments': calificacion.observaciones,
                    'fecha': calificacion.fecha.isoformat() if calificacion.fecha else None,
                }

                calificacion_nombre_voicebot = _calificacion_nombre_voicebot()
                if call_id_verloop and opcion_calificacion.nombre == calificacion_nombre_voicebot:
                    self._publicar_voicebot_transfer_proceed(call_id_verloop)
                elif call_id_verloop:
                    logger.info(
                        'Verloop: disposition "%s" (id=%s) no es %s, no se envía '
                        'voicebot_transfer_proceed',
                        opcion_calificacion.nombre, opcion_calificacion.id,
                        calificacion_nombre_voicebot,
                    )
                else:
                    logger.warning(
                        'Verloop: sin call_id en request, no se envía voicebot_transfer_proceed'
                    )

                return Response(
                    data={
                        'status': 'SUCCESS',
                        'message': (
                            _('Disposition updated successfully')
                            if calificacion_existente
                            else _('Disposition created successfully')
                        ),
                        'data': response_data,
                    },
                    status=HTTP_200_OK,
                )

            except ValueError as e:
                logger.error(
                    'Verloop: value error creating disposition for contact %s: %s',
                    customer_id_int, e, exc_info=True,
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': str(e),
                        'errors': {'validation': str(e)},
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.exception(
                    'Verloop: unexpected error creating disposition for contact %s: %s',
                    customer_id_int, e,
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Error creating disposition'),
                        'errors': {
                            'internal': _('An error occurred while creating the disposition')
                        },
                    },
                    status=HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except ValueError as e:
            logger.error('Verloop: value error: %s', e, exc_info=True)
            return Response(
                data={
                    'status': 'ERROR',
                    'message': _('Invalid value in request'),
                    'errors': {'validation': str(e)},
                },
                status=HTTP_400_BAD_REQUEST,
            )
        except TypeError as e:
            logger.error('Verloop: type error: %s', e, exc_info=True)
            return Response(
                data={
                    'status': 'ERROR',
                    'message': _('Type error in request processing'),
                    'errors': {'type': str(e)},
                },
                status=HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception(
                'Verloop: unexpected error - user=%s ip=%s: %s',
                getattr(request.user, 'username', 'unknown'),
                request.META.get('REMOTE_ADDR', 'unknown'),
                e,
            )
            return Response(
                data={
                    'status': 'ERROR',
                    'message': _('Unexpected error processing webhook'),
                    'errors': {
                        'internal': _(
                            'An unexpected error occurred. Please contact support if this '
                            'persists.'
                        )
                    },
                },
                status=HTTP_500_INTERNAL_SERVER_ERROR,
            )
