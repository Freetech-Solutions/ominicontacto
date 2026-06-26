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

import logging
from email.message import EmailMessage
from email.utils import formataddr
from email.utils import formatdate
from email.utils import make_msgid
from hashlib import sha256

from django.utils import timezone

from ..adapter import smtplib
from ..models import Message

log = logging.getLogger(__name__)


def build_from_header(config, agente=None):
    """Compose the ``From`` header per the account's display-name policy.

    The real address is always ``config['from_addr']``. The display name is,
    in order of preference:
        from_name + agent     -> "Equipo de Devops (Marcelo Perez)"
        from_name only        -> "Equipo de Devops"
        agent only            -> "Marcelo Perez"
        neither               -> no display name (bare address)
    """
    addr = config["from_addr"]
    general = (config.get("from_name") or "").strip()
    agent_name = ""
    if config.get("include_agent_name") and agente is not None:
        agent_name = (agente.user.get_full_name() or agente.user.username or "").strip()
    if general and agent_name:
        display = "{0} ({1})".format(general, agent_name)
    else:
        display = general or agent_name
    return formataddr((display, addr)) if display else addr


def build_reply_mime(config, conversation, last_inbound, body_text, body_html,
                     files=(), cc="", bcc="", agente=None):
    """Build the outbound reply as an EmailMessage, carrying the threading
    headers (In-Reply-To/References) so the reply stays in the same thread.

    ``cc``/``bcc`` are optional extra recipients (comma/semicolon separated).
    The Bcc header is honoured by smtplib.send_message (it computes the envelope
    recipients from To/Cc/Bcc and strips Bcc before sending)."""
    message = EmailMessage()
    message["From"] = build_from_header(config, agente)
    message["To"] = conversation.client_mail
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    subject = conversation.subject or ""
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject if subject else "Re:"
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    if last_inbound and last_inbound.message_id:
        message["In-Reply-To"] = last_inbound.message_id
        references = list(last_inbound.references or [])
        references.append(last_inbound.message_id)
        message["References"] = " ".join(references)

    message.set_content(body_text or "")
    if body_html:
        message.add_alternative(body_html, subtype="html")

    for upload in files:
        content_type = getattr(upload, "content_type", "") or "application/octet-stream"
        maintype, _, subtype = content_type.partition("/")
        message.add_attachment(
            upload.read(),
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=upload.name,
        )
    return message


def deliver(config, message):
    """Connect, authenticate and hand the message to the SMTP server. Isolated
    so it can be mocked in tests."""
    client = smtplib.client(config)
    with client:
        smtplib.login(client, config)
        smtplib.send(client, config, message)


def send_reply(conversation, agente, body_text, body_html, files=(), mode="keep",
               cc="", bcc=""):
    """Send an agent reply on a conversation and persist it as an outbound
    Message (parsed through the same hydrate() pipeline as inbound mail).

    ``mode`` drives the lifecycle transition:
        "unassign" -> Respondido / Pendiente cliente: released to the campaign
                      general inbox (agent cleared, status=answered).
        "keep"     -> En gestión: the agent keeps the conversation (status=in_progress).
        "dispose"  -> like "keep"; the caller chains a disposition that closes it.
    """
    account = conversation.account
    config = account.settings["outbound"]
    last_inbound = (
        conversation.mensajes.filter(direction=Message.DIRECTION_INBOUND)
        .order_by("id")
        .last()
    )
    mime = build_reply_mime(
        config, conversation, last_inbound, body_text, body_html, files,
        cc=cc, bcc=bcc, agente=agente)
    deliver(config, mime)

    raw = bytes(mime)
    message = Message.objects.create(
        account=account,
        conversation=conversation,
        direction=Message.DIRECTION_OUTBOUND,
        content_bytes=raw,
        content_stamp=sha256(raw).hexdigest(),
        mailbox_uidva="",
        sender={
            "name": agente.user.get_full_name() or agente.user.username,
            "agent_id": agente.user_id,
        },
        status="sent",
        type=Message.TYPE_EMAIL,
    )
    # reuse the inbound parser to populate subject/body/attachments/etc.
    message.hydrate()

    conversation.date_last_interaction = timezone.now()
    if mode == "unassign":
        conversation.agent = None
        conversation.atendida = False
        conversation.status = conversation.STATUS_ANSWERED
    else:  # "keep" / "dispose": the agent retains the conversation
        conversation.agent = agente
        conversation.atendida = True
        conversation.status = conversation.STATUS_IN_PROGRESS
    conversation.save(
        update_fields=["date_last_interaction", "agent", "atendida", "status"]
    )
    return message
