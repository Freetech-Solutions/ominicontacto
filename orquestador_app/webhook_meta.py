# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

# This file is part of OMniLeads

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#
import json
import logging

from django.http import HttpResponse
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from ominicontacto_app.services.redis.redis_streams import RedisStreams
from orquestador_app.meta_webhook_signature import verify_meta_webhook_signature

from facebook_meta_app.models import PaginaMetaFacebook
from instagram_app.models import CuentaInstagram
from whatsapp_app.models import Linea, ConfiguracionProveedor

logger = logging.getLogger(__name__)


class WebhookMetaView(APIView):
    permission_classes = [AllowAny]

    def dispatch(self, request, *args, **kwargs):
        self.redis_stream = RedisStreams()
        return super(WebhookMetaView, self).dispatch(request, *args, **kwargs)

    def _get_linea(self, app_id):
        return Linea.objects.filter(
            proveedor__tipo_proveedor=ConfiguracionProveedor.TIPO_META,
            configuracion__contains={'app_id': app_id}
        ).first()

    def _get_payload(self, request, app_id):
        try:
            return json.loads(request.body.decode('utf-8'))
        except ValueError:
            logger.warning("Webhook Meta (app_id=%s): payload JSON invalido.", app_id)
            return None

    def _get_instagram_account(self, payload, app_id):
        entries = payload.get("entry", [])
        ig_user_id = entries[0].get("id") if entries else None
        if ig_user_id:
            account = CuentaInstagram.objects_default.filter(
                ig_user_id=ig_user_id,
                is_active=True,
            ).first()
            if account:
                return account
        return CuentaInstagram.objects_default.filter(app_id=app_id, is_active=True).first()

    def _get_facebook_page(self, payload, app_id):
        entries = payload.get("entry", [])
        page_id = entries[0].get("id") if entries else None
        if page_id:
            page = PaginaMetaFacebook.objects_default.filter(
                page_id=page_id,
                is_active=True,
            ).first()
            if page:
                return page
        return PaginaMetaFacebook.objects_default.filter(app_id=app_id, is_active=True).first()

    def _dispatch_instagram_payload(self, request, payload, app_id):
        account = self._get_instagram_account(payload, app_id)
        if account is None:
            logger.warning(
                "Webhook Meta (app_id=%s): payload Instagram recibido, "
                "pero no se encontro cuenta activa.",
                app_id,
            )
            return HttpResponse(status=status.HTTP_200_OK)
        if not verify_meta_webhook_signature(
                request, account.app_secret, app_id, 'Instagram'):
            return HttpResponse(status=status.HTTP_403_FORBIDDEN)
        self.redis_stream.write_stream(
            account.get_stream_name,
            request.body.decode('utf-8'),
            max_stream_length=100000,
        )
        logger.info(
            "Webhook Meta (app_id=%s): payload Instagram derivado al stream %s.",
            app_id,
            account.get_stream_name,
        )
        return HttpResponse(status=status.HTTP_200_OK)

    def _dispatch_facebook_payload(self, request, payload, app_id):
        page = self._get_facebook_page(payload, app_id)
        if page is None:
            logger.warning(
                "Webhook Meta (app_id=%s): payload Facebook Page recibido, "
                "pero no se encontro pagina activa.",
                app_id,
            )
            return HttpResponse(status=status.HTTP_200_OK)
        if not verify_meta_webhook_signature(
                request, page.app_secret, app_id, 'Facebook'):
            return HttpResponse(status=status.HTTP_403_FORBIDDEN)
        self.redis_stream.write_stream(
            page.get_stream_name,
            request.body,
            max_stream_length=100000,
        )
        logger.info(
            "Webhook Meta (app_id=%s): payload Facebook Page derivado al stream %s.",
            app_id,
            page.get_stream_name,
        )
        return HttpResponse(status=status.HTTP_200_OK)

    def _dispatch_non_whatsapp_payload(self, request, app_id):
        payload = self._get_payload(request, app_id)
        if payload is None:
            return None

        payload_object = payload.get("object")
        if payload_object == "instagram":
            return self._dispatch_instagram_payload(request, payload, app_id)
        if payload_object == "page":
            return self._dispatch_facebook_payload(request, payload, app_id)
        return None

    def _verify_signature(self, request, linea):
        """Validate WhatsApp with the same optional Meta signature policy."""
        app_secret = linea.configuracion.get('app_secret', '')
        return verify_meta_webhook_signature(
            request,
            app_secret,
            linea.configuracion.get('app_id'),
            'WhatsApp')

    def get(self, request, app_id):
        try:
            mode = request.GET.get("hub.mode", None)
            token = request.GET.get("hub.verify_token", None)
            challenge = request.GET.get("hub.challenge", None)
            if token:
                line_token = self._get_linea(app_id)
                if mode and line_token:
                    if mode == "subscribe" and \
                       token == line_token.configuracion['verification_token']:
                        return HttpResponse(challenge, status=status.HTTP_200_OK)
                return HttpResponse(challenge, status=status.HTTP_403_FORBIDDEN)
            else:
                return HttpResponse(challenge, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Error en verificacion GET webhook Meta: %s", e)
            return HttpResponse(status=status.HTTP_403_FORBIDDEN)

    def post(self, request, app_id):
        non_whatsapp_response = self._dispatch_non_whatsapp_payload(request, app_id)
        if non_whatsapp_response is not None:
            return non_whatsapp_response

        linea = self._get_linea(app_id)
        if linea is None:
            logger.warning("Webhook Meta: no se encontro Linea para app_id=%s", app_id)
            return HttpResponse(status=status.HTTP_200_OK)

        if not self._verify_signature(request, linea):
            return HttpResponse(status=status.HTTP_403_FORBIDDEN)

        stream_name = 'whatsapp_webhook_meta_{}'.format(app_id)
        self.redis_stream.write_stream(
            stream_name,
            request.body,
            max_stream_length=settings.WHATSAPP_WEBHOOK_STREAM_MAXLEN,
        )
        return HttpResponse(status=status.HTTP_200_OK)
