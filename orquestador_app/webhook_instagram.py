import logging
import json

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from instagram_app.models import CuentaInstagram
from ominicontacto_app.services.redis.redis_streams import RedisStreams


logger = logging.getLogger(__name__)


class WebhookInstagramView(APIView):
    permission_classes = [AllowAny]

    def dispatch(self, request, *args, **kwargs):
        self.redis_stream = RedisStreams()
        return super(WebhookInstagramView, self).dispatch(request, *args, **kwargs)

    def _get_account(self, app_id):
        return CuentaInstagram.objects_default.filter(app_id=app_id, is_active=True).first()

    def _get_account_from_payload(self, payload, app_id):
        entries = payload.get("entry", [])
        ig_user_id = entries[0].get("id") if entries else None
        if ig_user_id:
            account = CuentaInstagram.objects_default.filter(
                ig_user_id=ig_user_id, is_active=True).first()
            if account:
                return account
        return self._get_account(app_id)

    def get(self, request, app_id):
        challenge = request.GET.get("hub.challenge", None)
        try:
            mode = request.GET.get("hub.mode", None)
            token = request.GET.get("hub.verify_token", None)
            account = self._get_account(app_id)
            if mode == "subscribe" and account and token == account.verify_token:
                if not account.validated:
                    account.validated = True
                    account.save(update_fields=["validated"])
                return HttpResponse(challenge, status=status.HTTP_200_OK)
            return HttpResponse(challenge, status=status.HTTP_403_FORBIDDEN)
        except Exception as exception:
            logger.exception("Error en webhook Instagram: %s", exception)
            return HttpResponse(challenge, status=status.HTTP_403_FORBIDDEN)

    def post(self, request, app_id):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except ValueError:
            logger.warning("Webhook Instagram: payload invalido app_id=%s", app_id)
            return HttpResponse(status=status.HTTP_200_OK)
        account = self._get_account_from_payload(payload, app_id)
        if account is None:
            logger.warning("Webhook Instagram: no se encontro cuenta para app_id=%s", app_id)
            return HttpResponse(status=status.HTTP_200_OK)
        self.redis_stream.write_stream(
            account.get_stream_name, request.body.decode("utf-8"), max_stream_length=100000)
        return HttpResponse(status=status.HTTP_200_OK)
