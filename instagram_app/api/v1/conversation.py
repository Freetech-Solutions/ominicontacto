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
import mimetypes
import operator
import uuid
from dataclasses import dataclass
from functools import reduce

from django.db.models import (
    Count, IntegerField, OuterRef, Prefetch, Q, Subquery, Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import decorators, response, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from api_app.services.media_url import build_public_media_url
from api_app.views.permissions import TienePermisoOML
from facebook_meta_app.models import PlantillaMessenger
from instagram_app.api.permissions import TienePermisoCanalInstagramAgente
from instagram_app.api.utils import HttpResponseStatus, get_response_data
from instagram_app.api.v1.contact import ListSerializer as ContactoSerializer
from instagram_app.api.v1.message import (
    MessageInstagramAppAttachmentSerializer, MessageInstagramAppSerializer,
)
from instagram_app.models import (
    ConversationInstagramApp, MessageInstagramApp, PlantillaInstagram,
)
from notification_app.notification import AgentNotifier
from ominicontacto_app.models import Campana, Contacto
from ominicontacto_app.utiles import datetime_hora_maxima_dia, datetime_hora_minima_dia
from orquestador_app.core.instagram.send_message import (
    send_media_message, send_text_message, upload_media_to_meta, uses_instagram_login,
)

mimetypes.init()

MESSAGE_SENDERS = {
    'AGENT': 0,
    'CLIENT': 1,
}


def _message_count_subquery(filters=None):
    filters = filters or {}
    queryset = MessageInstagramApp.objects.filter(
        conversation_id=OuterRef('id'),
        **filters
    ).order_by().values('conversation_id').annotate(
        count=Count('id')
    ).values('count')[:1]
    return Coalesce(
        Subquery(queryset, output_field=IntegerField()),
        Value(0),
        output_field=IntegerField(),
    )


def _conversation_base_queryset():
    return ConversationInstagramApp.objects.select_related(
        'campana',
        'account',
        'client__bd_contacto',
        'agent__user',
    ).annotate(
        message_number=_message_count_subquery(),
        message_unread=_message_count_subquery({
            'origen': OuterRef('ig_scoped_id'),
            'status': 'delivered',
        }),
    )


def _ordered_messages_prefetch():
    return Prefetch(
        'messages',
        queryset=MessageInstagramApp.objects.order_by('timestamp', 'id'),
    )


def _get_contact_data(conversation):
    if conversation.client:
        return conversation.client.obtener_datos()
    return {}


@dataclass
class ConversationFilterParams:
    start_date: object = None
    end_date: object = None
    phone: str = None
    agents: list = None


class ConversationFilterParamsSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    phone = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    agents = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        if bool(start_date) != bool(end_date):
            raise serializers.ValidationError(
                _('Debe indicar fecha desde y fecha hasta para aplicar el filtro.')
            )
        return attrs

    def create(self, validated_data):
        start_date = validated_data.get('start_date')
        end_date = validated_data.get('end_date')
        if start_date and end_date:
            validated_data['start_date'] = datetime_hora_minima_dia(start_date)
            validated_data['end_date'] = datetime_hora_maxima_dia(end_date)
        return ConversationFilterParams(**validated_data)


def get_report_conversations_queryset(campaign, params):
    chats = _conversation_base_queryset().filter(
        campana=campaign
    ).select_related(
        "conversation_disposition__opcion_calificacion",
    ).order_by(
        '-date_last_interaction', '-timestamp'
    )
    list_of_Q = []
    if params.agents:
        agents = list(params.agents)
        if -1 in agents:
            list_of_Q.append(Q(agent__isnull=True))
            agents.remove(-1)
        if agents:
            list_of_Q.append(Q(agent__in=agents))
    if list_of_Q:
        chats = chats.filter(reduce(operator.or_, list_of_Q))
    list_of_Q = []
    if params.start_date and params.end_date:
        list_of_Q.append(
            Q(date_last_interaction__range=[params.start_date, params.end_date])
        )
    if params.phone:
        list_of_Q.append(Q(ig_scoped_id__contains=params.phone))
    if list_of_Q:
        chats = chats.filter(reduce(operator.and_, list_of_Q))
    return chats


def get_type(file_name):
    mimestart = mimetypes.guess_type(file_name)[0]
    if mimestart is not None:
        type_file = mimestart.split('/')[0]
        return type_file if type_file not in ['application', 'text'] else 'file'
    return 'file'


class ConversacionInstagramSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    campaing_id = serializers.PrimaryKeyRelatedField(
        source='campana', read_only=True)
    campaing_name = serializers.CharField(source='campana.nombre', default=None)
    campaign_id = serializers.PrimaryKeyRelatedField(
        source='campana', read_only=True)
    campaign_name = serializers.CharField(source='campana.nombre', default=None)
    saliente = serializers.BooleanField(default=False)
    destination = serializers.CharField(source='ig_scoped_id', allow_null=True)
    ig_scoped_id = serializers.CharField(allow_null=True)
    page_client_id = serializers.CharField(source='ig_scoped_id', allow_null=True)
    client = serializers.SerializerMethodField()
    agent = serializers.PrimaryKeyRelatedField(read_only=True)
    is_active = serializers.BooleanField(default=True)
    is_disposition = serializers.BooleanField()
    expire = serializers.DateTimeField(allow_null=True)
    timestamp = serializers.DateTimeField()
    date_last_interaction = serializers.DateTimeField(allow_null=True)
    message_number = serializers.SerializerMethodField()
    message_unread = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    photo = serializers.CharField(default="")
    page = serializers.SerializerMethodField()
    error = serializers.BooleanField(default=False)
    error_ex = serializers.JSONField()
    client_alias = serializers.CharField(default="")

    def get_page(self, obj):
        account = obj.account
        if not account:
            return None
        return {
            'id': account.id,
            'page_id': account.ig_user_id,
            'name': account.name,
        }

    def get_message_number(self, obj):
        annotated_count = getattr(obj, 'message_number', None)
        if annotated_count is not None:
            return annotated_count
        return obj.messages.count()

    def get_message_unread(self, obj):
        annotated_count = getattr(obj, 'message_unread', None)
        if annotated_count is not None:
            return annotated_count
        return obj.messages.mensajes_recibidos().filter(status='delivered').count()

    def get_messages(self, obj):
        if self.context.get('include_messages') is False:
            return []
        messages_queryset = obj.messages.all()
        if 'messages' not in getattr(obj, '_prefetched_objects_cache', {}):
            messages_queryset = messages_queryset.order_by('timestamp', 'id')
        serializer_context = dict(self.context)
        serializer_context['contact_data'] = _get_contact_data(obj)
        return MessageInstagramAppSerializer(
            messages_queryset, many=True, context=serializer_context).data

    def get_client(self, obj):
        if obj.client:
            return {
                'id': obj.client.id,
                'phone': obj.client.telefono,
                'ig_scoped_id': obj.client.ig_scoped_id or obj.ig_scoped_id,
                'data': obj.client.obtener_datos(),
                'disposition': getattr(obj.client, 'last_disposition_id', None),
            }
        return None


class ConversacionInstagramFilterSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    campaign = serializers.SerializerMethodField()
    destination = serializers.CharField(source='ig_scoped_id', allow_null=True)
    was_closed_by_system = serializers.SerializerMethodField()
    disposition = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    agent = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(default=True)
    expire = serializers.DateTimeField(allow_null=True)
    timestamp = serializers.DateTimeField()
    date_last_interaction = serializers.DateTimeField(allow_null=True)
    message_number = serializers.IntegerField()
    photo = serializers.CharField(default="")
    line = serializers.SerializerMethodField()
    error = serializers.BooleanField(default=False)

    def get_line(self, obj):
        account = obj.account
        if not account:
            return {}
        return {
            'id': account.id,
            'name': account.name,
            'number': account.ig_user_id,
        }

    def get_campaign(self, obj):
        if obj.campana:
            return {
                'id': obj.campana.id,
                'name': obj.campana.nombre,
                'type': obj.campana.type,
            }
        return {}

    def get_agent(self, obj):
        if obj.agent:
            return {
                'id': obj.agent.user.id,
                'name': obj.agent.user.get_full_name() or obj.agent.user.username,
            }
        return None

    def get_client(self, obj):
        if obj.client:
            serializer = ContactoSerializer(obj.client)
            if 'disposition' in serializer.fields:
                del serializer.fields['disposition']
            return serializer.data
        return None

    def get_disposition(self, obj):
        try:
            if obj.is_disposition and obj.conversation_disposition:
                return {
                    'id': obj.conversation_disposition.opcion_calificacion.id,
                    'name': obj.conversation_disposition.opcion_calificacion.nombre,
                }
            return {}
        except Exception:
            return {}

    def get_was_closed_by_system(self, obj):
        return obj.is_disposition and not obj.conversation_disposition


class ReportConversationAPIView(APIView):
    permission_classes = [TienePermisoOML]
    authentication_classes = (SessionAuthentication, )

    def post(self, request, campaing_id):
        try:
            campaign = Campana.objects.get(id=campaing_id)
            params_serializer = ConversationFilterParamsSerializer(
                data={
                    'start_date': request.data.get('start_date'),
                    'end_date': request.data.get('end_date'),
                    'phone': request.data.get('phone'),
                    'agents': request.data.get('agents'),
                }
            )
            params_serializer.is_valid(raise_exception=True)
            params = params_serializer.save()
            chats = get_report_conversations_queryset(campaign, params)
            serializer = ConversacionInstagramFilterSerializer(chats, many=True)
            return response.Response(
                data=get_response_data(status=HttpResponseStatus.SUCCESS, data=serializer.data),
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR, data={}, message=_(str(e))
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ReportConversationDetailAPIView(APIView):
    permission_classes = [TienePermisoOML]
    authentication_classes = (SessionAuthentication, )

    def get(self, request, pk):
        try:
            conversation = _conversation_base_queryset().prefetch_related(
                _ordered_messages_prefetch()
            ).get(pk=pk)
            serializer = ConversacionInstagramSerializer(
                conversation, context={'request': request})
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    data=serializer.data,
                    message=_('Se obtuvo la conversacion de forma exitosa')),
                status=status.HTTP_200_OK)
        except ConversationInstagramApp.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Conversacion no encontrada')),
                status=status.HTTP_404_NOT_FOUND)


