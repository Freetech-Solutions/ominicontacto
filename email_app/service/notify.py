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

log = logging.getLogger(__name__)


def _campaign_agent_user_ids(conversation):
    """User ids of the agents that belong to the conversation's campaign."""
    campana = conversation.campana
    if not campana:
        return []
    return [agente.user_id for agente in campana.obtener_agentes()]


async def notify_new_email_conversation(conversation, created, message):
    """Push the right realtime event for a freshly ingested inbound email so the
    agent console reacts like WhatsApp does. Two cases:

    * Unassigned + queued (new client mail, or a reopened thread the client
      wrote again after being answered/closed) -> ``email_new_conversation`` to
      every campaign agent, so it surfaces in the general inbox.
    * Already assigned to an agent (client replied while it is being managed)
      -> ``email_new_message`` to that agent, so their open thread / assigned
      tab updates and the unread badge grows ("respuestas sin responder").
    """
    if conversation.campana_id is None:
        return
    # imported lazily to avoid import-time coupling with notification_app
    from notification_app.notification import AgentNotifier

    notifier = AgentNotifier()

    if conversation.agent_id is None:
        if conversation.status not in conversation.GENERAL_INBOX_QUEUED:
            return
        user_ids = await sync_to_async(_campaign_agent_user_ids)(conversation)
        for user_id in user_ids:
            await notifier.notify_email_new_conversation(
                user_id, conversation=conversation)
        return

    # assigned conversation: notify only its owner of the new client reply
    agent = await sync_to_async(lambda: conversation.agent)()
    if agent is not None:
        await notifier.notify_email_new_message(agent.user_id, conversation)
