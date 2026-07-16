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

from email.message import EmailMessage
from email.utils import parseaddr
from django.core.paginator import Page
from django.core.validators import EmailValidator
from django.db.models import Count
from django.utils.translation import gettext as _
from rest_framework import decorators
from rest_framework import exceptions
from rest_framework import pagination
from rest_framework import response
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets

from ... import models
from ...adapter import imaplib
from ...adapter import smtplib
from ...crypter import encrypt
from ..permissions import ViewPermission


def validate_email_address(value):
    name, email = parseaddr(value)
    EmailValidator()(email)
    if name:
        return f"{name} <{email}>"
    return email


def _build_test_message(config, to=None):
    """Minimal message used by the account 'Test de envío'. Sent to ``to`` (so
    the agent can verify reception off-server) or to the account itself when no
    address is given, confirming the full SMTP send path works."""
    message = EmailMessage()
    message["From"] = config["from_addr"]
    message["To"] = to or config["from_addr"]
    message["Subject"] = "OMniLeads - test de envío"
    message.set_content("Test de envío correcto desde OMniLeads.")
    return message


class Pagination(pagination.PageNumberPagination):
    page: Page
    page_size = 25

    def get_paginated_response(self, data):
        paginator = self.page.paginator
        return response.Response(
            data=pagination.OrderedDict(
                [
                    ("per_page", paginator.per_page),
                    ("total", paginator.count),
                    ("page", self.page.number),
                    ("results", data),
                ]
            )
        )


class InboundSerializer(serializers.Serializer):
    protocol = serializers.ChoiceField(choices=["imap+ssl"])
    host = serializers.CharField()
    port = serializers.IntegerField(min_value=0, max_value=65535)
    # NOTE: "xoauth2" (OAuth2) is not implemented yet; only basic auth is
    # supported (e.g. Gmail / Google Workspace via an App Password).
    auth_type = serializers.ChoiceField(choices=["basic"])
    username = serializers.CharField()
    password = serializers.CharField(allow_blank=True, write_only=True)
    fetch_mode = serializers.ChoiceField(choices=["idle", "poll"])
    idle_duration = serializers.IntegerField(min_value=180, max_value=1740)
    poll_interval = serializers.IntegerField(min_value=180, max_value=86400)
    mailbox = serializers.CharField()
    since = serializers.CharField(allow_blank=True)
    ssl_check_hostname = serializers.BooleanField()

    parent: "CreateSerializer | RetrieveSerializer"

    def validate_password(self, value):
        if self.parent.instance is None and value == "":
            self.fields["password"].fail("blank")
        return value


class OutboundSerializer(serializers.Serializer):
    protocol = serializers.ChoiceField(choices=["smtp+tls", "smtp+ssl"])
    host = serializers.CharField()
    port = serializers.IntegerField(min_value=0, max_value=65535)
    # NOTE: "xoauth2" (OAuth2) is not implemented yet; only basic auth is
    # supported (e.g. Gmail / Google Workspace via an App Password).
    auth_type = serializers.ChoiceField(choices=["basic"])
    username = serializers.CharField()
    password = serializers.CharField(allow_blank=True, write_only=True)
    from_addr = serializers.CharField(validators=[validate_email_address])
    # Outbound "From" display-name policy:
    #   from_name           -> general display name (e.g. "Equipo de Devops").
    #   include_agent_name  -> append the replying agent's name, mail-client
    #                          style: "Equipo de Devops (Marcelo Perez)".
    # The real address is always ``from_addr``.
    from_name = serializers.CharField(allow_blank=True, required=False, default="")
    include_agent_name = serializers.BooleanField(required=False, default=False)
    # Signature appended to the footer of every reply:
    #   signature_text   -> plain/rich text block.
    #   signature_image  -> optional PNG/JPG as a data-URI (or raw base64),
    #                       embedded inline (cid) in the HTML part.
    signature_text = serializers.CharField(
        allow_blank=True, required=False, default="")
    signature_image = serializers.CharField(
        allow_blank=True, required=False, default="")

    parent: "CreateSerializer | RetrieveSerializer"

    def validate_password(self, value):
        if self.parent.instance is None and value == "":
            self.fields["password"].fail("blank")
        return value


class ListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    active = serializers.BooleanField()
    messages = serializers.IntegerField()

    @classmethod
    def get_instance(cls):
        queryset = (
            models.Account.objects.only(
                "id",
                "name",
                "active",
            )
            .annotate(
                messages=Count("message"),
            )
            .order_by("id")
        )
        return cls(instance=queryset, many=True)


class CreateSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=100)
    active = serializers.BooleanField()
    inbound = InboundSerializer(source="settings.inbound")
    outbound = OutboundSerializer(source="settings.outbound")

    @classmethod
    def get_instance(cls, data):
        return cls(data=data)

    def create(self, validated_data):
        instance = models.Account()
        for attr, value in validated_data.items():
            if attr == "settings":
                for section in ("inbound", "outbound"):
                    value[section]["password"] = encrypt(value[section]["password"])
            setattr(instance, attr, value)
        instance.save()
        return instance


class RetrieveSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    active = serializers.BooleanField()
    inbound = InboundSerializer(source="settings.inbound")
    outbound = OutboundSerializer(source="settings.outbound")

    @classmethod
    def get_instance(cls, pk):
        queryset = models.Account.objects.only(
            "id",
            "name",
            "active",
            "settings",
        )
        instance = queryset.get(pk=pk)
        return cls(instance=instance)


class UpdateSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=100)
    active = serializers.BooleanField()
    inbound = InboundSerializer(source="settings.inbound")
    outbound = OutboundSerializer(source="settings.outbound")

    @classmethod
    def get_instance(cls, pk, data):
        queryset = models.Account.objects.only(
            "id",
            "name",
            "active",
            "settings",
        )
        instance = queryset.get(pk=pk)
        return cls(instance=instance, data=data, partial=True)

    def update(self, instance: models.Account, validated_data):
        for attr, value in validated_data.items():
            if attr == "settings":
                for section in ("inbound", "outbound"):
                    if value[section].get("password"):
                        value[section]["password"] = encrypt(value[section]["password"])
                    else:
                        value[section]["password"] = instance.settings[section]["password"]
            setattr(instance, attr, value)
        instance.save(update_fields=validated_data.keys())
        return instance


class AccountInUse(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "account_in_use"


class DestroySerializer(serializers.Serializer):
    instance: models.Account

    @classmethod
    def get_instance(cls, pk):
        queryset = models.Account.objects.only("id")
        instance = queryset.get(pk=pk)
        return cls(instance=instance)

    def destroy(self, **kwargs):
        campaigns = list(
            self.instance.campaign_accounts.values_list("campaign__nombre", flat=True)
        )
        if campaigns:
            raise AccountInUse(
                _(
                    "This account cannot be deleted because it is configured in the "
                    "following campaign(s): %(campaigns)s. Remove the account from "
                    "those campaigns before deleting it."
                )
                % {"campaigns": ", ".join(campaigns)}
            )
        self.instance.message_set.only("id").delete()
        self.instance.delete()


class MessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    date = serializers.DateTimeField()
    subject = serializers.CharField()
    from_mail = serializers.CharField()
    to_mail = serializers.CharField()

    @classmethod
    def get_instance(cls, request, pk):
        queryset = (
            models.Message.objects.filter(account=pk)
            .only(
                "id",
                "date",
                "subject",
                "from_mail",
                "to_mail",
            )
            .order_by("id")
        )
        pagination = Pagination()
        if page := pagination.paginate_queryset(queryset, request):
            return cls(instance=page, many=True, context={"pagination": pagination})
        return cls(instance=queryset, many=True)


class ResyncSerializer(serializers.Serializer):
    instance: models.Account

    active = serializers.BooleanField()

    @classmethod
    def get_instance(cls, pk):
        queryset = models.Account.objects.only("id")
        instance = queryset.get(pk=pk)
        return cls(instance=instance)

    def resync(self):
        self.instance.resync()


class PurgeHistorySerializer(serializers.Serializer):
    """Delete this account's local data (conversations + messages) and reset the
    fetch progress so the next sync re-downloads the inbox from the configured
    ``since`` date. Does NOT touch the IMAP server."""
    instance: models.Account

    id = serializers.IntegerField(read_only=True)
    deleted_messages = serializers.IntegerField(read_only=True)

    @classmethod
    def get_instance(cls, pk):
        instance = models.Account.objects.get(pk=pk)
        return cls(instance=instance)

    def purge(self):
        account = self.instance
        # messages first (FK message.conversation), then conversations
        deleted, _ = models.Message.objects.filter(account=account).delete()
        models.ConversacionEmail.objects.filter(account=account).delete()
        # reset the fetch marker -> next sync does a full re-fetch honouring SINCE
        account.insights = {}
        account.save(update_fields=["insights"])
        self._deleted_messages = deleted

    @property
    def data(self):
        return {"id": self.instance.pk, "deleted_messages": getattr(
            self, "_deleted_messages", 0)}


class TemplateSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=100, write_only=True)
    active = serializers.BooleanField(write_only=True)
    inbound = InboundSerializer(source="settings.inbound", write_only=True)
    outbound = OutboundSerializer(source="settings.outbound", write_only=True)

    @classmethod
    def get_instance(cls, pk, data):
        queryset = models.Account.objects.only(
            "name",
            "active",
            "settings",
        )
        template = queryset.get(pk=pk)
        return cls(data=data, context={"template": template}, partial=True)

    def validate(self, attrs):
        template = self.context["template"]
        for attr, value in attrs.items():
            if attr == "settings":
                for section in ("inbound", "outbound"):
                    if value[section].get("password"):
                        value[section]["password"] = encrypt(value[section]["password"])
                    else:
                        value[section]["password"] = template.settings[section]["password"]
        return attrs

    def create(self, validated_data):
        instance = models.Account()
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class TestSerializer(serializers.Serializer):
    instance: models.Account

    action = serializers.MultipleChoiceField(choices=["inbound", "outbound"], write_only=True)
    # optional destination for the outbound test send; defaults to from_addr
    # (send-to-self) when omitted.
    to = serializers.EmailField(required=False, allow_blank=True, write_only=True)
    inbound = serializers.JSONField(read_only=True)
    outbound = serializers.JSONField(read_only=True)
    roundtrip = serializers.JSONField(read_only=True)

    @classmethod
    def get_instance(cls, pk, data):
        queryset = models.Account.objects.all()
        instance = queryset.get(pk=pk)
        return cls(instance=instance, data=data)

    def validate(self, attrs):
        action = attrs.pop("action")
        test_to = attrs.pop("to", "") or None
        is_inbd_valid = None
        if not action or "inbound" in action:
            try:
                config = self.instance.settings["inbound"]
                client = imaplib.client(config, timeout=3)
                with client:
                    imaplib.login(client, config)
                    imaplib.examine_mailbox(client, config)
                    imaplib.validate_fetch_mode(client, config)
            except Exception as exc:
                is_inbd_valid = False
                attrs["inbound"] = {"ok": False, "errors": exc.args}
            else:
                is_inbd_valid = True
                attrs["inbound"] = {"ok": True}
        is_oubd_valid = None
        if not action or "outbound" in action:
            try:
                config = self.instance.settings["outbound"]
                client = smtplib.client(config, timeout=15)
                with client:
                    smtplib.login(client, config)
                    # real test send: exercises the full MAIL FROM / RCPT / DATA
                    # path (not just VRFY). Goes to the requested address (so it
                    # can be checked off-server) or to from_addr if none given.
                    smtplib.send(client, config, _build_test_message(config, test_to))
            except Exception as exc:
                is_oubd_valid = False
                attrs["outbound"] = {"ok": False, "errors": [str(a) for a in exc.args]}
            else:
                is_oubd_valid = True
                attrs["outbound"] = {"ok": True}
        if is_inbd_valid and is_oubd_valid:
            # send a beacon email with some secret and check if received in a timeout
            pass  # attrs["roundtrip"] = {"ok": None}
        return attrs


