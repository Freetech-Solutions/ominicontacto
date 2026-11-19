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

from hmac import compare_digest

from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token
from rest_framework.authentication import BaseAuthentication, TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from datetime import timedelta
from django.utils import timezone
from django.conf import settings


# this return left time
def expires_in(token):
    time_elapsed = timezone.now() - token.created
    left_time = timedelta(seconds=settings.TOKEN_EXPIRED_AFTER_SECONDS) - time_elapsed
    return left_time


def is_token_expired(token):
    # token checker if token expired or not
    return expires_in(token) < timedelta(seconds=0)


# if token is expired new token will be established
# If token is expired then it will be removed
# and new one with different key will be created
def token_expire_handler(token):
    is_expired = is_token_expired(token)
    if is_expired:
        token.delete()
        token = Token.objects.create(user=token.user)
    return is_expired, token


class ExpiringTokenAuthentication(TokenAuthentication):
    """
    If token is expired then it will be removed
    and new one with different key will be created
    """

    keyword = 'Bearer'

    def authenticate_credentials(self, key):
        try:
            token = Token.objects.get(key=key)
        except Token.DoesNotExist:
            raise AuthenticationFailed("Invalid Token")

        if not token.user.is_active:
            raise AuthenticationFailed("User is not active")

        is_expired, token = token_expire_handler(token)
        if is_expired:
            raise AuthenticationFailed("The Token is expired")

        return (token.user, token)


INTERNAL_SECRET_HEADER = 'X-OML-INTERNAL-SECRET'
INTERNAL_AUTH = 'internal'


def is_valid_internal_secret(secret):
    expected = settings.OML_INTERNAL_SECRET
    if not expected or not secret:
        return False
    return compare_digest(str(secret).encode(), str(expected).encode())


class InternalSecretAuthentication(BaseAuthentication):
    """
    Autentica requests de componentes internos de OML (fastagi, acd, etc.)
    mediante el secret compartido OML_INTERNAL_SECRET enviado en el header
    X-OML-INTERNAL-SECRET. No hay un usuario OML asociado.
    """

    def authenticate(self, request):
        secret = request.META.get('HTTP_X_OML_INTERNAL_SECRET')
        if not is_valid_internal_secret(secret):
            raise AuthenticationFailed('Invalid internal secret')
        return (AnonymousUser(), INTERNAL_AUTH)

    def authenticate_header(self, request):
        return INTERNAL_SECRET_HEADER


class IsInternalComponent(BasePermission):

    def has_permission(self, request, view):
        return request.auth == INTERNAL_AUTH
