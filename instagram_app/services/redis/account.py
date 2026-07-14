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
from instagram_app.models import CuentaInstagram


NOMBRE_STREAM = 'instagram_enabled_accounts'


class StreamDeCuentasInstagram(object):

    def notificar_nueva_cuenta(self, account):
        RedisStreams().write_stream(NOMBRE_STREAM, account.id)

    def notificar_cuenta_eliminada(self, account):
        RedisStreams().write_stream(NOMBRE_STREAM, account.id)

    def regenerar_stream(self):
        stream_manager = RedisStreams()
        stream_manager.flush(NOMBRE_STREAM)
        for account in CuentaInstagram.objects_default.all():
            if account.is_active:
                self.notificar_nueva_cuenta(account)
            else:
                self.notificar_cuenta_eliminada(account)
