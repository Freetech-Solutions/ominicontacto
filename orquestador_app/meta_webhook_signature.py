# -*- coding: utf-8 -*-

import hashlib
import hmac
import logging


logger = logging.getLogger(__name__)


def verify_meta_webhook_signature(request, app_secret, app_id, channel):
    """Validate Meta's HMAC-SHA256 signature. Requests are rejected when no
    App Secret is configured for the page, account or line."""
    if not app_secret:
        logger.warning(
            "Webhook Meta %s (app_id=%s): no hay App Secret configurado. "
            "Se rechaza el request.",
            channel, app_id)
        return False

    signature_header = request.headers.get('X-Hub-Signature-256', '')
    if not signature_header:
        logger.warning(
            "Webhook Meta %s (app_id=%s): request sin header X-Hub-Signature-256.",
            channel, app_id)
        return False

    expected = 'sha256=' + hmac.new(
        app_secret.encode('utf-8'), request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature_header, expected):
        logger.warning(
            "Webhook Meta %s (app_id=%s): firma HMAC invalida. "
            "Posible solicitud no autorizada.",
            channel, app_id)
        return False

    return True
