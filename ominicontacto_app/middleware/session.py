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

from django.contrib.sessions.middleware import SessionMiddleware


class SessionMiddlewareSinRenovar(SessionMiddleware):
    """
    Como SESSION_SAVE_EVERY_REQUEST esta activo, cada request renueva la sesion.
    Las vistas listadas solo consultan la sesion y no deben extender su vencimiento.
    """
    URL_NAMES_SIN_RENOVAR = {'api_ws_auth'}

    def process_response(self, request, response):
        match = getattr(request, 'resolver_match', None)
        if match and match.url_name in self.URL_NAMES_SIN_RENOVAR:
            return response
        return super().process_response(request, response)
