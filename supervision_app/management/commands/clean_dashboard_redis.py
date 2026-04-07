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
from datetime import datetime

from django.core.management.base import BaseCommand
from django.conf import settings

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger

from ominicontacto_app.services.redis.connection import create_redis_connection

logger = logging.getLogger(__name__)

# Patrones de keys de Redis DB 2 relacionadas con el dashboard Panel
DASHBOARD_REDIS_PATTERNS = [
    'OML:CALLDATA:*',
    'OML:AGENTDATA:*',
    'OML:DISPOSITIONDATA:*',
]

# Redis DB para el dashboard
REDIS_DB = 2


def clean_dashboard_redis_keys():
    """
    Limpia todas las keys de Redis DB 2 relacionadas con el dashboard Panel.
    
    Usa SCAN iterativo para evitar bloquear Redis y elimina todas las keys
    que coincidan con los patrones definidos.
    """
    start_time = time.time()
    total_deleted = 0
    errors = 0
    
    try:
        # Conectar a Redis DB 2
        redis_connection = create_redis_connection(db=REDIS_DB)
        redis_connection.ping()
        
        logger.info("Iniciando limpieza de keys de Redis DB 2 para dashboard Panel")
        
        # Usar pipeline para operaciones batch
        pipeline = redis_connection.pipeline()
        keys_to_delete = []
        
        # Escanear cada patrón usando SCAN (no bloqueante)
        for pattern in DASHBOARD_REDIS_PATTERNS:
            cursor = 0
            pattern_deleted = 0
            
            while True:
                # SCAN retorna (next_cursor, [keys])
                cursor, keys = redis_connection.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100  # Procesar en lotes de 100
                )
                
                # Agregar keys al lote para eliminación
                for key in keys:
                    # Normalizar key (convertir bytes a string si es necesario)
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    keys_to_delete.append(key)
                
                # Si el cursor es 0, hemos terminado de escanear este patrón
                if cursor == 0:
                    break
            
            pattern_deleted = len([k for k in keys_to_delete if pattern.replace('*', '') in k])
            logger.info(f"Patrón {pattern}: encontradas {pattern_deleted} keys para eliminar")
        
        # Eliminar todas las keys encontradas en batch
        if keys_to_delete:
            # Eliminar duplicados
            unique_keys = list(set(keys_to_delete))
            
            # Usar pipeline para eliminación eficiente
            for key in unique_keys:
                try:
                    pipeline.delete(key)
                except Exception as e:
                    logger.warning(f"Error agregando key {key} al pipeline: {e}")
                    errors += 1
            
            # Ejecutar pipeline
            try:
                results = pipeline.execute()
                total_deleted = sum(1 for r in results if r > 0)
                logger.info(f"Pipeline ejecutado: {total_deleted} keys eliminadas de {len(unique_keys)} intentadas")
            except Exception as e:
                logger.error(f"Error ejecutando pipeline de eliminación: {e}")
                errors += 1
        else:
            logger.info("No se encontraron keys para eliminar")
        
        elapsed_time = time.time() - start_time
        logger.info(
            f"Limpieza completada: {total_deleted} keys eliminadas en {elapsed_time:.2f} segundos. "
            f"Errores: {errors}"
        )
        
    except Exception as e:
        logger.error(f"Error durante la limpieza de Redis DB 2: {e}", exc_info=True)
        errors += 1


class Command(BaseCommand):
    help = 'Ejecuta un scheduler con AppScheduler para limpiar diariamente las keys de Redis DB 2 del dashboard Panel'

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
            clean_dashboard_redis_keys,
            trigger=CronTrigger(hour=0, minute=0),  # Todos los días a las 00:00
            id='clean_dashboard_redis_daily',
            name='Limpieza diaria de Redis DB 2 (Dashboard Panel)',
            replace_existing=True
        )
        
        logger.info("Scheduler configurado: limpieza diaria a las 00:00 (TZ del contenedor)")

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
            
            # Ejecutar limpieza inmediatamente al inicio (opcional, para testing)
            # Comentado por defecto - descomentar si se desea ejecución inmediata
            # logger.info("Ejecutando limpieza inicial...")
            # clean_dashboard_redis_keys()
            
            # Mantener el proceso corriendo
            try:
                while not self.shutdown_requested:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Interrupción de teclado recibida")
                self.shutdown_requested = True
            
        except Exception as e:
            logger.error(f"Error en el comando clean_dashboard_redis: {e}", exc_info=True)
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            sys.exit(1)
        finally:
            if self.scheduler and self.scheduler.running:
                logger.info("Cerrando scheduler...")
                self.scheduler.shutdown(wait=True)
                logger.info("Scheduler cerrado correctamente")