class ViewSet(viewsets.ModelViewSet):
    queryset = ConversationInstagramApp.objects.all()
    serializer_class = ConversacionInstagramSerializer
    authentication_classes = (SessionAuthentication, )
    permission_classes = (TienePermisoCanalInstagramAgente,)

    def get_queryset(self):
        return _conversation_base_queryset().filter(
            is_disposition=False
        ).order_by('-date_last_interaction')

    def get_detail_queryset(self):
        return _conversation_base_queryset().prefetch_related(
            _ordered_messages_prefetch()
        )

    def list(self, request):
        try:
            agente = request.user.get_agente_profile()
            agente_campanas = agente.get_campanas_activas_miembro().values_list(
                'queue_name__campana_id', flat=True)
            conversaciones = self.get_queryset()
            conversaciones_nuevas = conversaciones.filter(
                Q(agent=None, campana__id__in=agente_campanas) |
                Q(agent=agente, atendida=False)
            )
            conversaciones_en_curso = conversaciones.filter(agent=agente, atendida=True)
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se obtuvieron las conversaciones de forma exitosa'),
                    data={
                        'new_conversations': ConversacionInstagramSerializer(
                            conversaciones_nuevas, many=True,
                            context={'include_messages': False}).data,
                        'inprogress_conversations': ConversacionInstagramSerializer(
                            conversaciones_en_curso, many=True,
                            context={'include_messages': False}).data,
                    }),
                status=status.HTTP_200_OK)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al obtener las conversaciones')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, pk):
        try:
            instance = self.get_detail_queryset().get(pk=pk)
            instance.messages.mensajes_recibidos().update(status='read')
            serializer = ConversacionInstagramSerializer(
                instance, context={'request': request})
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    data=serializer.data,
                    message=_('Se obtuvo la conversacion de forma exitosa')),
                status=status.HTTP_200_OK)
        except ConversationInstagramApp.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Conversacion no encontrada')),
                status=status.HTTP_404_NOT_FOUND)

    @decorators.action(detail=True, methods=['post'])
    def attend_chat(self, request, pk):
        try:
            conversacion = self.get_detail_queryset().get(pk=pk)
            agente = request.user.get_agente_profile()
            if not conversacion.agent or conversacion.agent == agente:
                conversation_granted = conversacion.otorgar_conversacion(agente)
                mensajes = conversacion.messages.all()
                serializer_context = {
                    'request': request,
                    'contact_data': _get_contact_data(conversacion),
                }
                data = {
                    'conversation_granted': conversation_granted,
                    'conversation_data': ConversacionInstagramSerializer(
                        conversacion,
                        context={'request': request, 'include_messages': False},
                    ).data,
                    'messages': MessageInstagramAppSerializer(
                        mensajes, many=True, context=serializer_context).data,
                }
                agent_notifier = AgentNotifier()
                for agente_campana in conversacion.campana.obtener_agentes():
                    message = {
                        'chat_id': conversacion.id,
                        'campaign_id': conversacion.campana.pk,
                        'campaign_name': conversacion.campana.nombre,
                        'agent': agente_campana.user.pk,
                    }
                    agent_notifier.notify_instagram_chat_attended(
                        agente_campana.user_id, message)
                return response.Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS, data=data,
                        message=_('Se asignó la conversación de forma exitosa')),
                    status=status.HTTP_200_OK)
            return response.Response(
                data=get_response_data(
                    message=_('Esta conversación ya está siendo atendida por otro agente')),
                status=status.HTTP_401_UNAUTHORIZED)
        except ConversationInstagramApp.DoesNotExist:
            return response.Response(
                data=get_response_data(
                    message=_('No se puede asignar una conversación que no existe')),
                status=status.HTTP_404_NOT_FOUND)

    @decorators.action(detail=True, methods=["post"])
    def assign_contact(self, request, pk):
        try:
            contact_pk = request.data.get('contact_pk')
            conversacion = ConversationInstagramApp.objects.get(pk=pk)
            contact = Contacto.objects.get(pk=contact_pk)
            if contact.bd_contacto != conversacion.campana.bd_contacto:
                return response.Response(
                    data=get_response_data(
                        message=_('El contacto no pertenece a la base de datos de la campaña')),
                    status=status.HTTP_400_BAD_REQUEST)
            if contact.ig_scoped_id and contact.ig_scoped_id != conversacion.ig_scoped_id:
                return response.Response(
                    data=get_response_data(
                        message=_(
                            'El contacto ya está asociado a otro identificador de Instagram'
                        )),
                    status=status.HTTP_400_BAD_REQUEST)
            if ConversationInstagramApp.objects.filter(is_disposition=False)\
                    .filter(client_id=contact.pk, account_id=conversacion.account_id)\
                    .exclude(pk=conversacion.pk).exists():
                return response.Response(
                    data=get_response_data(
                        message=_('El contacto ya tiene una conversación activa')),
                    status=status.HTTP_400_BAD_REQUEST)
            if not contact.ig_scoped_id:
                contact.ig_scoped_id = conversacion.ig_scoped_id
                contact.save(update_fields=['ig_scoped_id'])
            conversacion.client = contact
            conversacion.save(update_fields=['client'])
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se asigno el contacto a la conversacion de forma satisfactoria')),
                status=status.HTTP_200_OK)
        except ConversationInstagramApp.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Conversación no encontrada')),
                status=status.HTTP_404_NOT_FOUND)
        except Contacto.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Contacto no encontrado')),
                status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al asignar el contacto')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'])
    def messages(self, request, pk):
        conversation = self.get_detail_queryset().get(pk=pk)
        if 'message_id' in request.GET:
            last_message = MessageInstagramApp.objects.get(id=request.GET['message_id'])
            mensajes = MessageInstagramApp.objects.filter(
                conversation=pk, timestamp__gte=last_message.timestamp
            ).order_by('timestamp', 'id')
        else:
            mensajes = conversation.messages.all()
        serializer_context = {
            'request': request,
            'contact_data': _get_contact_data(conversation),
        }
        data = {
            'messages': MessageInstagramAppSerializer(
                mensajes, many=True, context=serializer_context).data,
            'conversation_info': ConversacionInstagramSerializer(
                conversation,
                context={'request': request, 'include_messages': False},
            ).data,
        }
        return response.Response(
            data=get_response_data(status=HttpResponseStatus.SUCCESS, data=data),
            status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['post'])
    def send_message_text(self, request, pk):
        try:
            conversation = ConversationInstagramApp.objects.get(pk=pk)
            if not conversation.error:
                timestamp = timezone.now().astimezone(timezone.get_current_timezone())
                if conversation.is_active:
                    destination = conversation.ig_scoped_id
                    sender = request.user.get_agente_profile()
                    if not conversation.agent or conversation.agent != sender:
                        raise Exception(
                            _('Esta conversación ya está siendo atendida por otro agente'))
                    data = request.data.copy()
                    account = conversation.account
                    message = {"text": data['message'], "type": "text"}
                    message_id = send_text_message(account, destination, message)
                    if message_id:
                        mensaje = MessageInstagramApp.objects.create(
                            message_id=message_id,
                            conversation=conversation,
                            origen=account.ig_user_id,
                            timestamp=timestamp,
                            sender={"name": sender.user.username, "agent_id": sender.user.id},
                            content=message,
                            type="message",
                            status="sent",
                        )
                        serializer = MessageInstagramAppSerializer(mensaje)
                        return response.Response(
                            data=get_response_data(
                                status=HttpResponseStatus.SUCCESS,
                                data=serializer.data),
                            status=status.HTTP_200_OK)
                    raise Exception(_('Este mensaje no se pudo enviar'))
                return response.Response(
                    data=get_response_data(
                        message=_(
                            'La conversacion esta inactiva hasta que el cliente responda')),
                    status=status.HTTP_401_UNAUTHORIZED)
            return response.Response(
                data=get_response_data(message=_('Conversacion es erronea')),
                status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR, data={},
                    errors=str(e), message=_('Error al enviar el mensaje')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['post'])
    def send_message_attachment(self, request, pk):
        try:
            conversation = ConversationInstagramApp.objects.get(pk=pk)
            if not conversation.error:
                timestamp = timezone.now().astimezone(timezone.get_current_timezone())
                if conversation.is_active:
                    sender = request.user.get_agente_profile()
                    if not conversation.agent or conversation.agent != sender:
                        raise Exception(
                            _('Esta conversación ya está siendo atendida por otro agente'))
                    account = conversation.account
                    data = request.data.copy()
                    data.update({
                        "conversation": pk,
                        "message_id": "instagram-local-{}".format(uuid.uuid4()),
                        "sender": MESSAGE_SENDERS['AGENT'],
                    })
                    serializer = MessageInstagramAppAttachmentSerializer(data=data)
                    serializer.is_valid(raise_exception=True)
                    mensaje = serializer.save()
                    try:
                        filename = data['file'].name[:100]
                        file_type = get_type(filename)
                        media_path = mensaje.file.path
                        media_url = build_public_media_url(request, mensaje.file.url)
                        send_by_url_error = None
                        try:
                            message_id = send_media_message(
                                account, conversation.ig_scoped_id, file_type,
                                attachment_url=media_url)
                        except Exception as e:
                            send_by_url_error = e
                            if uses_instagram_login(account):
                                raise
                            message_id = None
                        if not message_id and not uses_instagram_login(account):
                            # Legacy Page Access Token flow: keep upload as fallback only.
                            try:
                                attachment_id = upload_media_to_meta(
                                    account, file_type, media_path, media_url)
                                if not attachment_id:
                                    raise Exception(_('No se pudo subir el archivo a Meta'))
                                message_id = send_media_message(
                                    account, conversation.ig_scoped_id, file_type,
                                    attachment_id=attachment_id)
                            except Exception as upload_error:
                                if send_by_url_error:
                                    raise Exception(
                                        '{}: {}; {}: {}'.format(
                                            _('Error al enviar adjunto por URL'),
                                            send_by_url_error,
                                            _('Error al subir archivo a Meta'),
                                            upload_error,
                                        ))
                                raise
                        if not message_id and send_by_url_error:
                            raise send_by_url_error
                    except Exception:
                        mensaje.delete()
                        raise
                    if message_id:
                        mensaje.message_id = message_id
                        mensaje.origen = account.ig_user_id
                        mensaje.timestamp = timestamp
                        mensaje.sender = {
                            "name": sender.user.username,
                            "agent_id": sender.user.id,
                        }
                        mensaje.content = {file_type: {"url": media_url}}
                        mensaje.type = file_type
                        mensaje.status = "sent"
                        mensaje.save()
                        serializer = MessageInstagramAppSerializer(mensaje)
                    else:
                        mensaje.delete()
                        raise Exception(_('Este mensaje no se pudo enviar'))
                    return response.Response(
                        data=get_response_data(
                            status=HttpResponseStatus.SUCCESS,
                            data=serializer.data),
                        status=status.HTTP_200_OK)
                return response.Response(
                    data=get_response_data(
                        message=_(
                            'La conversacion esta inactiva hasta que el cliente responda')),
                    status=status.HTTP_401_UNAUTHORIZED)
            return response.Response(
                data=get_response_data(message=_('Conversacion es erronea')),
                status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR, data={},
                    errors=str(e), message=_('Error al enviar el mensaje')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['post'])
    def send_message_template(self, request, pk):
        try:
            conversation = ConversationInstagramApp.objects.get(pk=pk)
            if not conversation.error:
                timestamp = timezone.now().astimezone(timezone.get_current_timezone())
                if conversation.is_active:
                    destination = conversation.ig_scoped_id
                    sender = request.user.get_agente_profile()
                    if not conversation.agent or conversation.agent != sender:
                        raise Exception(
                            _('Esta conversación ya está siendo atendida por otro agente'))
                    data = request.data.copy()
                    account = conversation.account
                    try:
                        template_data = PlantillaMessenger.objects.get(pk=data['template_id'])
                    except PlantillaMessenger.DoesNotExist:
                        template_data = PlantillaInstagram.objects.get(pk=data['template_id'])
                    message = template_data.configuracion
                    message_id = send_text_message(account, destination, message)
                    if message_id:
                        mensaje = MessageInstagramApp.objects.create(
                            message_id=message_id,
                            conversation=conversation,
                            origen=account.ig_user_id,
                            timestamp=timestamp,
                            sender={"name": sender.user.username, "agent_id": sender.user.id},
                            content=message,
                            type="message",
                            status="sent",
                        )
                        serializer = MessageInstagramAppSerializer(mensaje)
                        return response.Response(
                            data=get_response_data(
                                status=HttpResponseStatus.SUCCESS,
                                data=serializer.data),
                            status=status.HTTP_200_OK)
                    raise Exception(_('Este mensaje no se pudo enviar'))
                return response.Response(
                    data=get_response_data(
                        message=_(
                            'La conversacion esta inactiva hasta que el cliente responda')),
                    status=status.HTTP_401_UNAUTHORIZED)
            return response.Response(
                data=get_response_data(message=_('Conversacion es erronea')),
                status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR, data={},
                    errors=str(e), message=_('Error al enviar el mensaje')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['post'])
    def send_message_whatsapp_template(self, request, pk):
        return self.send_message_template(request, pk)

    @decorators.action(detail=True, methods=['post'])
    def reactive_expired_conversation(self, request, pk):
        return response.Response(
            data=get_response_data(
                message=_('La reactivación de conversaciones Instagram no está habilitada.')),
            status=status.HTTP_400_BAD_REQUEST)

    @decorators.action(detail=False, methods=['post'])
    def mark_as_read(self, request):
        try:
            message_ids = request.data
            if isinstance(message_ids, dict):
                if 'message_ids' in message_ids:
                    message_ids = message_ids['message_ids']
                elif 'message_id' in message_ids:
                    message_ids = [message_ids['message_id']]
                else:
                    message_ids = []
            if not isinstance(message_ids, list):
                message_ids = []
            MessageInstagramApp.objects.filter(id__in=message_ids).update(status='read')
            return response.Response(
                data=get_response_data(status=HttpResponseStatus.SUCCESS, data=[]),
                status=status.HTTP_200_OK)
        except Exception as e:
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR, data={}, message=_(str(e))),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
