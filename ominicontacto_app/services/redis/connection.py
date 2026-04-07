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

import redis
import threading
from django.conf import settings

# Diccionario global para almacenar connection pools por base de datos Redis
_redis_pools = {}
# Lock para proteger la creación de pools (thread-safe)
_pools_lock = threading.Lock()


def create_redis_connection(db=0):
    """
    Crea o retorna una conexión Redis reutilizando connection pools.
    
    Implementa connection pooling para mejorar el rendimiento y reducir
    el overhead de crear nuevas conexiones en cada request.
    Utiliza thread-safety para prevenir race conditions en la creación de pools.
    
    Args:
        db (int): Número de base de datos Redis (default: 0)
    
    Returns:
        redis.Redis: Conexión Redis configurada con decode_responses=True
    """
    # Verificación inicial sin lock (optimización)
    if db not in _redis_pools:
        # Usar lock para proteger la sección crítica
        with _pools_lock:
            # Double-check pattern: verificar nuevamente dentro del lock
            # para evitar crear múltiples pools si varios threads llegaron aquí
            if db not in _redis_pools:
                pool = redis.ConnectionPool(
                    host=settings.REDIS_HOSTNAME,
                    port=settings.CONSTANCE_REDIS_CONNECTION['port'],
                    db=db,
                    decode_responses=True,
                    max_connections=50
                )
                _redis_pools[db] = pool
    
    # Retornar una conexión del pool
    redis_connection = redis.Redis(connection_pool=_redis_pools[db])
    return redis_connection
