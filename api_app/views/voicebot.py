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
    intentar_anexar_summary_a_agenda_previa,
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
# hacia el ACD. Se puede sobreescribir desde settings (VOICEBOT_CALIFICACION_NOMBRE).
DEFAULT_VOICEBOT_CALIFICACION_NOMBRE = 'GESTION_BOT'

LOG_LABEL = 'Voicebot'


def _calificacion_nombre_voicebot():
    """Nombre de OpcionCalificacion que indica fin de gestión del voicebot."""
    return getattr(
        settings, 'VOICEBOT_CALIFICACION_NOMBRE', DEFAULT_VOICEBOT_CALIFICACION_NOMBRE
    )


class VoicebotWebhookView(APIView):
    """
    Vista genérica que procesa webhooks de voicebots SIP y crea/actualiza la
    calificación del contacto en la campaña correspondiente. Si ya existe una
    AgendaContacto para el contacto y la campaña, solo concatena el
    call_summary a las observaciones de esa agenda y no publica comandos al
    ACD. Si no hay agenda previa y la opción aplicada coincide con la
    configurada para fin de gestión del bot, publica voicebot_transfer_proceed
    en Redis para que el ACD continúe la transferencia pendiente tras el REFER.
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
            body_data, excluded_keys={'contactID', 'customerID', 'phone', 'CampaignID'})

    @staticmethod
    def _resolver_agente(request, campana):
        return resolver_agente_fallback(
            request, campana,
            getattr(settings, 'VOICEBOT_BOT_AGENT_USERNAME', None), LOG_LABEL)

    @staticmethod
    def _publicar_voicebot_transfer_proceed(call_id):
        publicar_voicebot_transfer_proceed(call_id)

    @staticmethod
    def _read_required_field(body_data, headers, field_name):
        return read_required_field(body_data, headers, field_name)

    def post(self, request):
        """
        Procesa el POST del webhook genérico de voicebot y crea/actualiza una calificación.

        Campos OBLIGATORIOS (en body JSON o header, con ese nombre EXACTO,
        prioridad body > header). No se aceptan variaciones de nombre:
          - X-OML-Contact-ID     (id de Contacto)
          - X-OML-Campaign-ID    (id de Campana, debe coincidir con la campaña de la
                                   OpcionCalificacion indicada)
          - X-OML-Call-ID        (id de la llamada en el ACD)
          - X-OML-Disposition    (id de OpcionCalificacion)

        Campos opcionales en body (para observaciones / resumen):
          - call_summary / Call_Summary (raíz o en analysis.user_defined)
        """
        logger.info(
            'Voicebot webhook received - user=%s ip=%s',
            getattr(request.user, 'username', 'anonymous'),
            request.META.get('REMOTE_ADDR', 'unknown'),
        )
        debug_payload = bool(getattr(settings, 'VOICEBOT_DEBUG_PAYLOAD', False))
        if debug_payload:
            logger.info(
                'Voicebot DEBUG headers=%s',
                sanitize_headers_for_log(request.headers),
            )
        elif logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                'Voicebot webhook headers=%s',
                sanitize_headers_for_log(request.headers),
            )

        try:
            try:
                body_data = request.data if hasattr(request, 'data') else json.loads(request.body)
            except json.JSONDecodeError as e:
                logger.error('Voicebot: invalid JSON body received: %s', e)
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Invalid JSON body'),
                        'errors': {'json': _('The request body must be valid JSON')},
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            except (AttributeError, TypeError) as e:
                logger.error('Voicebot: error accessing request body: %s', e)
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Invalid request body'),
                        'errors': {'body': _('Unable to parse request body')},
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            if not isinstance(body_data, dict):
                logger.warning('Voicebot: request body is not a dict, got %s', type(body_data))
                body_data = {}

            if debug_payload:
                try:
                    body_dump = json.dumps(
                        body_data, indent=2, ensure_ascii=False, default=str,
                    )
                except (TypeError, ValueError):
                    body_dump = repr(body_data)
                logger.info('Voicebot DEBUG body completo:\n%s', body_dump)
            elif logger.isEnabledFor(logging.DEBUG):
                logger.debug('Voicebot body keys: %s', list(body_data.keys()))

            call_summary = self._extract_call_summary(body_data)
            if (
                call_summary
                and isinstance(call_summary, str)
                and call_summary.strip().lower() == 'none'
            ):
                logger.error('Voicebot: call_summary is "None" string, which is invalid')
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

            contact_id = self._read_required_field(
                body_data, request.headers, 'X-OML-Contact-ID'
            )
            if not contact_id:
                logger.error('Voicebot: X-OML-Contact-ID is missing in body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-OML-Contact-ID is required'),
                        'errors': {
                            'X-OML-Contact-ID': _(
                                'The X-OML-Contact-ID must be provided either in the '
                                'request body or as a header'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            try:
                contact_id_int = int(contact_id)
                if contact_id_int <= 0:
                    raise ValueError('Contact ID must be positive')
            except (ValueError, TypeError) as e:
                logger.error('Voicebot: invalid contact_id format: %s - %s', contact_id, e)
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-OML-Contact-ID must be a valid positive integer'),
                        'errors': {
                            'X-OML-Contact-ID': _(
                                'The contact ID must be a valid positive integer'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            camp_id = self._read_required_field(
                body_data, request.headers, 'X-OML-Campaign-ID'
            )
            if not camp_id:
                logger.error('Voicebot: X-OML-Campaign-ID is missing in body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-OML-Campaign-ID is required'),
                        'errors': {
                            'X-OML-Campaign-ID': _(
                                'The X-OML-Campaign-ID must be provided either in the '
                                'request body or as a header'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            try:
                camp_id_int = int(camp_id)
                if camp_id_int <= 0:
                    raise ValueError('Campaign ID must be positive')
            except (ValueError, TypeError) as e:
                logger.error('Voicebot: invalid X-OML-Campaign-ID format: %s - %s', camp_id, e)
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-OML-Campaign-ID must be a valid positive integer'),
                        'errors': {
                            'X-OML-Campaign-ID': _(
                                'The campaign ID must be a valid positive integer'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            call_id_acd = self._read_required_field(
                body_data, request.headers, 'X-OML-Call-ID'
            )
            if not call_id_acd:
                logger.error('Voicebot: X-OML-Call-ID is missing in body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-OML-Call-ID is required'),
                        'errors': {
                            'X-OML-Call-ID': _(
                                'The X-OML-Call-ID must be provided either in the '
                                'request body or as a header'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            call_id_acd = str(call_id_acd)

            disposition_id = self._read_required_field(
                body_data, request.headers, 'X-OML-Disposition'
            )
            if not disposition_id:
                logger.error('Voicebot: X-OML-Disposition is missing in body and header')
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-OML-Disposition is required'),
                        'errors': {
                            'X-OML-Disposition': _(
                                'The X-OML-Disposition (disposition option ID) must be '
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
                    'Voicebot: invalid X-OML-Disposition format: %s - %s',
                    disposition_id, e,
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('X-OML-Disposition must be a valid positive integer'),
                        'errors': {
                            'X-OML-Disposition': _(
                                'The disposition option ID must be a valid positive integer'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            try:
                contacto = Contacto.objects.get(pk=contact_id_int)
            except Contacto.DoesNotExist:
                logger.error('Voicebot: contact %s not found', contact_id_int)
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
                    'Voicebot: disposition option %s not found', id_disposition_option
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _('Disposition option not found'),
                        'errors': {
                            'X-OML-Disposition': _(
                                'The disposition option with the provided ID does not exist'
                            )
                        },
                    },
                    status=HTTP_404_NOT_FOUND,
                )

            campana = opcion_calificacion.campana
            if campana.id != camp_id_int:
                logger.error(
                    'Voicebot: X-OML-Campaign-ID=%s no coincide con la campaña %s '
                    'de la OpcionCalificacion %s',
                    camp_id_int, campana.id, id_disposition_option,
                )
                return Response(
                    data={
                        'status': 'ERROR',
                        'message': _(
                            'X-OML-Campaign-ID does not match the disposition option campaign'
                        ),
                        'errors': {
                            'X-OML-Campaign-ID': _(
                                'The provided campaign ID does not match the campaign of '
                                'the specified disposition option'
                            )
                        },
                    },
                    status=HTTP_400_BAD_REQUEST,
                )

            if contacto.bd_contacto_id != campana.bd_contacto_id:
                logger.error(
                    'Voicebot: contact %s does not belong to campaign %s database',
                    contact_id_int, campana.id,
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

            payload_agenda = intentar_anexar_summary_a_agenda_previa(
                contacto, campana, call_summary, LOG_LABEL)
            if payload_agenda is not None:
                return Response(
                    data={
                        'status': 'SUCCESS',
                        'message': _('Summary appended to existing schedule'),
                        'data': payload_agenda,
                    },
                    status=HTTP_200_OK,
                )

            try:
                observaciones = self._construir_observaciones(body_data)

                calificacion_existente = CalificacionCliente.objects.filter(
                    contacto=contacto,
                    opcion_calificacion__campana=campana,
                ).first()

                if calificacion_existente:
                    logger.info(
                        'Voicebot: actualizando calificación id=%s para contacto=%s en campaña=%s',
                        calificacion_existente.id, contact_id_int, campana.id,
                    )
                    calificacion_existente.opcion_calificacion = opcion_calificacion
                    calificacion_existente.observaciones = observaciones
                    calificacion_existente.callid = call_id_acd
                    calificacion_existente.save()
                    calificacion = calificacion_existente
                else:
                    logger.info(
                        'Voicebot: creando nueva calificación para contacto=%s con opción=%s',
                        contact_id_int, id_disposition_option,
                    )
                    agente = self._resolver_agente(request, campana)
                    calificacion = CalificacionCliente.objects.create(
                        contacto=contacto,
                        opcion_calificacion=opcion_calificacion,
                        observaciones=observaciones,
                        agente=agente,
                        es_calificacion_manual=False,
                        callid=call_id_acd,
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
                    self._publicar_voicebot_transfer_proceed(call_id_acd)
                else:
                    logger.info(
                        'Voicebot: disposition "%s" (id=%s) no es %s, no se envía '
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
                    'Voicebot: value error creating disposition for contact %s: %s',
                    contact_id_int, e, exc_info=True,
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
                    'Voicebot: unexpected error creating disposition for contact %s: %s',
                    contact_id_int, e,
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
            logger.error('Voicebot: value error: %s', e, exc_info=True)
            return Response(
                data={
                    'status': 'ERROR',
                    'message': _('Invalid value in request'),
                    'errors': {'validation': str(e)},
                },
                status=HTTP_400_BAD_REQUEST,
            )
        except TypeError as e:
            logger.error('Voicebot: type error: %s', e, exc_info=True)
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
                'Voicebot: unexpected error - user=%s ip=%s: %s',
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
