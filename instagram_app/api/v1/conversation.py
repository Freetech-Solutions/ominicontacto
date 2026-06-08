import mimetypes

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import ugettext as _
from rest_framework import decorators, response, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication

from api_app.authentication import ExpiringTokenAuthentication
from api_app.services.media_url import build_public_media_url
from facebook_meta_app.models import PlantillaMessenger
from instagram_app.api.permissions import TienePermisoCanalInstagramAgente
from instagram_app.api.utils import HttpResponseStatus, get_response_data
from instagram_app.api.v1.message import (
    MessageInstagramAppAttachmentSerializer, MessageInstagramAppSerializer,
)
from instagram_app.models import (
    ConversationInstagramApp, MessageInstagramApp, PlantillaInstagram,
)
from notification_app.notification import AgentNotifier
from ominicontacto_app.models import Contacto
from orquestador_app.core.instagram.send_message import (
    send_media_message, send_text_message, upload_media_to_meta,
)

mimetypes.init()

MESSAGE_SENDERS = {
    'AGENT': 0,
    'CLIENT': 1,
}


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
    saliente = serializers.BooleanField(default=False)
    destination = serializers.CharField(source='ig_scoped_id', allow_null=True)
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
        return obj.messages.count()

    def get_message_unread(self, obj):
        return obj.messages.mensajes_recibidos().filter(status='delivered').count()

    def get_messages(self, obj):
        msgs = obj.messages.all().order_by('timestamp', 'id')
        return MessageInstagramAppSerializer(msgs, many=True).data

    def get_client(self, obj):
        if obj.client:
            return {
                'id': obj.client.id,
                'phone': obj.client.telefono,
                'page_client_id': obj.ig_scoped_id,
                'data': obj.client.obtener_datos(),
                'disposition': getattr(obj.client, 'last_disposition_id', None),
            }
        return None


class ViewSet(viewsets.ModelViewSet):
    queryset = ConversationInstagramApp.objects.all()
    serializer_class = ConversacionInstagramSerializer
    authentication_classes = (ExpiringTokenAuthentication, SessionAuthentication)
    permission_classes = (TienePermisoCanalInstagramAgente,)

    def get_queryset(self):
        return ConversationInstagramApp.objects.filter(
            is_disposition=False
        ).select_related(
            'campana',
            'account',
            'client',
            'agent',
        ).prefetch_related('messages').order_by('-date_last_interaction')

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
                            conversaciones_nuevas, many=True).data,
                        'inprogress_conversations': ConversacionInstagramSerializer(
                            conversaciones_en_curso, many=True).data,
                    }),
                status=status.HTTP_200_OK)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al obtener las conversaciones')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, pk):
        try:
            instance = self.get_queryset().get(pk=pk)
            instance.messages.mensajes_recibidos().update(status='read')
            serializer = ConversacionInstagramSerializer(instance)
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
            conversacion = ConversationInstagramApp.objects.get(pk=pk)
            agente = request.user.get_agente_profile()
            if not conversacion.agent or conversacion.agent == agente:
                conversation_granted = conversacion.otorgar_conversacion(agente)
                mensajes = conversacion.messages.all()
                data = {
                    'conversation_granted': conversation_granted,
                    'conversation_data': ConversacionInstagramSerializer(conversacion).data,
                    'messages': MessageInstagramAppSerializer(mensajes, many=True).data,
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
            if contact.instagram and contact.instagram != conversacion.ig_scoped_id:
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
            if not contact.instagram:
                contact.instagram = conversacion.ig_scoped_id
                contact.save(update_fields=['instagram'])
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
        conversation = ConversationInstagramApp.objects.get(pk=pk)
        if 'message_id' in request.GET:
            last_message = MessageInstagramApp.objects.get(id=request.GET['message_id'])
            mensajes = MessageInstagramApp.objects.filter(
                conversation=pk, timestamp__gte=last_message.timestamp).order_by('timestamp')
        else:
            mensajes = MessageInstagramApp.objects.filter(conversation=pk).order_by('timestamp')
        data = {
            'messages': MessageInstagramAppSerializer(mensajes, many=True).data,
            'conversation_info': ConversacionInstagramSerializer(conversation).data,
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
                    data.update({"conversation": pk, "sender": MESSAGE_SENDERS['AGENT']})
                    serializer = MessageInstagramAppAttachmentSerializer(data=data)
                    serializer.is_valid(raise_exception=True)
                    mensaje = serializer.save()
                    filename = data['file'].name[:100]
                    file_type = get_type(filename)
                    media_path = mensaje.file.path
                    media_url = build_public_media_url(request, mensaje.file.url)
                    attachment_id = upload_media_to_meta(account, file_type, media_path)
                    if not attachment_id:
                        mensaje.delete()
                        raise Exception(_('No se pudo subir el archivo a Meta'))
                    message_id = send_media_message(
                        account, conversation.ig_scoped_id, file_type, attachment_id)
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
