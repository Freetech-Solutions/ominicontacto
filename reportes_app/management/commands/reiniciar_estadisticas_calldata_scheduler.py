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

import os
import logging
import signal
import sys
import time

from django.core.management.base import BaseCommand

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger

from ominicontacto_app.services.redis.connection import create_redis_connection
from reportes_app.services.redis.call_data_generation import CallDataGenerator
from reportes_app.services.redis.disposition_cache import CampaignDispositionsCache

logger = logging.getLogger(__name__)


def reiniciar_estadisticas_calldata():
    """
    Reinicia valores de calldata al comenzar nuevo día.
    Esta función se ejecuta diariamente a medianoche mediante APScheduler.
    """
    try:
        logger.info("Iniciando reinicio de estadísticas calldata")
        redis_oml_connection = create_redis_connection(0)
        redis_calldata_connection = create_redis_connection(2)
        calldata_generator = CallDataGenerator(redis_calldata_connection)
        calldata_generator.eliminar_datos()
        disposition_cache = CampaignDispositionsCache()
        disposition_cache.eliminar_datos()
        if not os.getenv('WALLBOARD_VERSION', '') == '':
            from wallboard_app.redis.regeneracion import reiniciar_wallboard_cache
            reiniciar_wallboard_cache(redis_oml_connection, redis_calldata_connection)
        logger.info("Reinicio de estadísticas calldata completado exitosamente")
    except Exception as e:
        logger.error(f'Fallo al reiniciar estadísticas calldata: {e}', exc_info=True)


class Command(BaseCommand):
    help = 'Ejecuta un scheduler con APScheduler para reiniciar estadísticas calldata diariamente a medianoche'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.scheduler = None
        self.shutdown_requested = False

    def setup_scheduler(self):
        """Configura el scheduler de APScheduler."""
        # Configurar executor con un solo thread
        executors = {
            'default': ThreadPoolExecutor(1)
        }
        
        # Configurar defaults de jobs
        job_defaults = {
            'coalesce': True,  # Ejecutar solo una vez si hay múltiples ejecuciones pendientes
            'max_instances': 1,  # Solo una instancia del job puede ejecutarse a la vez
            'misfire_grace_time': 3600  # 1 hora de gracia si el contenedor estuvo caído
        }
        
        # Crear scheduler
        self.scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults=job_defaults,
            timezone=None  # Usar timezone del sistema/contenedor (TZ env var)
        )
        
        # Agregar job diario a las 00:00
        # El timezone se toma de la variable de entorno TZ del contenedor
        self.scheduler.add_job(
            reiniciar_estadisticas_calldata,
            trigger=CronTrigger(hour=0, minute=0),  # Todos los días a las 00:00
            id='reiniciar_estadisticas_calldata_daily',
            name='Reinicio diario de estadísticas calldata',
            replace_existing=True
        )
        
        logger.info("Scheduler configurado: reinicio diario de estadísticas calldata a las 00:00 (TZ del contenedor)")

    def signal_handler(self, signum, frame):
        """Maneja señales de terminación para cerrar el scheduler gracefully."""
        logger.info(f"Señal {signum} recibida. Cerrando scheduler...")
        self.shutdown_requested = True
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        sys.exit(0)

    def handle(self, *args, **options):
        """Punto de entrada principal del comando."""
        try:
            # Registrar handlers de señales
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)
            
            # Configurar scheduler
            self.setup_scheduler()
            
            # Iniciar scheduler
            self.scheduler.start()
            logger.info("Scheduler iniciado. Esperando ejecución diaria a las 00:00...")
            
            # Mantener el proceso corriendo
            try:
                while not self.shutdown_requested:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Interrupción de teclado recibida")
                self.shutdown_requested = True
            
        except Exception as e:
            logger.error(f"Error en el comando reiniciar_estadisticas_calldata_scheduler: {e}", exc_info=True)
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            sys.exit(1)
        finally:
            if self.scheduler and self.scheduler.running:
                logger.info("Cerrando scheduler...")
                self.scheduler.shutdown(wait=True)
                logger.info("Scheduler cerrado correctamente")
