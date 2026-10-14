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

from ominicontacto_app.services.redis.redis_streams import RedisStreams
from whatsapp_app.models import Linea


NOMBRE_STREAM_LINEAS = 'whatsapp_enabled_lines'


class StreamDeLineas(object):

    def notificar_nueva_linea(self, linea):
        RedisStreams().write_stream(NOMBRE_STREAM_LINEAS, linea.id)

    def notificar_linea_eliminada(self, linea):
        RedisStreams().write_stream(NOMBRE_STREAM_LINEAS, linea.id)

    def regenerar_stream(self):
        """
        Seed the master stream only when empty.

        Flushing on every orchestrator start makes peers re-read all line ids,
        cancel in-flight slave tasks and leave unacked messages in the PEL.
        """
        stream_manager = RedisStreams()
        try:
            if stream_manager.connection.xlen(NOMBRE_STREAM_LINEAS) > 0:
                return False
        except Exception:
            pass
        stream_manager.flush(NOMBRE_STREAM_LINEAS)
        for linea in Linea.objects.all():
            if linea.is_active:
                self.notificar_nueva_linea(linea)
            else:
                self.notificar_linea_eliminada(linea)
        return True
