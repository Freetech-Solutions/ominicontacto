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

from utiles_globales import request_url_name
from django.core.exceptions import PermissionDenied


# URLs accesibles con permisos alternativos (misma regla que en DRF permissions).
URL_PERMISOS_ALTERNATIVOS = {
    'api_interaction_transfers_centro_contacto': ('grabacion_buscar',),
    # Panel Dialer reutiliza el permiso de Panel General (sin ítem de menú propio).
    'supervision_panel_dialer': ('supervision_contact_center',),
    'supervision_panel_dialer_campaign': ('supervision_contact_center',),
    'supervision_panel_dialer_estado': ('supervision_contact_center',),
}


class PermisoOMLMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        self.verificar_permiso(request)
        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response

    def verificar_permiso(self, request):
        # Si el agente no esta loggeado dejo que se encargue login_required
        if request.user.is_authenticated:
            url_name = request_url_name(request)
            if request.user.tiene_permiso_oml(url_name):
                return
            permisos_alternativos = URL_PERMISOS_ALTERNATIVOS.get(url_name, ())
            if any(request.user.tiene_permiso_oml(p) for p in permisos_alternativos):
                return
            raise PermissionDenied
