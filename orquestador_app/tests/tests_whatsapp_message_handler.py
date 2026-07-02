# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import asyncio
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase

from orquestador_app.core.whatsapp.message_handler import handle_meta_messages


class HandleMetaMessagesTest(SimpleTestCase):

    def test_status_sent_without_conversation_does_not_fail(self):
        line = object()
        event = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "entry-id",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "5493513036130",
                            "phone_number_id": "961887093678879",
                        },
                        "statuses": [{
                            "id": "wamid.test",
                            "status": "sent",
                            "timestamp": "1774643340",
                            "recipient_id": "5493516571322",
                            "pricing": {
                                "billable": False,
                                "pricing_model": "PMP",
                                "category": "service",
                                "type": "free_customer_service",
                            },
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }

        with patch(
            "orquestador_app.core.whatsapp.message_handler.outbound_chat_event",
            new=AsyncMock(),
        ) as outbound_mock:
            asyncio.run(handle_meta_messages(line, event))

        outbound_mock.assert_awaited_once()
        self.assertIsNone(outbound_mock.await_args.kwargs["expire"])

    def test_media_message_preserves_caption(self):
        line = object()
        event = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "entry-id",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "5493513036130",
                            "phone_number_id": "961887093678879",
                        },
                        "contacts": [{
                            "profile": {"name": "Cliente"},
                            "wa_id": "5493516571322",
                        }],
                        "messages": [{
                            "from": "5493516571322",
                            "id": "wamid.media",
                            "timestamp": "1774643340",
                            "type": "image",
                            "image": {
                                "id": "media-id",
                                "mime_type": "image/jpeg",
                                "sha256": "media-sha",
                                "caption": "Prueba 2",
                            },
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }

        with patch(
            "orquestador_app.core.whatsapp.message_handler.meta_get_media_content",
            return_value={
                "type": "image",
                "previewUrl": "/media/archivos_whatsapp/media-id.jpg",
                "originalUrl": "/media/archivos_whatsapp/media-id.jpg",
                "url": "/media/archivos_whatsapp/media-id.jpg",
                "name": "media-id.jpg",
                "filename": "media-id.jpg",
            },
        ), patch(
            "orquestador_app.core.whatsapp.message_handler.inbound_chat_event",
            new=AsyncMock(),
        ) as inbound_mock:
            asyncio.run(handle_meta_messages(line, event))

        inbound_mock.assert_awaited_once()
        content = inbound_mock.await_args.args[4]
        self.assertEqual(content["caption"], "Prueba 2")
        self.assertEqual(inbound_mock.await_args.args[7], "image")
