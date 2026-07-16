# Copyright (C) 2026 Freetech Solutions
#
# This file is part of OMniLeads
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.

import json
import logging
import re

from django.core.files.storage import default_storage
from django.db.models import F, Func, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _
from rest_framework import decorators
from rest_framework import exceptions
from rest_framework import permissions
from rest_framework import response
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets

from ... import models
from ...service.outbound import send_reply
from notification_app.notification import AgentNotifier
from ominicontacto_app.models import (
    CalificacionCliente, OpcionCalificacion, RespuestaFormularioGestion)
# Shared, channel-agnostic disposition/contact serializers (they encode campaign
# calificación and contact-DB rules; they happen to live in whatsapp_app).
from whatsapp_app.api.v1.calificacion import (
    CreateSerializer as DispositionCreateSerializer,
    UpdateSerializer as DispositionUpdateSerializer,
    OpcionCalificacionSerializer,
    RespuestaFormularioGestionCreateSerilializer,
    RespuestaFormularioGestionUpdateSerilializer,
)
from whatsapp_app.api.v1.contacto import CreateSerializer as ContactCreateSerializer

log = logging.getLogger(__name__)

# matches src="cid:<content-id>" / src='cid:...' inside an HTML body
_CID_SRC_RE = re.compile(r'(src\s*=\s*["\'])cid:([^"\']+)(["\'])', re.IGNORECASE)


def rewrite_inline_cids(html, attachments):
    """Inline images in HTML mail reference attachments by Content-ID
    (``src="cid:xxx"``), which a browser cannot resolve. Rewrite those to the
    stored attachment URL so the images actually render in the agent console."""
    if not html or not attachments:
        return html or ""
    cid_to_url = {}
    for attachment in attachments:
        cid = (attachment.get("cid") or "").strip().strip("<>").strip()
        if cid and attachment.get("path"):
            cid_to_url[cid.lower()] = default_storage.url(attachment["path"])

    def _replace(match):
        url = cid_to_url.get(match.group(2).strip().lower())
        return "{0}{1}{2}".format(match.group(1), url, match.group(3)) if url \
            else match.group(0)

    return _CID_SRC_RE.sub(_replace, html)


