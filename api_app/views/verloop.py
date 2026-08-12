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
from api_app.services.voicebot_webhook import (
    construir_observaciones,
    extract_call_summary,
    publicar_voicebot_transfer_proceed,
    read_required_field,
    resolver_agente_fallback,
    sanitize_headers_for_log,
)
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.models import (
    Contacto, OpcionCalificacion, CalificacionCliente
)

logger = logging.getLogger(__name__)

# Nombre de la calificación que dispara el comando voicebot_transfer_proceed
# hacia el ACD. Se puede sobreescribir desde settings (VERLOOP_CALIFICACION_NOMBRE).
DEFAULT_VERLOOP_CALIFICACION_NOMBRE = 'GESTION_BOT'

LOG_LABEL = 'Verloop'


def _calificacion_nombre_voicebot():
    """Nombre de OpcionCalificacion que indica fin de gestión del voicebot."""
    return getattr(
        settings, 'VERLOOP_CALIFICACION_NOMBRE', DEFAULT_VERLOOP_CALIFICACION_NOMBRE
    )


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
        return extract_call_summary(body_data)

    @staticmethod
    def _construir_observaciones(body_data):
        return construir_observaciones(
            body_data, excluded_keys={'callID', 'customerID', 'phone', 'CampID'})

    @staticmethod
    def _resolver_agente(request, campana):
        return resolver_agente_fallback(
            request, campana,
            getattr(settings, 'VERLOOP_BOT_AGENT_USERNAME', None), LOG_LABEL)

    @staticmethod
    def _publicar_voicebot_transfer_proceed(call_id):
        publicar_voicebot_transfer_proceed(call_id)

    @staticmethod
    def _read_required_field(body_data, headers, field_name):
        return read_required_field(body_data, headers, field_name)

    def post(self, request):
        """
        Procesa el POST request de Verloop y crea/actualiza una calificación.

        Campos OBLIGATORIOS (en body JSON o header, con ese nombre EXACTO,
        prioridad body > header). No se aceptan variaciones de nombre:
          - X-Verloop-customerID   (id de Contacto)
          - X-Verloop-CampID       (id de Campana, debe coincidir con la
                                    campaña de la OpcionCalificacion indicada)
          - X-Verloop-callID       (id de la llamada en el ACD)
          - X-Verloop-Disposition  (id de OpcionCalificacion)

        Campos opcionales en body (para observaciones / resumen):
          - call_summary / Call_Summary (raíz o en analysis.user_defined)
          - name, PlanId, PlanCost, PlanUsage, companyName
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
                sanitize_headers_for_log(request.headers),
            )
        elif logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                'Verloop webhook headers=%s',
                sanitize_headers_for_log(request.headers),
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

            customer_id = self._read_required_field(
                body_data, request.headers, 'X-Verloop-customerID'
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

            camp_id = self._read_required_field(
                body_data, request.headers, 'X-Verloop-CampID'
            )
            if not camp_id:
                logger.error('Verloop: X-Verloop-CampID is missing in body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-CampID is required'),
                        'errors': {
                            'X-Verloop-CampID': _(
                                'The X-Verloop-CampID must be provided either in the '
                                'request body or as a header'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            try:
                camp_id_int = int(camp_id)
                if camp_id_int <= 0:
                    raise ValueError('Camp ID must be positive')
            except (ValueError, TypeError) as e:
                logger.error('Verloop: invalid X-Verloop-CampID format: %s - %s', camp_id, e)
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-CampID must be a valid positive integer'),
                        'errors': {
                            'X-Verloop-CampID': _(
                                'The campaign ID must be a valid positive integer'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            call_id_verloop = self._read_required_field(
                body_data, request.headers, 'X-Verloop-callID'
            )
            if not call_id_verloop:
                logger.error('Verloop: X-Verloop-callID is missing in body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-Verloop-callID is required'),
                        'errors': {
                            'X-Verloop-callID': _(
                                'The X-Verloop-callID must be provided either in the '
                                'request body or as a header'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            call_id_verloop = str(call_id_verloop)

            disposition_id = self._read_required_field(
                body_data, request.headers, 'X-Verloop-Disposition'
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
            if campana.id != camp_id_int:
                logger.error(
                    'Verloop: X-Verloop-CampID=%s no coincide con la campaña %s '
                    'de la OpcionCalificacion %s',
                    camp_id_int, campana.id, id_disposition_option,
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _(
                            'X-Verloop-CampID does not match the disposition option campaign'
                        ),
                        'errors': {
                            'X-Verloop-CampID': _(
                                'The provided campaign ID does not match the campaign of '
                                'the specified disposition option'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

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

            try:
                observaciones = self._construir_observaciones(body_data)

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
                if opcion_calificacion.nombre == calificacion_nombre_voicebot:
                    self._publicar_voicebot_transfer_proceed(call_id_verloop)
                else:
                    logger.info(
                        'Verloop: disposition "%s" (id=%s) no es %s, no se envía '
                        'voicebot_transfer_proceed',
                        opcion_calificacion.nombre, opcion_calificacion.id,
                        calificacion_nombre_voicebot,
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
