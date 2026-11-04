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

from __future__ import unicode_literals
from django.urls import resolve
from rest_framework.permissions import IsAuthenticated


class TienePermisoOML(IsAuthenticated):
    """Permiso para aplicar a vistas restringidas por PermisoOML"""

    def has_permission(self, request, view):
        has_permission = super(TienePermisoOML, self).has_permission(request, view)
        if not has_permission:
            return has_permission

        resolver_match = resolve(request.path_info)
        basename = getattr(view, 'basename', None) or None
        return request.user.tiene_permiso_oml_en_url(resolver_match, basename)
