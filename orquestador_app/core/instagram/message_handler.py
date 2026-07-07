import logging
from datetime import datetime

from asgiref.sync import sync_to_async
from django.utils import timezone

from configuracion_telefonia_app.models import DestinoEntrante
from instagram_app.models import ConversationInstagramApp, MessageInstagramApp
from orquestador_app.core.instagram.send_message import autoresponse_welcome
from orquestador_app.core.notify_agents import send_notify


logger = logging.getLogger(__name__)


async def instagram_handler_messages(account, payloads):
    for entry in payloads.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            if _is_outgoing_echo(account, messaging_event):
                logger.info("Instagram echo ignorado: %r", messaging_event)
                continue
            data = _parse_messaging_event(messaging_event)
            if data:
                notifications = await _save_inbound_message(account, **data)
                for ntype, nargs in notifications:
                    await send_notify(ntype, **nargs)


def _get_timestamp(messaging_event):
    timestamp = messaging_event.get("timestamp")
    if timestamp:
        return datetime.fromtimestamp(
            int(timestamp) / 1000,
            timezone.get_current_timezone())
    return timezone.now().astimezone(timezone.get_current_timezone())


def _is_outgoing_echo(account, messaging_event):
    sender_id = messaging_event.get("sender", {}).get("id")
    message = messaging_event.get("message", {})
    return sender_id == account.ig_user_id or message.get("is_echo")


def _parse_messaging_event(messaging_event):
    sender_id = messaging_event.get("sender", {}).get("id")
    if not sender_id:
        logger.warning("Instagram event sin sender id: %r", messaging_event)
        return None

    timestamp = _get_timestamp(messaging_event)
    sender = {"id": sender_id}
    file = None

    if "message" in messaging_event:
        message = messaging_event["message"]
        message_id = message.get("mid") or "instagram-{}-{}".format(
            sender_id, messaging_event.get("timestamp", timestamp.timestamp()))
        message_type = "message"
        content = {}
        if "text" in message:
            content = {"text": message["text"]}
        elif message.get("attachments"):
            attachment = message["attachments"][0]
            message_type = attachment.get("type", "attachment")
            attachment_payload = attachment.get("payload", {})
            content = {message_type: attachment_payload}
            file = attachment_payload.get("url")
        if "quick_reply" in message:
            message_type = "quick_reply"
            content = {
                "text": message.get("text", ""),
                "quick_reply": message.get("quick_reply", {}),
            }
        return {
            "timestamp": timestamp,
            "message_id": message_id,
            "origen": sender_id,
            "content": content,
            "sender": sender,
            "message_type": message_type,
            "file": file,
        }

    if "postback" in messaging_event:
        postback = messaging_event["postback"]
        return {
            "timestamp": timestamp,
            "message_id": postback.get("mid") or "instagram-postback-{}-{}".format(
                sender_id, messaging_event.get("timestamp", timestamp.timestamp())),
            "origen": sender_id,
            "content": {"postback": postback},
            "sender": sender,
            "message_type": "postback",
            "file": None,
        }

    logger.info("Instagram event ignorado: %r", messaging_event)
    return None


@sync_to_async
def _save_inbound_message(account, timestamp, message_id, origen, content,
                          sender, message_type, file=None):
    notifications = []
    message, created_message = MessageInstagramApp.objects.get_or_create(
        message_id=message_id,
        defaults={
            "origen": origen,
            "timestamp": timestamp,
            "sender": sender,
            "content": content,
            "type": message_type,
            "file": file,
            "status": "delivered",
        })

    if not created_message and message.conversation:
        return notifications

    destination = account.destination
    campana = None
    if destination and destination.tipo == DestinoEntrante.CAMPANA:
        campana = destination.content_object

    conversation = ConversationInstagramApp.objects.filter(
        account=account,
        ig_scoped_id=origen,
        is_disposition=False,
    ).last()
    created_conversation = False
    if not conversation:
        expire = (
            timestamp + timezone.timedelta(days=1)
        ) - timezone.timedelta(seconds=timestamp.second, microseconds=timestamp.microsecond)
        conversation = ConversationInstagramApp.objects.create(
            account=account,
            client=None,
            campana=campana,
            ig_scoped_id=origen,
            is_active=True,
            agent=None,
            expire=expire,
            timestamp=timestamp,
            date_last_interaction=timestamp,
            client_alias=sender.get("name", ""),
        )
        created_conversation = True
        autoresponse_welcome(conversation, timestamp)
    else:
        update_fields = ["date_last_interaction", "is_active", "updated_at"]
        conversation.date_last_interaction = timestamp
        conversation.updated_at = timezone.now()
        if not conversation.is_active:
            conversation.is_active = True
        if campana and not conversation.campana:
            conversation.campana = campana
            update_fields.append("campana")
        conversation.save(update_fields=update_fields)

    message.conversation = conversation
    message.save(update_fields=["conversation"])
    conversation.last_message = message
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=["last_message", "updated_at"])
    if (created_conversation or created_message) and conversation.campana \
            and not conversation.agent:
        notifications.append(('notify_instagram_new_chat', {
            'conversation': conversation,
        }))
    elif created_message and conversation.agent:
        notifications.append(('notify_instagram_new_message', {
            'conversation': conversation,
            'account': account,
            'message': message,
        }))
    return notifications
