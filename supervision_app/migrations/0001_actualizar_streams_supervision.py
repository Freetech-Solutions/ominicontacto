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
"""
OML-3494: recorte de streams de supervisión.

Los eventos de supervisión de RedisGears se registran la primera vez que un supervisor
entra a la pantalla que los usa, y no se vuelven a registrar si ya existen. Esta
migración los da de baja para que se registren con los scripts registrar_evento_* nuevos
(con límite MAXLEN en los streams), y vacía los streams de supervisores existentes.

El reverse no hace nada: los eventos registrados con los scripts nuevos funcionan igual
con la versión anterior del código.

No toca la base de datos. Si Redis no está disponible, se avisa y se continúa para no
frenar el despliegue. En ese caso hay que ejecutar a mano
`python manage.py actualizar_streams_supervision`.
Con el setting MIGRACIONES_OMITIR_REDIS (settings de tests) no hace nada.
"""
import logging

from django.conf import settings
from django.db import migrations
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def actualizar_streams_supervision(apps, schema_editor):
    if getattr(settings, 'MIGRACIONES_OMITIR_REDIS', False):
        return
    from supervision_app.services.redisgears_service import RedisGearsService
    try:
        service = RedisGearsService()
        bajas = service.da_de_baja_eventos_supervision()
        borradas = service.limpia_streams_supervisores()
    except RedisError as e:
        mensaje = 'No se pudieron actualizar los streams de supervisión en Redis ({}). ' \
                  'Ejecutar a mano: python manage.py actualizar_streams_supervision'.format(e)
        logger.warning(mensaje)
        print('\n  ' + mensaje)
        return
    logger.info('Streams de supervisión actualizados por migración: '
                '{} eventos dados de baja, {} entradas vaciadas'.format(bajas, borradas))


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        migrations.RunPython(actualizar_streams_supervision, migrations.RunPython.noop,
                             elidable=True),
    ]
