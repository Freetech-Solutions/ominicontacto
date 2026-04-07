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

import logging
import signal
import sys
import time

from django.core.management.base import BaseCommand

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger

# Importar funciones de los comandos originales
from supervision_app.management.commands.clean_dashboard_redis import clean_dashboard_redis_keys
from reportes_app.management.commands.reiniciar_estadisticas_calldata_scheduler import reiniciar_estadisticas_calldata

logger = logging.getLogger(__name__)


def daily_redis_cleanup():
    """
    Función combinada que ejecuta ambas tareas de limpieza de Redis en secuencia:
    1. Limpieza de keys del dashboard Redis (DB 2)
    2. Reinicio de estadísticas calldata
    
    Si una tarea falla, se registra el error pero se intenta ejecutar la siguiente.
    """
    logger.info("Iniciando limpieza diaria de Redis (tareas combinadas)")
    
    # Ejecutar limpieza del dashboard Redis
    try:
        logger.info("Ejecutando limpieza de keys del dashboard Redis...")
        clean_dashboard_redis_keys()
        logger.info("Limpieza de keys del dashboard Redis completada")
    except Exception as e:
        logger.error(f"Error durante la limpieza de keys del dashboard Redis: {e}", exc_info=True)
    
    # Ejecutar reinicio de estadísticas calldata
    try:
        logger.info("Ejecutando reinicio de estadísticas calldata...")
        reiniciar_estadisticas_calldata()
        logger.info("Reinicio de estadísticas calldata completado")
    except Exception as e:
        logger.error(f"Error durante el reinicio de estadísticas calldata: {e}", exc_info=True)
    
    logger.info("Limpieza diaria de Redis completada (todas las tareas ejecutadas)")


class Command(BaseCommand):
    help = 'Ejecuta un scheduler con APScheduler para realizar limpieza diaria de Redis: limpieza de dashboard y reinicio de estadísticas calldata'

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
            daily_redis_cleanup,
            trigger=CronTrigger(hour=0, minute=0),  # Todos los días a las 00:00
            id='daily_redis_cleanup',
            name='Limpieza diaria de Redis (dashboard y estadísticas calldata)',
            replace_existing=True
        )
        
        logger.info("Scheduler configurado: limpieza diaria de Redis a las 00:00 (TZ del contenedor)")

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
            logger.error(f"Error en el comando daily_redis_cleanup: {e}", exc_info=True)
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            sys.exit(1)
        finally:
            if self.scheduler and self.scheduler.running:
                logger.info("Cerrando scheduler...")
                self.scheduler.shutdown(wait=True)
                logger.info("Scheduler cerrado correctamente")
