# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions
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
#

import getpass
import logging
from django.core.management.base import BaseCommand, CommandError
from supervision_app.services.redisgears_service import RedisGearsService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Da de baja en RedisGears los eventos de supervisión y vacía los streams de
    supervisores. Los eventos se vuelven a registrar, con los scripts registrar_evento_*
    vigentes, la próxima vez que un supervisor entra a la pantalla que los usa; hasta
    entonces las pantallas abiertas no se actualizan. Ejecutar fuera del horario de
    operación.
    La migración supervision_app 0001 hace lo mismo al desplegar; este comando queda
    para correrlo a mano si la migración no pudo conectarse a Redis.
    """
    help = "Da de baja los eventos de supervisión en RedisGears (se vuelven a registrar " \
           "al suscribirse un supervisor) y vacía los streams de supervisores"

    def add_arguments(self, parser):
        parser.add_argument(
            '--sin-limpiar-streams', action='store_true',
            help='Solo da de baja los eventos, sin vaciar los streams')

    def handle(self, *args, **options):
        usuario = self._usuario_sistema()
        service = RedisGearsService()
        try:
            bajas = service.da_de_baja_eventos_supervision()
            mensaje = f'Eventos de supervisión dados de baja: {bajas}'
            if not options['sin_limpiar_streams']:
                borradas = service.limpia_streams_supervisores()
                mensaje += f'. Streams de supervisores vaciados ({borradas} entradas)'
        except Exception as e:
            logger.error(f"Fallo al actualizar streams de supervisión (usuario: {usuario}): {e}")
            raise CommandError(f"Fallo al actualizar streams de supervisión: {e}")
        logger.info(f"actualizar_streams_supervision ejecutado por {usuario}: {mensaje}")
        self.stdout.write(mensaje)

    def _usuario_sistema(self):
        try:
            return getpass.getuser()
        except Exception:
            return 'desconocido'
