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
from facebook_meta_app.models import PaginaMetaFacebook


NOMBRE_STREAM = 'facebook_enabled_pages'


class StreamDePaginas(object):

    def notificar_nueva_page(self, page):
        RedisStreams().write_stream(NOMBRE_STREAM, page.id)

    def notificar_page_eliminada(self, page):
        RedisStreams().write_stream(NOMBRE_STREAM, page.id)

    def regenerar_stream(self):
        """
        Seed the master stream only when empty.

        Flushing on every orchestrator start makes peers re-read all page ids,
        cancel in-flight slave tasks and leave unacked messages in the PEL.
        """
        stream_manager = RedisStreams()
        try:
            if stream_manager.connection.xlen(NOMBRE_STREAM) > 0:
                return False
        except Exception:
            pass
        stream_manager.flush(NOMBRE_STREAM)
        for page in PaginaMetaFacebook.objects_default.all():
            if page.is_active:
                self.notificar_nueva_page(page)
            else:
                self.notificar_page_eliminada(page)
        return True
