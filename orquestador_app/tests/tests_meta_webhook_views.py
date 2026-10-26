# -*- coding: utf-8 -*-

import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from facebook_meta_app.models import PaginaMetaFacebook
from instagram_app.models import CuentaInstagram
from whatsapp_app.models import ConfiguracionProveedor
from whatsapp_app.tests.factories import ConfiguracionProveedorFactory, LineaFactory


APP_ID = 'meta-app-id'
APP_SECRET = 'meta-app-secret'
FAKE_SIGNATURE = 'sha256=' + '0' * 64


def _sign(body, app_secret=APP_SECRET):
    return 'sha256=' + hmac.new(
        app_secret.encode('utf-8'), body, hashlib.sha256).hexdigest()


class MetaWebhookViewsBaseTest(TestCase):
    databases = {'default', 'replica'}

    def setUp(self):
        patcher = patch('ominicontacto_app.services.redis.redis_streams.RedisStreams.write_stream')
        self.write_stream = patcher.start()
        self.addCleanup(patcher.stop)

    def _post(self, url, body, signature=None):
        headers = {}
        if signature is not None:
            headers['HTTP_X_HUB_SIGNATURE_256'] = signature
        return self.client.post(url, data=body, content_type='application/json', **headers)

    def _create_page(self, app_secret):
        return PaginaMetaFacebook.objects.create(
            name='Page test', access_token='token', verify_token='verify',
            app_id=APP_ID, app_secret=app_secret, page_id='page-id')

    def _create_instagram_account(self, app_secret):
        return CuentaInstagram.objects.create(
            name='Account test', access_token='token', verify_token='verify',
            app_id=APP_ID, app_secret=app_secret, page_id='page-id', ig_user_id='ig-user-id')

    def _create_whatsapp_line(self, app_secret):
        proveedor = ConfiguracionProveedorFactory(tipo_proveedor=ConfiguracionProveedor.TIPO_META)
        return LineaFactory(proveedor=proveedor, configuracion={
            'app_id': APP_ID, 'waba_id': 'waba', 'verification_token': 'verify',
            'app_secret': app_secret})


class WebhookFacebookMessengerViewTest(MetaWebhookViewsBaseTest):

    body = json.dumps({'object': 'page', 'entry': []}).encode('utf-8')

    def setUp(self):
        super().setUp()
        self.url = reverse('webhook-facebook-messenger', args=[APP_ID])

    def test_rejects_unknown_page(self):
        response = self._post(
            reverse('webhook-facebook-messenger', args=['HACKER-123']), self.body)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_page_without_app_secret(self):
        self._create_page(app_secret=None)
        response = self._post(self.url, self.body, _sign(self.body, ''))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_fake_signature(self):
        self._create_page(app_secret=APP_SECRET)
        response = self._post(self.url, self.body, FAKE_SIGNATURE)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_missing_signature(self):
        self._create_page(app_secret=APP_SECRET)
        response = self._post(self.url, self.body)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_accepts_valid_signature(self):
        page = self._create_page(app_secret=APP_SECRET)
        response = self._post(self.url, self.body, _sign(self.body))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.write_stream.assert_called_once()
        self.assertEqual(self.write_stream.call_args[0][0], page.get_stream_name)


class WebhookInstagramViewTest(MetaWebhookViewsBaseTest):

    body = json.dumps({'object': 'instagram', 'entry': []}).encode('utf-8')

    def setUp(self):
        super().setUp()
        self.url = reverse('webhook-instagram', args=[APP_ID])

    def test_rejects_unknown_account(self):
        response = self._post(self.url, self.body, _sign(self.body))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_account_without_app_secret(self):
        self._create_instagram_account(app_secret='')
        response = self._post(self.url, self.body, _sign(self.body, ''))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_fake_signature(self):
        self._create_instagram_account(app_secret=APP_SECRET)
        response = self._post(self.url, self.body, FAKE_SIGNATURE)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_accepts_valid_signature(self):
        self._create_instagram_account(app_secret=APP_SECRET)
        response = self._post(self.url, self.body, _sign(self.body))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.write_stream.assert_called_once()


class WebhookMetaViewTest(MetaWebhookViewsBaseTest):

    whatsapp_body = json.dumps(
        {'object': 'whatsapp_business_account', 'entry': []}).encode('utf-8')
    page_body = json.dumps({'object': 'page', 'entry': []}).encode('utf-8')
    instagram_body = json.dumps({'object': 'instagram', 'entry': []}).encode('utf-8')

    def setUp(self):
        super().setUp()
        self.url = reverse('webhook-meta', args=[APP_ID])

    def test_rejects_unknown_whatsapp_line(self):
        response = self._post(self.url, self.whatsapp_body, _sign(self.whatsapp_body))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_whatsapp_line_without_app_secret(self):
        self._create_whatsapp_line(app_secret='')
        response = self._post(self.url, self.whatsapp_body, _sign(self.whatsapp_body, ''))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_whatsapp_fake_signature(self):
        self._create_whatsapp_line(app_secret=APP_SECRET)
        response = self._post(self.url, self.whatsapp_body, FAKE_SIGNATURE)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_accepts_whatsapp_valid_signature(self):
        self._create_whatsapp_line(app_secret=APP_SECRET)
        response = self._post(self.url, self.whatsapp_body, _sign(self.whatsapp_body))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.write_stream.assert_called_once()

    def test_rejects_unknown_facebook_page(self):
        response = self._post(self.url, self.page_body, _sign(self.page_body))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_facebook_page_without_app_secret(self):
        self._create_page(app_secret=None)
        response = self._post(self.url, self.page_body, _sign(self.page_body, ''))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_unknown_instagram_account(self):
        response = self._post(self.url, self.instagram_body, _sign(self.instagram_body))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()

    def test_rejects_instagram_account_without_app_secret(self):
        self._create_instagram_account(app_secret=None)
        response = self._post(self.url, self.instagram_body, _sign(self.instagram_body, ''))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.write_stream.assert_not_called()
