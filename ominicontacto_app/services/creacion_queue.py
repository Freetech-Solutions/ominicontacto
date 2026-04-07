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

"""
Servicio vinculado a la activación y sincronización de colas (queues) de campañas:
actualización de Redis (CampanaFamily).
"""

from __future__ import unicode_literals

import logging

from ominicontacto_app.errors import OmlError
from ominicontacto_app.services.asterisk.redis_database import CampanaFamily

logger = logging.getLogger(__name__)


class RestablecerDialplanError(OmlError):
    """Indica que se produjo un error al sincronizar la configuración de colas."""
    pass


class ActivacionQueueService(object):
    """Sincronizador de configuracion de Campaña / Queue (Redis)."""

    def __init__(self):
        self.asterisk_database = CampanaFamily()

    def activar_campanas(self):
        self.asterisk_database.regenerar_families()

    def activar(self, campana):
        self.asterisk_database.regenerar_family(campana)

    def sincronizar_por_eliminacion(self, campana):
        self.asterisk_database.delete_family(campana)
