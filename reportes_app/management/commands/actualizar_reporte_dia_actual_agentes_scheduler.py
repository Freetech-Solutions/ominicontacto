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
from django.db import close_old_connections

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.interval import IntervalTrigger

from reportes_app.reportes.reporte_estadisticas_agentes import ReporteDiarioAgentesFamily

logger = logging.getLogger(__name__)


def actualizar_reporte_agentes():
    """
    Actualiza el reporte diario de agentes en Redis.
    Esta función se ejecuta cada 1 minuto mediante APScheduler.
    """
    close_old_connections()
    try:
        logger.info("Iniciando actualización del reporte diario de agentes")
        family = ReporteDiarioAgentesFamily()
        family.regenerar_families()
        logger.info("Actualización del reporte diario de agentes completada exitosamente")
    except Exception as e:
        logger.error(f'Fallo al actualizar reporte diario de agentes: {e}', exc_info=True)


class Command(BaseCommand):
    help = (
        'Ejecuta un scheduler con APScheduler para actualizar '
        'el reporte diario de agentes cada 1 minuto'
    )

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
            'misfire_grace_time': 60  # 1 minuto de gracia si el contenedor estuvo caído
        }

        # Crear scheduler
        self.scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults=job_defaults,
            timezone=None  # Usar timezone del sistema/contenedor (TZ env var)
        )

        # Agregar job cada 1 minuto
        self.scheduler.add_job(
            actualizar_reporte_agentes,
            trigger=IntervalTrigger(minutes=1),  # Cada 1 minuto
            id='actualizar_reporte_dia_actual_agentes',
            name='Actualización del reporte diario de agentes',
            replace_existing=True
        )

        logger.info(
            "Scheduler configurado: actualización del reporte "
            "diario de agentes cada 1 minuto"
        )

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
            logger.info(
                "Scheduler iniciado. Ejecutando actualización del "
                "reporte diario de agentes cada 1 minuto..."
            )

            # Mantener el proceso corriendo
            try:
                while not self.shutdown_requested:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Interrupción de teclado recibida")
                self.shutdown_requested = True

        except Exception as e:
            logger.error(
                "Error en el comando "
                "actualizar_reporte_dia_actual_agentes_scheduler: %s",
                e,
                exc_info=True,
            )
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            sys.exit(1)
        finally:
            if self.scheduler and self.scheduler.running:
                logger.info("Cerrando scheduler...")
                self.scheduler.shutdown(wait=True)
                logger.info("Scheduler cerrado correctamente")
