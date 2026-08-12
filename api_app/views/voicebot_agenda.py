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
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
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
    parse_callback_valid,
    parse_positive_int,
    read_required_field,
    resolver_agente_voicebot,
    sanitize_headers_for_log,
)
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.models import (
    AgendaContacto, CalificacionCliente, Campana, Contacto, OpcionCalificacion
)
from ominicontacto_app.services.agenda_contacto import guardar_agenda_contacto

logger = logging.getLogger(__name__)

LOG_LABEL = 'VoicebotAgenda'

# Claves que no deben volcarse en las observaciones de la calificación.
OBSERVACIONES_EXCLUDED_KEYS = {
    'contactID', 'customerID', 'phone', 'CampaignID', 'CampID', 'callID',
}


def _parse_date(date_raw):
    try:
        return datetime.strptime(date_raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _parse_time(time_raw):
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(time_raw, fmt).time()
        except (TypeError, ValueError):
            continue
    return None


class VoicebotAgendaWebhookView(APIView):
    """
    Webhook genérico para que un voicebot (Verloop u otro) agende un callback
    de un contacto en una sola llamada:
      1. Califica al contacto con la opción reservada "Agenda" de la campaña.
      2. Si callback_valid=true y la fecha/hora son válidas, crea o actualiza
         (upsert por contacto+campaña) la AgendaContacto personal asignada al
         agente voicebot de la campaña.

    Campos OBLIGATORIOS (en body JSON o header, con ese nombre EXACTO,
    prioridad body > header). No se aceptan variaciones de nombre:
      - X-OML-Campaign-ID    (id de Campana activa)
      - X-OML-Contact-ID     (id de Contacto de la base de la campaña)
      - X-OML-Call-ID        (id de la llamada en el ACD)
      - phone                (teléfono del contacto a llamar)

    Campos opcionales en body:
      - callback_valid       ("true"/"false"; default false)
      - callback_date        (YYYY-MM-DD; requerida si callback_valid=true)
      - callback_time        (HH:MM:SS o HH:MM; requerida si callback_valid=true)
      - callback_request     (pedido original del cliente → observaciones)
      - callback_rule        (regla de normalización aplicada → observaciones)
    """
    permission_classes = (TienePermisoOML,)
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)
    renderer_classes = (JSONRenderer,)
    http_method_names = ['post']

    def _error_response(self, message, errors, http_status):
        return Response(
            data={'status': 'ERROR', 'message': message, 'errors': errors},
            status=http_status,
        )

    def _read_positive_int_field(self, body_data, headers, field_name, error_message):
        """Lee un campo obligatorio y lo valida como entero positivo.

        Devuelve (valor_int, None) o (None, Response de error).
        """
        raw = read_required_field(body_data, headers, field_name)
        if not raw:
            logger.error('%s: %s is missing in body and header', LOG_LABEL, field_name)
            return None, self._error_response(
                _(f'{field_name} is required'),
                {field_name: _(
                    f'The {field_name} must be provided either in the request body '
                    'or as a header')},
                HTTP_400_BAD_REQUEST,
            )
        try:
            return parse_positive_int(raw), None
        except (ValueError, TypeError) as e:
            logger.error('%s: invalid %s format: %s - %s', LOG_LABEL, field_name, raw, e)
            return None, self._error_response(
                _(f'{field_name} must be a valid positive integer'),
                {field_name: _('The value must be a valid positive integer')},
                HTTP_400_BAD_REQUEST,
            )

    def post(self, request):
        logger.info(
            'Voicebot agenda webhook received - user=%s ip=%s',
            getattr(request.user, 'username', 'anonymous'),
            request.META.get('REMOTE_ADDR', 'unknown'),
        )
        debug_payload = bool(getattr(settings, 'VOICEBOT_DEBUG_PAYLOAD', False))
        if debug_payload:
            logger.info(
                '%s DEBUG headers=%s', LOG_LABEL,
                sanitize_headers_for_log(request.headers),
            )

        try:
            try:
                body_data = request.data if hasattr(request, 'data') else json.loads(request.body)
            except (json.JSONDecodeError, AttributeError, TypeError) as e:
                logger.error('%s: invalid request body: %s', LOG_LABEL, e)
                return self._error_response(
                    _('Invalid request body'),
                    {'body': _('The request body must be valid JSON')},
                    HTTP_400_BAD_REQUEST,
                )

            if not isinstance(body_data, dict):
                logger.warning('%s: request body is not a dict, got %s', LOG_LABEL,
                               type(body_data))
                body_data = {}

            if debug_payload:
                try:
                    body_dump = json.dumps(
                        body_data, indent=2, ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    body_dump = repr(body_data)
                logger.info('%s DEBUG body completo:\n%s', LOG_LABEL, body_dump)

            camp_id, error = self._read_positive_int_field(
                body_data, request.headers, 'X-OML-Campaign-ID', _('Campaign ID'))
            if error:
                return error

            contact_id, error = self._read_positive_int_field(
                body_data, request.headers, 'X-OML-Contact-ID', _('Contact ID'))
            if error:
                return error

            call_id = read_required_field(body_data, request.headers, 'X-OML-Call-ID')
            if not call_id:
                logger.error('%s: X-OML-Call-ID is missing in body and header', LOG_LABEL)
                return self._error_response(
                    _('X-OML-Call-ID is required'),
                    {'X-OML-Call-ID': _(
                        'The X-OML-Call-ID must be provided either in the request body '
                        'or as a header')},
                    HTTP_400_BAD_REQUEST,
                )
            call_id = str(call_id)

            phone = read_required_field(body_data, request.headers, 'phone')
            if not phone:
                logger.error('%s: phone is missing in body and header', LOG_LABEL)
                return self._error_response(
                    _('phone is required'),
                    {'phone': _(
                        'The phone must be provided either in the request body or as '
                        'a header')},
                    HTTP_400_BAD_REQUEST,
                )
            phone = str(phone)

            callback_valid = parse_callback_valid(body_data.get('callback_valid'))
            callback_request = body_data.get('callback_request') or ''
            callback_rule = body_data.get('callback_rule') or ''

            try:
                campana = Campana.objects.obtener_activas().get(pk=camp_id)
            except Campana.DoesNotExist:
                logger.error('%s: campaign %s not found or not active', LOG_LABEL, camp_id)
                return self._error_response(
                    _('Campaign not found or not active'),
                    {'campaign': _(
                        'The campaign with the provided ID does not exist or is not active')},
                    HTTP_404_NOT_FOUND,
                )

            try:
                contacto = Contacto.objects.get(pk=contact_id)
            except Contacto.DoesNotExist:
                logger.error('%s: contact %s not found', LOG_LABEL, contact_id)
                return self._error_response(
                    _('Contact not found'),
                    {'contact': _('The contact with the provided ID does not exist')},
                    HTTP_404_NOT_FOUND,
                )

            if campana.bd_contacto_id is None:
                logger.error('%s: campaign %s has no contact database', LOG_LABEL, campana.id)
                return self._error_response(
                    _('Campaign has no contact database'),
                    {'campaign': _('The campaign does not have a contact database')},
                    HTTP_400_BAD_REQUEST,
                )

            if contacto.bd_contacto_id != campana.bd_contacto_id:
                logger.error(
                    '%s: contact %s does not belong to campaign %s database',
                    LOG_LABEL, contact_id, campana.id,
                )
                return self._error_response(
                    _('Contact does not belong to campaign database'),
                    {'contact': _(
                        'The contact does not belong to the campaign database')},
                    HTTP_400_BAD_REQUEST,
                )

            if phone not in contacto.lista_de_telefonos_de_contacto():
                logger.error(
                    '%s: phone %s is not a valid phone for contact %s',
                    LOG_LABEL, phone, contact_id,
                )
                return self._error_response(
                    _('Invalid phone for the contact'),
                    {'phone': _('The phone must be one of the contact phone numbers')},
                    HTTP_400_BAD_REQUEST,
                )

            agente = resolver_agente_voicebot(campana)
            if agente is None:
                logger.error(
                    '%s: campaign %s has no voicebot agent assigned', LOG_LABEL, campana.id)
                return self._error_response(
                    _('Campaign has no voicebot agent'),
                    {'campaign': _(
                        'The campaign does not have a voicebot agent assigned')},
                    HTTP_400_BAD_REQUEST,
                )

            warnings = []
            fecha = hora = None
            if callback_valid:
                fecha = _parse_date(body_data.get('callback_date'))
                hora = _parse_time(body_data.get('callback_time'))
                if fecha is None or hora is None:
                    logger.warning(
                        '%s: callback_valid=true pero fecha/hora inválidas '
                        '(date=%r time=%r); se califica sin agendar',
                        LOG_LABEL, body_data.get('callback_date'),
                        body_data.get('callback_time'),
                    )
                    warnings.append(_(
                        'Invalid callback_date/callback_time: the disposition was '
                        'recorded without scheduling'))
                    fecha = hora = None
            else:
                warnings.append(_(
                    'callback_valid=false: the disposition was recorded without '
                    'scheduling'))

            observaciones = construir_observaciones(
                body_data, excluded_keys=OBSERVACIONES_EXCLUDED_KEYS)
            observaciones_agenda = callback_request or observaciones
            if callback_rule:
                observaciones_agenda = '{0} (rule: {1})'.format(
                    observaciones_agenda, callback_rule) if observaciones_agenda \
                    else '(rule: {0})'.format(callback_rule)

            try:
                with transaction.atomic():
                    opcion_agenda, _opcion_created = OpcionCalificacion.objects.get_or_create(
                        campana=campana,
                        nombre=settings.CALIFICACION_REAGENDA,
                        tipo=OpcionCalificacion.AGENDA,
                    )

                    calificacion = CalificacionCliente.objects.filter(
                        contacto=contacto,
                        opcion_calificacion__campana=campana,
                    ).first()
                    if calificacion:
                        logger.info(
                            '%s: actualizando calificación id=%s para contacto=%s en '
                            'campaña=%s',
                            LOG_LABEL, calificacion.id, contact_id, campana.id,
                        )
                        calificacion.opcion_calificacion = opcion_agenda
                        calificacion.observaciones = observaciones
                        calificacion.callid = call_id
                        calificacion.save()
                    else:
                        logger.info(
                            '%s: creando calificación Agenda para contacto=%s campaña=%s',
                            LOG_LABEL, contact_id, campana.id,
                        )
                        calificacion = CalificacionCliente.objects.create(
                            contacto=contacto,
                            opcion_calificacion=opcion_agenda,
                            observaciones=observaciones,
                            agente=agente,
                            es_calificacion_manual=False,
                            callid=call_id,
                        )

                    agenda = None
                    agenda_created = False
                    if callback_valid and fecha is not None:
                        agenda, agenda_created, _despausado = guardar_agenda_contacto(
                            agente, campana, contacto, fecha, hora, phone,
                            AgendaContacto.TYPE_PERSONAL,
                            observaciones=observaciones_agenda)
                        logger.info(
                            '%s: agenda id=%s %s para contacto=%s (%s %s)',
                            LOG_LABEL, agenda.id,
                            'creada' if agenda_created else 'actualizada',
                            contact_id, fecha, hora,
                        )
            except ValidationError as e:
                logger.error(
                    '%s: error de validación agendando contacto %s: %s',
                    LOG_LABEL, contact_id, e, exc_info=True,
                )
                return self._error_response(
                    '; '.join(e.messages),
                    {'agenda': e.messages},
                    HTTP_400_BAD_REQUEST,
                )

            return Response(
                data={
                    'status': 'OK',
                    'calificacion_id': calificacion.id,
                    'agenda_id': agenda.id if agenda else None,
                    'created': agenda_created,
                    'warnings': warnings,
                },
                status=HTTP_200_OK,
            )

        except Exception as e:
            logger.exception(
                '%s: unexpected error - user=%s ip=%s: %s',
                LOG_LABEL,
                getattr(request.user, 'username', 'unknown'),
                request.META.get('REMOTE_ADDR', 'unknown'),
                e,
            )
            return self._error_response(
                _('Unexpected error processing webhook'),
                {'internal': _(
                    'An unexpected error occurred. Please contact support if this '
                    'persists.')},
                HTTP_500_INTERNAL_SERVER_ERROR,
            )
