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

from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from notification_app.notification import AgentNotifier
from ominicontacto_app.models import AgendaContacto, Campana, Contacto
from ominicontacto_app.services.agenda_contacto import guardar_agenda_contacto


class AgendaContactoCreateAPIView(APIView):
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    renderer_classes = (JSONRenderer, )
    http_method_names = ['post']

    def post(self, request):
        msg_error_datos = _('Hubo errores en los datos recibidos')
        agente = request.user.get_agente_profile()
        if not agente:
            return Response(data={
                'status': 'ERROR',
                'message': _('Usted no tiene permiso para realizar esta acción'),
            }, status=status.HTTP_403_FORBIDDEN)

        errors = {}

        try:
            campaign_id = int(request.data.get('campaign_id'))
        except (TypeError, ValueError):
            errors['campaign_id'] = [_('Este campo es requerido.')]

        try:
            contact_id = int(request.data.get('contact_id'))
        except (TypeError, ValueError):
            errors['contact_id'] = [_('Este campo es requerido.')]

        date_raw = request.data.get('date')
        time_raw = request.data.get('time')
        phone = request.data.get('phone')
        observations = request.data.get('observations', '')

        if not date_raw:
            errors['date'] = [_('Este campo es requerido.')]
        if not time_raw:
            errors['time'] = [_('Este campo es requerido.')]
        if not phone:
            errors['phone'] = [_('Este campo es requerido.')]

        schedule_type_raw = request.data.get('schedule_type', AgendaContacto.TYPE_PERSONAL)
        try:
            tipo_agenda = int(schedule_type_raw)
        except (TypeError, ValueError):
            errors['schedule_type'] = [_('Valor inválido.')]

        if errors:
            return Response(data={
                'status': 'ERROR',
                'message': msg_error_datos,
                'errors': errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        if tipo_agenda not in (AgendaContacto.TYPE_PERSONAL, AgendaContacto.TYPE_GLOBAL):
            return Response(data={
                'status': 'ERROR',
                'message': msg_error_datos,
                'errors': {'schedule_type': [_('Valor inválido.')]},
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            campana = Campana.objects.obtener_activas().get(pk=campaign_id)
        except Campana.DoesNotExist:
            return Response(data={
                'status': 'ERROR',
                'message': _('Campaña inexistente o inactiva.'),
            }, status=status.HTTP_404_NOT_FOUND)

        if not campana.queue_campana.members.filter(id=agente.id).exists():
            return Response(data={
                'status': 'ERROR',
                'message': _('Usted no tiene permiso para realizar esta acción'),
            }, status=status.HTTP_403_FORBIDDEN)

        if campana.bd_contacto is None:
            return Response(data={
                'status': 'ERROR',
                'message': _('La campaña no tiene base de contactos asociada.'),
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            contacto = campana.bd_contacto.contactos.get(pk=contact_id)
        except Contacto.DoesNotExist:
            return Response(data={
                'status': 'ERROR',
                'message': _('Contacto inexistente o no pertenece a la campaña.'),
            }, status=status.HTTP_404_NOT_FOUND)

        if tipo_agenda == AgendaContacto.TYPE_GLOBAL and campana.type != Campana.TYPE_DIALER:
            return Response(data={
                'status': 'ERROR',
                'message': msg_error_datos,
                'errors': {
                    'schedule_type': [_('Solo se permite agenda global en campañas dialer.')],
                },
            }, status=status.HTTP_400_BAD_REQUEST)

        telefonos_validos = contacto.lista_de_telefonos_de_contacto()
        if phone not in telefonos_validos:
            return Response(data={
                'status': 'ERROR',
                'message': msg_error_datos,
                'errors': {'phone': [_('Teléfono inválido para el contacto.')]},
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            fecha = datetime.strptime(date_raw, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return Response(data={
                'status': 'ERROR',
                'message': msg_error_datos,
                'errors': {'date': [_('Formato inválido. Use YYYY-MM-DD.')]},
            }, status=status.HTTP_400_BAD_REQUEST)

        hora = self._parse_time(time_raw)
        if hora is None:
            return Response(data={
                'status': 'ERROR',
                'message': msg_error_datos,
                'errors': {'time': [_('Formato inválido. Use HH:MM:SS o HH:MM.')]},
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            agenda, created, despausado = guardar_agenda_contacto(
                agente, campana, contacto, fecha, hora, phone,
                tipo_agenda, observaciones=observations)
        except ValidationError as e:
            return Response(data={
                'status': 'ERROR',
                'message': e.message,
            }, status=status.HTTP_400_BAD_REQUEST)

        if despausado:
            AgentNotifier().notify_dispositioned(agente.user_id, None, True)

        return Response(data={
            'status': 'OK',
            'agenda_id': agenda.id,
            'created': created,
        })

    def _parse_time(self, time_raw):
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return datetime.strptime(time_raw, fmt).time()
            except (TypeError, ValueError):
                continue
        return None
