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

from django.core.management.base import BaseCommand
from ominicontacto_app.services.redis.connection import create_redis_connection
import logging
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Unregister Redis Gears Registrations'

    def handle(self, *args, **options):

        try:
            self._delete_registrations()
        except Exception as e:
            logger.error('Fallo del comando: {0}'.format(e))

    def _delete_registrations(self):
        subscriptions = [
            ('OML:AGENT:*', 'sup_agent'),
            ('OML:SUPERVISION_CAMPAIGN:*', 'sup_entrantes'),
            ('OML:SUPERVISION_SALIENTE:*', 'sup_salientes'),
            ('OML:SUPERVISION_DIALER:*', 'sup_dialers'),
        ]
        self.conn = create_redis_connection()
        for redis_key, desc in subscriptions:
            id = self._id_registration(redis_key, desc)
            if id is not None:
                try:
                    res = self.conn.execute_command(f'RG.UNREGISTER {id}')
                    logger.warning(f'Deleting {desc}: {res}')
                except Exception as e:
                    logger.warning(f'Error Deleting {desc}: {e}')

    def _id_registration(self, redis_key, desc):
        REGISTRATION_DATA = 7
        ARGS = 13
        REGEX = 1
        DESCRIPTION = 5
        ID = 1
        lista_eventos_registrados = self.conn.execute_command("RG.DUMPREGISTRATIONS")
        for evento in lista_eventos_registrados:
            if evento[REGISTRATION_DATA][ARGS][REGEX] == redis_key and evento[DESCRIPTION] == desc:
                return evento[ID]
        return
