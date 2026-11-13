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
"""Tests de ExpiringTokenAuthentication (token Bearer de las APIs públicas)."""

from datetime import timedelta

from django.conf import settings
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed

from api_app.authentication import ExpiringTokenAuthentication
from ominicontacto_app.tests.utiles import OMLBaseTest


class ExpiringTokenAuthenticationTest(OMLBaseTest):

    def setUp(self):
        super(ExpiringTokenAuthenticationTest, self).setUp()
        self.auth = ExpiringTokenAuthentication()
        self.factory = RequestFactory()
        self.user = self.crear_supervisor_profile().user
        self.token = Token.objects.create(user=self.user)

    def _authenticate(self, authorization=None, **params):
        extra = {'HTTP_AUTHORIZATION': authorization} if authorization else {}
        return self.auth.authenticate(self.factory.get('/', params, **extra))

    def _envejecer_token(self, segundos):
        Token.objects.filter(key=self.token.key).update(
            created=timezone.now() - timedelta(seconds=segundos))

    def test_token_valido_autentica_al_usuario(self):
        user, token = self._authenticate('Bearer ' + self.token.key)
        self.assertEqual(user, self.user)
        self.assertEqual(token.key, self.token.key)

    def test_sin_header_no_autentica(self):
        self.assertIsNone(self._authenticate())

    def test_keyword_distinto_de_bearer_no_autentica(self):
        self.assertIsNone(self._authenticate('Token ' + self.token.key))

    def test_token_en_query_string_no_autentica(self):
        self.assertIsNone(self._authenticate(token=self.token.key))

    def test_token_inexistente_falla(self):
        with self.assertRaisesMessage(AuthenticationFailed, 'Invalid Token'):
            self._authenticate('Bearer token-inexistente')

    def test_usuario_inactivo_falla(self):
        self.user.is_active = False
        self.user.save()
        with self.assertRaisesMessage(AuthenticationFailed, 'User is not active'):
            self._authenticate('Bearer ' + self.token.key)

    def test_token_no_vencido_autentica(self):
        self._envejecer_token(settings.TOKEN_EXPIRED_AFTER_SECONDS - 60)
        user, _ = self._authenticate('Bearer ' + self.token.key)
        self.assertEqual(user, self.user)

    def test_token_vencido_falla_y_se_reemplaza(self):
        self._envejecer_token(settings.TOKEN_EXPIRED_AFTER_SECONDS + 1)
        with self.assertRaisesMessage(AuthenticationFailed, 'The Token is expired'):
            self._authenticate('Bearer ' + self.token.key)
        self.assertFalse(Token.objects.filter(key=self.token.key).exists())
        self.assertTrue(Token.objects.filter(user=self.user).exists())

    def test_header_www_authenticate_es_bearer(self):
        self.assertEqual(self.auth.authenticate_header(self.factory.get('/')), 'Bearer')
