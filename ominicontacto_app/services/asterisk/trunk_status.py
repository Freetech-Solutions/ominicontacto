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


class TrunkStatusMonitor(object):
    """Asigna estado a los troncales PJSIP. Sin consulta a Asterisk (AMI removido)."""

    def _set_unknown_status(self, trunk):
        trunk.status = _('Desconocido')

    def set_trunks_statuses(self, trunks):
        """Marca todos los troncales con estado 'Desconocido' (no se consulta Asterisk)."""
        for trunk in trunks:
            self._set_unknown_status(trunk)
