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


class CustomDeleteViewMixin(object):
    """
    Django 6 cambió DeleteView.post(): ya no llama a delete() personalizado,
    sino form_valid() -> Model.delete(). Vistas con borrado lógico u operaciones
    extra deben enrutar POST al delete() sobreescrito.
    """

    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)
