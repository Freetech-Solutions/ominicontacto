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

import base64
import logging
from email.utils import parseaddr
from os import path
import mailparser
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone

from ._utils import TruncatedCharField
from ._utils import alters_data

log = logging.getLogger(__name__)


hydrated_fields = [
    "date",
    "subject",
    "from_mail",
    "from_name",
    "to_mail",
    "to_name",
    "body_html",
    "body_text",
    "message_id",
    "in_reply_to",
    "references",
    "attachments",
]


def parse(self: "Message"):
    # content_bytes may be a memoryview (read back from a BinaryField via
    # psycopg2), a bytearray (freshly fetched from IMAP before any DB
    # round-trip) or plain bytes. bytes() normalizes all of them.
    content = bytes(self.content_bytes)

    date = timezone.now()
    subject = ""
    from_name = ""
    from_mail = ""
    to_name = ""
    to_mail = ""
    body_html = ""
    body_text = ""
    message_id = ""
    in_reply_to = ""
    references = []
    attachments = []
    try:
        message = mailparser.parse_from_bytes(content)
        if message.date:
            date = message.date
        subject = message.subject
        if message.from_:
            from_name, from_mail = message.from_[0]
        elif message.return_path:
            from_name, from_mail = parseaddr(message.return_path)
        if message.to:
            to_name, to_mail = message.to[0]
        body_html = "".join(message.text_html)
        body_text = "".join(message.text_plain)
        if isinstance(message.message_id, list):
            message_id = message.message_id[0]
        elif message.message_id:
            message_id = message.message_id
        in_reply_to = message.in_reply_to
        references = message.references.split()
        attachments = [
            {
                "cid": attachment["content-id"],
                "name": attachment["filename"],
                "path": default_storage.save(
                    path.join(
                        path.normpath(settings.MEDIA_ROOT),
                        "email",
                        "message",
                        message_id,
                        "attachments",
                        attachment["filename"],
                    ),
                    ContentFile(base64.b64decode(attachment["payload"]))
                    if attachment["binary"]
                    else ContentFile(attachment["payload"]),
                ),
            }
            for attachment in message.attachments
        ]
    except Exception:
        log.exception("message:parse-error id=%r", self.pk)
    return {
        "date": date,
        "subject": subject,
        "from_mail": from_mail,
        "from_name": from_name,
        "to_mail": to_mail,
        "to_name": to_name,
        "body_html": body_html,
        "body_text": body_text,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "attachments": attachments,
    }


class QuerySet(models.QuerySet):
    @alters_data
    async def acreate(self, **kwargs):
        return await sync_to_async(self.create)(**kwargs)

    @alters_data
    async def aget_or_create(self, defaults=None, **kwargs):
        return await sync_to_async(self.get_or_create)(defaults=defaults, **kwargs)

    @alters_data
    async def aupdate_or_create(self, defaults=None, **kwargs):
        return await sync_to_async(self.update_or_create)(defaults=defaults, **kwargs)

    def hydrate(self):
        for obj in self:
            parsed_data = parse(obj)
            for attr, value in parsed_data.items():
                setattr(obj, attr, value)
        return self.bulk_update(self, hydrated_fields, batch_size=50)


class Message(models.Model):
    DIRECTION_INBOUND = "inbound"
    DIRECTION_OUTBOUND = "outbound"
    DIRECTION_CHOICES = (
        (DIRECTION_INBOUND, "inbound"),
        (DIRECTION_OUTBOUND, "outbound"),
    )

    TYPE_EMAIL = "email"
    TYPE_TRANSFER_EVENT = "transfer_event"

    account = models.ForeignKey("email_app.Account", on_delete=models.PROTECT)

    # agent-channel: thread this message belongs to (null for legacy/admin-only
    # messages that were never grouped into a conversation).
    conversation = models.ForeignKey(
        "email_app.ConversacionEmail",
        on_delete=models.CASCADE,
        related_name="mensajes",
        null=True,
    )
    direction = models.CharField(
        max_length=10, choices=DIRECTION_CHOICES, default=DIRECTION_INBOUND
    )
    is_read = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="received")
    fail_reason = models.CharField(max_length=254, blank=True, default="")
    # outbound/system author: {"name": ..., "agent_id": ...}; empty for inbound.
    sender = models.JSONField(default=dict)
    type = models.CharField(max_length=20, default=TYPE_EMAIL)

    content_bytes = models.BinaryField()
    content_stamp = models.CharField(max_length=64)
    mailbox_uidva = models.CharField(max_length=100)

    date = models.DateTimeField(null=True)
    subject = TruncatedCharField(max_length=254)
    from_mail = models.CharField(max_length=254)
    from_name = models.CharField(max_length=100)
    to_mail = models.CharField(max_length=254)
    to_name = models.CharField(max_length=100)
    body_html = models.TextField()
    body_text = models.TextField()
    message_id = models.CharField(max_length=254)
    in_reply_to = models.CharField(max_length=254)
    references = ArrayField(models.CharField(max_length=254), default=list)
    attachments = models.JSONField(default=list)

    objects = QuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["content_stamp"], name="email_app-content_stamp-idx"),
        ]

    def thread_key(self):
        """Stable key used to group messages into a ConversacionEmail. Uses the
        root of the References chain, then In-Reply-To, then this message's own
        Message-ID (a brand-new thread is its own root)."""
        if self.references:
            return self.references[0]
        if self.in_reply_to:
            return self.in_reply_to
        return self.message_id

    @alters_data
    async def asave(self, **kwargs):
        return await sync_to_async(self.save)(**kwargs)

    def hydrate(self):
        parsed_data = parse(self)
        for attr, value in parsed_data.items():
            setattr(self, attr, value)
        self.save(update_fields=hydrated_fields)
