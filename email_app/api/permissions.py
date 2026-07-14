# Copyright (C) 2026 Freetech Solutions
#
# This file is part of OMniLeads
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.

from django.urls import resolve
from rest_framework import permissions


class ViewPermission(permissions.IsAuthenticated):
    @staticmethod
    def _has_view_name_permission(request, obj=None):
        view_name = resolve(request.path_info).view_name
        return request.user.tiene_permiso_oml(view_name)

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if not self._has_view_name_permission(request):
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if not self._has_view_name_permission(request, obj):
            return False
        return True