class AgentPermission(permissions.IsAuthenticated):
    """Authenticated agent whose group has the email channel enabled."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        if not getattr(user, "is_agente", False):
            return False
        agente = user.get_agente_profile()
        if agente is None or agente.grupo is None:
            return False
        return bool(agente.grupo.email_habilitado)


class MessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    direction = serializers.CharField()
    date = serializers.DateTimeField()
    subject = serializers.CharField()
    from_mail = serializers.CharField()
    from_name = serializers.CharField()
    to_mail = serializers.CharField()
    to_name = serializers.CharField()
    body_html = serializers.SerializerMethodField()
    body_text = serializers.CharField()
    is_read = serializers.BooleanField()

    def get_body_html(self, message):
        return rewrite_inline_cids(message.body_html, message.attachments)
    status = serializers.CharField()
    type = serializers.CharField()
    sender = serializers.JSONField()
    attachments = serializers.SerializerMethodField()

    def get_attachments(self, message):
        return [
            {
                "cid": attachment["cid"],
                "name": attachment["name"],
                "url": default_storage.url(attachment["path"]),
            }
            for attachment in message.attachments
        ]


class ConversationListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    subject = serializers.CharField()
    client_mail = serializers.CharField()
    client_name = serializers.CharField()
    campana_id = serializers.IntegerField()
    agent_id = serializers.IntegerField()
    contacto_id = serializers.IntegerField()
    status = serializers.CharField()
    is_disposition = serializers.BooleanField()
    campaign_name = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    unread = serializers.SerializerMethodField()
    timestamp = serializers.DateTimeField()
    date_last_interaction = serializers.DateTimeField()

    def get_campaign_name(self, conversation):
        # campana is select_related + .only("campana__nombre") in the inbox
        # query, so this stays N+1-free; for a single un-scoped object it is at
        # most one extra query.
        return conversation.campana.nombre if conversation.campana_id else ""

    def get_messages(self, conversation):
        # uses the annotation set by the inbox list query (no N+1); falls back
        # to a count only for a single, un-annotated object (e.g. retrieve).
        value = getattr(conversation, "messages_count", None)
        if value is not None:
            return value
        return conversation.mensajes.count()

    def get_unread(self, conversation):
        value = getattr(conversation, "unread_count", None)
        if value is not None:
            return value
        return conversation.mensajes.filter(
            direction=models.Message.DIRECTION_INBOUND, is_read=False
        ).count()


class ConversationDetailSerializer(ConversationListSerializer):
    mensajes = MessageSerializer(many=True)


class ReplySerializer(serializers.Serializer):
    body_text = serializers.CharField(allow_blank=True, required=False, default="")
    body_html = serializers.CharField(allow_blank=True, required=False, default="")
    # extra recipients (comma/semicolon separated), like a regular mail client.
    cc = serializers.CharField(allow_blank=True, required=False, default="")
    bcc = serializers.CharField(allow_blank=True, required=False, default="")
    # unassign -> Respondido/Pendiente cliente; keep -> sigue en gestión;
    # dispose -> sigue en gestión y el front encadena la calificación.
    mode = serializers.ChoiceField(
        choices=["unassign", "keep", "dispose"], required=False, default="keep")

    def validate(self, attrs):
        if not (attrs.get("body_text") or attrs.get("body_html")):
            raise serializers.ValidationError(_("Provide a message body."))
        return attrs


class EmailContactCreateSerializer(ContactCreateSerializer):
    """Contact creation for the email channel: identical to the whatsapp one
    except the PHONE is optional. An email contact is identified by its address,
    so we don't force (nor validate) a phone number; the remaining mandatory
    fields are still enforced."""

    # Override Contacto.telefono it here so the field-level validation run
    # by ModelSerializer.to_internal_value keeps phone optional.
    telefono = serializers.CharField(required=False, allow_blank=True, max_length=128)

    def to_internal_value(self, data):
        metadata = self.campana.bd_contacto.get_metadata()
        campos_bd = metadata.nombres_de_columnas
        telefono = metadata.nombre_campo_telefono
        # phone is optional: take it if present and non-blank, validate only then
        telefono_val = data["datos"].pop(telefono, "") if telefono in data["datos"] else ""
        data["telefono"] = self.validar_telefono(telefono, telefono_val) if telefono_val else ""
        # required fields minus the phone column
        required = set(self.campana.get_campos_obligatorios()) - {telefono}
        if not set(data["datos"].keys()).issubset(set(campos_bd)):
            raise serializers.ValidationError(
                {"Error": _("Error en los campos de contacto")})
        if not set(data["datos"].keys()).issuperset(required):
            raise serializers.ValidationError({"Error": _("Faltan campos requeridos")})
        data["datos"] = self.get_datos_json(data["datos"])
        # skip ContactCreateSerializer.to_internal_value (which forces the phone)
        return serializers.ModelSerializer.to_internal_value(self, data)


class ViewSet(viewsets.ViewSet):
    permission_classes = [
        AgentPermission,
    ]

    def _agente(self, request):
        return request.user.get_agente_profile()

    def _agente_campana_ids(self, agente):
        return agente.get_campanas_activas_miembro().values_list(
            "queue_name__campana_id", flat=True
        )

    def _get_scoped(self, request, pk):
        """Fetch the conversation ensuring the agent may access it (belongs to
        one of the agent's campaigns, or is already assigned to the agent)."""
        agente = self._agente(request)
        try:
            conversation = models.ConversacionEmail.objects.get(pk=pk)
        except models.ConversacionEmail.DoesNotExist:
            raise exceptions.NotFound(_("The conversation does not exist."))
        campana_ids = set(self._agente_campana_ids(agente))
        if conversation.agent_id == agente.id or conversation.campana_id in campana_ids:
            return conversation, agente
        raise exceptions.PermissionDenied(
            _("You do not have access to this conversation.")
        )

    def _ensure_email_contacto(self, conversation):
        """Create a minimal Contacto from the conversation's sender email so an
        email conversation can be qualified without forcing the agent to fill a
        full contact form first. ``datos`` holds an empty value per data column
        (telefono/id_externo/email are stored on their own Contacto fields)."""
        from ominicontacto_app.models import Contacto
        bd = conversation.campana.bd_contacto
        metadata = bd.get_metadata()
        datos = json.dumps(["" for _ in metadata.nombres_de_columnas_de_datos])
        return Contacto.objects.create(
            bd_contacto=bd,
            telefono="",
            email=conversation.client_mail or "",
            datos=datos,
        )

    def _finalize(self, conversation, calificacion):
        conversation.is_disposition = True
        conversation.status = conversation.STATUS_CLOSED
        conversation.conversation_disposition = calificacion.history.first()
        conversation.save(
            update_fields=["is_disposition", "status", "conversation_disposition"]
        )

    def _save_form_response(self, calificacion, respuesta_formulario_gestion):
        formulario = calificacion.opcion_calificacion.formulario
        instance = RespuestaFormularioGestion.objects.filter(
            calificacion=calificacion).last()
        if instance:
            serializer = RespuestaFormularioGestionUpdateSerilializer(
                instance, {"metadata": respuesta_formulario_gestion}, partial=True)
        else:
            serializer = RespuestaFormularioGestionCreateSerilializer(
                data={"metadata": respuesta_formulario_gestion, "formulario": formulario})
        serializer.is_valid(raise_exception=True)
        serializer.save(calificacion=calificacion)

    # --- Inbox -------------------------------------------------------------

    def _inbox_queryset(self):
        """Lightweight, N+1-free queryset of conversation REFERENCES (no message
        bodies). Message/unread counts are computed as correlated subqueries so
        the cost is constant regardless of how many conversations are queued."""
        Conv = models.ConversacionEmail
        Msg = models.Message

        def count(**extra):
            sub = Msg.objects.filter(conversation_id=OuterRef("id"), **extra)
            sub = sub.annotate(c=Func(F("id"), function="Count")).values("c")
            return Coalesce(Subquery(sub, output_field=IntegerField()), 0)

        return Conv.objects.select_related("campana").only(
            "id", "subject", "client_mail", "client_name", "status",
            "is_disposition", "timestamp", "date_last_interaction",
            "campana_id", "agent_id", "contacto_id", "campana__nombre",
        ).annotate(
            messages_count=count(),
            unread_count=count(direction=Msg.DIRECTION_INBOUND, is_read=False),
        )

    def list(self, request):
        agente = self._agente(request)
        campana_ids = list(self._agente_campana_ids(agente))
        Conv = models.ConversacionEmail
        base = self._inbox_queryset()
        assigned = base.filter(agent=agente).exclude(status=Conv.STATUS_CLOSED)
        general = base.filter(agent=None, campana_id__in=campana_ids)
        general_new = general.filter(status__in=Conv.GENERAL_INBOX_QUEUED)
        general_waiting = general.filter(status__in=Conv.GENERAL_INBOX_WAITING)
        return response.Response(
            data={
                "assigned": ConversationListSerializer(assigned, many=True).data,
                "general": {
                    "new": ConversationListSerializer(general_new, many=True).data,
                    "waiting_client": ConversationListSerializer(
                        general_waiting, many=True).data,
                },
            }
        )

    def retrieve(self, request, pk):
        conversation, agente = self._get_scoped(request, pk)
        # SECURITY: an agent may only read the full thread of a conversation it
        # owns. Reading a conversation in the general inbox requires taking it
        # first (attend), which assigns it — otherwise an agent could read mail
        # without ever being assigned to it.
        if conversation.agent_id != agente.id:
            return response.Response(
                data={"detail": _("You must take this conversation before "
                                  "reading it.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        conversation.mark_in_progress()  # El agente lo abre -> En gestión
        return response.Response(data=ConversationDetailSerializer(conversation).data)

    # --- Asignación (inbox general -> personal) ----------------------------

    @decorators.action(detail=True, methods=["post"])
    def attend(self, request, pk):
        conversation, agente = self._get_scoped(request, pk)
        if conversation.agent_id not in (None, agente.id):
            return response.Response(
                data={"detail": _("This conversation is already being attended by "
                                  "another agent.")},
                status=status.HTTP_409_CONFLICT,
            )
        conversation.assign_to(agente)
        if conversation.campana_id:
            notifier = AgentNotifier()
            message = {
                "conversation_id": conversation.id,
                "campaign_id": conversation.campana_id,
                "agent": agente.user_id,
            }
            for other in conversation.campana.obtener_agentes():
                notifier.notify_email_conversation_attended(other.user_id, message)
        return response.Response(data=ConversationDetailSerializer(conversation).data)

    @decorators.action(detail=True, methods=["post"])
    def release(self, request, pk):
        """Devolver el correo a la cola general como NUEVO, sin responder
        (Desasignar). Reaparece en el inbox general de todos los agentes."""
        conversation, agente = self._get_scoped(request, pk)
        conversation.agent = None
        conversation.atendida = False
        conversation.is_disposition = False
        conversation.status = conversation.STATUS_NEW
        conversation.save(
            update_fields=["agent", "atendida", "is_disposition", "status"])
        if conversation.campana_id:
            notifier = AgentNotifier()
            message = {
                "conversation_id": conversation.id,
                "campaign_id": conversation.campana_id,
                "subject": conversation.subject,
                "from": conversation.client_name or conversation.client_mail,
            }
            for other in conversation.campana.obtener_agentes():
                notifier.send_email_message(
                    notifier.TYPE_EMAIL_NEW_CONVERSATION, message,
                    user_id=other.user_id)
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @decorators.action(detail=True, methods=["post"])
    def mark_as_read(self, request, pk):
        conversation, _agente = self._get_scoped(request, pk)
        conversation.mensajes.filter(
            direction=models.Message.DIRECTION_INBOUND, is_read=False
        ).update(is_read=True)
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    # --- Responder ---------------------------------------------------------

    @decorators.action(detail=True, methods=["post"])
    def reply(self, request, pk):
        conversation, agente = self._get_scoped(request, pk)
        serializer = ReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        files = request.FILES.getlist("attachments")
        try:
            send_reply(
                conversation,
                agente,
                serializer.validated_data["body_text"],
                serializer.validated_data["body_html"],
                files,
                mode=serializer.validated_data["mode"],
                cc=serializer.validated_data["cc"],
                bcc=serializer.validated_data["bcc"],
            )
        except Exception as exc:
            log.exception("email-reply conv=%r exception=%r", pk, exc)
            return response.Response(
                data={"detail": _("The email could not be sent.")},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        conversation.refresh_from_db()
        return response.Response(
            data=ConversationDetailSerializer(conversation).data,
            status=status.HTTP_201_CREATED,
        )

    # --- Calificar (cierra la interacción) ---------------------------------

    @decorators.action(detail=True, methods=["get"])
    def disposition_options(self, request, pk):
        conversation, _agente = self._get_scoped(request, pk)
        opciones = OpcionCalificacion.objects.filter(
            campana_id=conversation.campana_id, oculta=False)
        return response.Response(data=OpcionCalificacionSerializer(opciones, many=True).data)

    @decorators.action(detail=True, methods=["post"])
    def disposition(self, request, pk):
        conversation, agente = self._get_scoped(request, pk)
        if conversation.campana_id is None:
            return response.Response(
                data={"detail": _("The conversation has no campaign.")},
                status=status.HTTP_400_BAD_REQUEST)
        if conversation.contacto_id is None:
            # Email channel: a contact is identified by its address. Rather than
            # forcing the agent through the contact form before they can
            # qualify, auto-create a minimal contact from the sender's email
            # (the agent can still enrich it later via "Datos de contacto").
            conversation.contacto = self._ensure_email_contacto(conversation)
            conversation.save(update_fields=["contacto"])
        data = {
            "idContact": conversation.contacto_id,
            "idAgente": agente.pk,
            "idDispositionOption": request.data.get("idDispositionOption"),
            "subdispositionOption": request.data.get("subdispositionOption", "") or "",
            "comments": request.data.get("comments", "") or "",
        }
        serializer = DispositionCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        opcion = serializer.validated_data["opcion_calificacion"]
        contacto = serializer.validated_data["contacto"]
        existing = CalificacionCliente.objects.filter(
            contacto=contacto,
            opcion_calificacion__campana=opcion.campana).first()
        if existing:
            update = DispositionUpdateSerializer(existing, data={
                "idAgente": agente.pk,
                "idDispositionOption": opcion.pk,
                "subdispositionOption": serializer.validated_data.get("subcalificacion"),
                "comments": serializer.validated_data.get("observaciones"),
            }, partial=True)
            update.is_valid(raise_exception=True)
            calificacion = update.save()
        else:
            calificacion = serializer.save()
        calificacion.canalidad = CalificacionCliente.CANALIDAD_EMAIL
        calificacion.save(update_fields=["canalidad"])
        if opcion.tipo == OpcionCalificacion.GESTION:
            self._save_form_response(
                calificacion, request.data.get("respuestaFormularioGestion", {}))
        self._finalize(conversation, calificacion)
        return response.Response(data=ConversationDetailSerializer(conversation).data)

    # --- Guardar contacto en BD --------------------------------------------

    @decorators.action(detail=True, methods=["get"])
    def contact_fields(self, request, pk):
        conversation, _agente = self._get_scoped(request, pk)
        campana = conversation.campana
        if campana is None:
            return response.Response(data=[])
        metadata = campana.bd_contacto.get_metadata()
        telefono_field = metadata.nombre_campo_telefono
        data = []
        for index, name in enumerate(metadata.nombres_de_columnas):
            data.append({
                "name": name,
                # email channel: the phone is NOT mandatory (a mail contact is
                # identified by its address, not a phone number).
                "mandatory": name in campana.get_campos_obligatorios()
                and name != telefono_field,
                "block": name in campana.get_campos_no_editables(),
                "hide": name in campana.get_campos_ocultos(),
                "is_phone_field": index in metadata.columnas_con_telefono,
            })
        return response.Response(data=data)

    @decorators.action(detail=True, methods=["post"])
    def contact(self, request, pk):
        conversation, _agente = self._get_scoped(request, pk)
        campana = conversation.campana
        if campana is None:
            return response.Response(
                data={"detail": _("The conversation has no campaign.")},
                status=status.HTTP_400_BAD_REQUEST)
        request_data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        serializer = EmailContactCreateSerializer(
            data={"bd_contacto": campana.bd_contacto.id, "datos": request_data},
            context={"campana": campana})
        serializer.is_valid(raise_exception=True)
        client = serializer.save()
        conversation.contacto = client
        conversation.save(update_fields=["contacto"])
        return response.Response(
            data=ConversationDetailSerializer(conversation).data,
            status=status.HTTP_201_CREATED)
