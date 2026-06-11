import json

import requests

from instagram_app.models import MessageInstagramApp


META_FACEBOOK_URL_SEND_MESSAGE = 'https://graph.facebook.com/v22.0/{}/messages'
META_FACEBOOK_URL_UPLOAD_ATTACHMENT = 'https://graph.facebook.com/v22.0/{}/message_attachments'
META_INSTAGRAM_URL_SEND_MESSAGE = 'https://graph.instagram.com/v22.0/me/messages'
META_INSTAGRAM_URL_UPLOAD_ATTACHMENT = \
    'https://graph.instagram.com/v22.0/{}/message_attachments'


def _get_meta_response_error(response):
    try:
        return response.json()
    except ValueError:
        return response.text


def uses_instagram_login(account):
    return account.access_token.startswith("IG")


def _get_send_message_url(account):
    if uses_instagram_login(account):
        return META_INSTAGRAM_URL_SEND_MESSAGE
    return META_FACEBOOK_URL_SEND_MESSAGE.format(account.page_id)


def _get_upload_attachment_url(account):
    if uses_instagram_login(account):
        return META_INSTAGRAM_URL_UPLOAD_ATTACHMENT.format(account.ig_user_id)
    return META_FACEBOOK_URL_UPLOAD_ATTACHMENT.format(account.page_id)


def _validate_recipient(account, recipient_id):
    if recipient_id == account.ig_user_id:
        raise Exception(
            "El destinatario Instagram corresponde a la cuenta propia, no al usuario final")


def send_text_message(account, recipient_id, message_text):
    _validate_recipient(account, recipient_id)
    url = _get_send_message_url(account)
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {"text": message_text["text"]},
    }
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        params={"access_token": account.access_token},
        json=payload)
    if response.ok:
        message_id = response.json().get('message_id')
        if message_id:
            return message_id
        raise Exception("Meta no devolvio message_id: {}".format(response.json()))
    raise Exception("Error enviando mensaje a Instagram: {} {}".format(
        response.status_code, _get_meta_response_error(response)))


def autoresponse_welcome(conversation, timestamp):
    try:
        if not conversation.account or not conversation.account.welcome_message:
            return
        message = conversation.account.welcome_message.configuracion
        if message:
            message_id = send_text_message(
                conversation.account, conversation.ig_scoped_id, message)
            if message_id:
                MessageInstagramApp.objects.get_or_create(
                    message_id=message_id,
                    conversation=conversation,
                    defaults={
                        'origen': conversation.account.ig_user_id,
                        'timestamp': timestamp,
                        'sender': {},
                        'content': message,
                        'type': "message",
                        'status': "sent",
                    }
                )
    except Exception as e:
        print("instagram autoresponse_welcome >>>>>>>>", e)


def autoresponse_goodbye(conversation, timestamp):
    try:
        if not conversation.account or not conversation.account.goodbye_message:
            return
        message = conversation.account.goodbye_message.configuracion
        if message:
            message_id = send_text_message(
                conversation.account, conversation.ig_scoped_id, message)
            if message_id:
                MessageInstagramApp.objects.get_or_create(
                    message_id=message_id,
                    conversation=conversation,
                    defaults={
                        'origen': conversation.account.ig_user_id,
                        'timestamp': timestamp,
                        'sender': {},
                        'content': message,
                        'type': "message",
                        'status': "sent",
                    }
                )
    except Exception as e:
        print("instagram autoresponse_goodbye >>>>>>>>", e)


def upload_media_to_meta(account, type_file, file_path=None, media_url=None):
    url = _get_upload_attachment_url(account)
    if media_url:
        response = requests.post(
            url,
            params={"access_token": account.access_token},
            json={
                "platform": "instagram",
                "message": {
                    "attachment": {
                        "type": type_file,
                        "payload": {
                            "is_reusable": True,
                            "url": media_url,
                        },
                    }
                },
            })
        if response.ok:
            attachment_id = response.json().get("attachment_id")
            if attachment_id:
                return attachment_id
            raise Exception("No se obtuvo attachment_id: {}".format(response.json()))
        raise Exception("Error al subir archivo a Meta: {} {}".format(
            response.status_code, response.text))
    if not file_path:
        raise Exception("No se indico file_path ni media_url para subir el archivo")
    with open(file_path, "rb") as uploaded_file:
        response = requests.post(
            url,
            params={"access_token": account.access_token},
            data={
                "message": json.dumps({
                    "attachment": {
                        "type": type_file,
                        "payload": {"is_reusable": True},
                    }
                })
            },
            files={"filedata": uploaded_file})
    if response.ok:
        attachment_id = response.json().get("attachment_id")
        if attachment_id:
            return attachment_id
        raise Exception("No se obtuvo attachment_id: {}".format(response.json()))
    raise Exception("Error al subir archivo a Meta: {} {}".format(
        response.status_code, response.text))


def send_media_message(account, recipient_id, type_file, attachment_id=None, attachment_url=None):
    _validate_recipient(account, recipient_id)
    if not attachment_id and not attachment_url:
        raise Exception("No se indico attachment_id ni attachment_url")
    url = _get_send_message_url(account)
    attachment_payload = {"url": attachment_url} if attachment_url else {
        "attachment_id": attachment_id}
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": type_file,
                "payload": attachment_payload,
            }
        },
    }
    response = requests.post(
        url,
        params={"access_token": account.access_token},
        json=payload)
    if response.ok:
        return response.json().get("message_id")
    raise Exception("Error enviando mensaje: {} {}".format(
        response.status_code, response.text))
