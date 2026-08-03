# -*- coding: utf-8 -*-

import hashlib
import hmac
from types import SimpleNamespace

from django.test import SimpleTestCase

from orquestador_app.meta_webhook_signature import verify_meta_webhook_signature


class MetaWebhookSignatureTests(SimpleTestCase):

    app_id = 'meta-app-id'
    app_secret = 'meta-app-secret'
    body = b'{"object":"page"}'

    def _request(self, signature=None):
        headers = {}
        if signature is not None:
            headers['X-Hub-Signature-256'] = signature
        return SimpleNamespace(headers=headers, body=self.body)

    def test_allows_request_when_app_secret_is_null(self):
        self.assertTrue(verify_meta_webhook_signature(
            self._request(), None, self.app_id, 'Facebook'))

    def test_allows_request_when_app_secret_is_empty(self):
        self.assertTrue(verify_meta_webhook_signature(
            self._request(), '', self.app_id, 'Instagram'))

    def test_accepts_valid_signature(self):
        digest = hmac.new(
            self.app_secret.encode('utf-8'), self.body, hashlib.sha256).hexdigest()

        self.assertTrue(verify_meta_webhook_signature(
            self._request('sha256=' + digest),
            self.app_secret,
            self.app_id,
            'Facebook'))

    def test_rejects_invalid_signature(self):
        self.assertFalse(verify_meta_webhook_signature(
            self._request('sha256=invalid'),
            self.app_secret,
            self.app_id,
            'Instagram'))

    def test_rejects_missing_signature_when_app_secret_is_configured(self):
        self.assertFalse(verify_meta_webhook_signature(
            self._request(), self.app_secret, self.app_id, 'Facebook'))
