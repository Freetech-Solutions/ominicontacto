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
from django.utils.translation import gettext as _

from api_app.views.permissions import TienePermisoOML


class TienePermisoCanalInstagramAgente(TienePermisoOML):
    message = _('No tiene permiso para usar la canalidad Instagram.')

    def has_permission(self, request, view):
        if not super(TienePermisoCanalInstagramAgente, self).has_permission(request, view):
            return False

        if not request.user.is_agente:
            return True

        try:
            agente = request.user.get_agente_profile()
        except Exception:
            return False

        return bool(getattr(agente.grupo, 'instagram_habilitado', False))