class ViewSet(viewsets.ViewSet):
    permission_classes = [
        ViewPermission,
    ]

    def list(self, request):
        serializer = ListSerializer.get_instance()
        return response.Response(data=serializer.data)

    def create(self, request):
        serializer = CreateSerializer.get_instance(request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk):
        serializer = RetrieveSerializer.get_instance(pk)
        self.check_object_permissions(request, serializer.instance)
        return response.Response(data=serializer.data)

    def update(self, request, pk):
        serializer = UpdateSerializer.get_instance(pk, request.data)
        self.check_object_permissions(request, serializer.instance)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(serializer.data)

    def destroy(self, request, pk):
        serializer = DestroySerializer.get_instance(pk)
        self.check_object_permissions(request, serializer.instance)
        serializer.destroy()
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @decorators.action(detail=True)
    def messages(self, request, pk):
        serializer = MessageSerializer.get_instance(request, pk)
        self.check_object_permissions(request, serializer.instance)
        if pagination := serializer.context.get("pagination"):
            return pagination.get_paginated_response(serializer.data)
        return response.Response(data=serializer.data)

    @decorators.action(detail=True, methods=["post"])
    def resync(self, request, pk):
        serializer = ResyncSerializer.get_instance(pk)
        self.check_object_permissions(request, serializer.instance)
        serializer.resync()
        return response.Response(data=serializer.data)

    @decorators.action(detail=True, methods=["post"])
    def purge_history(self, request, pk):
        serializer = PurgeHistorySerializer.get_instance(pk)
        self.check_object_permissions(request, serializer.instance)
        serializer.purge()
        return response.Response(data=serializer.data)

    @decorators.action(detail=True, methods=["post"])
    def template(self, request, pk):
        serializer = TemplateSerializer.get_instance(pk, request.data)
        self.check_object_permissions(request, serializer.instance)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(data=serializer.data)

    @decorators.action(detail=True, methods=["post"])
    def test(self, request, pk):
        serializer = TestSerializer.get_instance(pk, request.data)
        self.check_object_permissions(request, serializer.instance)
        serializer.is_valid(raise_exception=True)
        return response.Response(data=serializer.validated_data)
