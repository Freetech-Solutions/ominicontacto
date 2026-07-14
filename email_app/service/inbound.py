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

from asgiref.sync import sync_to_async
from django.utils import timezone

# NOTE: import the package, not the name. This module is reachable while
# email_app.models is still being initialized (account.py -> EmailFetchService
# -> consumer -> inbound), so binding the partially-initialized package object
# is safe whereas `from ..models import ConversacionEmail` would raise an
# ImportError. The model is resolved at call time, when init has completed.
from .. import models

log = logging.getLogger(__name__)


def _match_contacto(campana, client_mail):
    """Best-effort match of an existing campaign contact by email. Never raises
    (a matching failure must not break ingestion)."""
    if not (campana and client_mail):
        return None
    try:
        return campana.bd_contacto.contactos.filter(email__iexact=client_mail).first()
    except Exception:
        log.exception("email contacto-match failed campana=%r", getattr(campana, "pk", None))
        return None


def ingest_inbound_message(message):
    """Group a freshly fetched inbound ``Message`` into its ``ConversacionEmail``
    (campaign general inbox). Returns ``(conversation, created)``.

    Runs synchronously — call via ``sync_to_async`` from the async fetch loop.
    """
    account = message.account
    campaign_account = account.campaign_accounts.select_related("campaign").first()
    campana = campaign_account.campaign if campaign_account else None

    thread_key = message.thread_key()
    conversation, created = models.ConversacionEmail.objects.get_or_create(
        account=account,
        thread_key=thread_key,
        defaults={
            "campana": campana,
            "subject": message.subject or "",
            "client_mail": message.from_mail or "",
            "client_name": message.from_name or "",
            "contacto": _match_contacto(campana, message.from_mail),
            "timestamp": message.date or timezone.now(),
        },
    )

    message.conversation = conversation
    message.direction = message.DIRECTION_INBOUND
    message.save(update_fields=["conversation", "direction"])

    conversation.date_last_interaction = message.date or timezone.now()
    conversation.is_active = True
    update_fields = ["date_last_interaction", "is_active"]
    if not created and conversation.status in models.ConversacionEmail.REOPENABLE:
        # client wrote again after the agent answered/closed: reopen and send it
        # back to the campaign general inbox (Reabierto / En cola).
        conversation.status = models.ConversacionEmail.STATUS_REOPENED
        conversation.agent = None
        conversation.atendida = False
        conversation.is_disposition = False
        update_fields += ["status", "agent", "atendida", "is_disposition"]
    conversation.save(update_fields=update_fields)
    return conversation, created


async def aingest_inbound_message(message):
    return await sync_to_async(ingest_inbound_message)(message)
