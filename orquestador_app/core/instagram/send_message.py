import json

import requests

from instagram_app.models import MessageInstagramApp


META_URL_SEND_MESSAGE = 'https://graph.facebook.com/v22.0/{}/messages'
META_URL_UPLOAD_ATTACHMENT = 'https://graph.facebook.com/v22.0/{}/message_attachments'


def _get_meta_response_error(response):
    try:
        return response.json()
    except ValueError:
        return response.text


def send_text_message(account, recipient_id, message_text):
    url = META_URL_SEND_MESSAGE.format(account.ig_user_id)
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


def upload_media_to_meta(account, type_file, file_path):
    url = META_URL_UPLOAD_ATTACHMENT.format(account.ig_user_id)
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


def send_media_message(account, recipient_id, type_file, attachment_id):
    url = META_URL_SEND_MESSAGE.format(account.ig_user_id)
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": type_file,
                "payload": {"attachment_id": attachment_id},
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
