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

"""
Utilidad para mantener OML:CAMP:{id}:STATUS en Redis.
Valores permitidos: active, paused, finalized, created, other.
"""

import logging

from ominicontacto_app.services.redis.connection import create_redis_connection

logger = logging.getLogger(__name__)

VALID_STATUSES = frozenset({'active', 'paused', 'finalized', 'created', 'other'})


def set_campaign_status_redis(campaign_id, status):
    """
    Establece OML:CAMP:{campaign_id}:STATUS en Redis DB 0.

    Args:
        campaign_id: ID de la campaña
        status: Uno de: active, paused, finalized, created, other

    Returns:
        bool: True si se escribió correctamente, False en caso de error
    """
    if status not in VALID_STATUSES:
        logger.warning(
            "set_campaign_status_redis: status '%s' no válido para campaña %s. "
            "Valores permitidos: %s",
            status, campaign_id, sorted(VALID_STATUSES)
        )
        return False

    try:
        redis_conn = create_redis_connection(db=0)
        key = f'OML:CAMP:{campaign_id}:STATUS'
        redis_conn.set(key, status)
        return True
    except Exception as e:
        logger.warning(
            "set_campaign_status_redis: error escribiendo STATUS para campaña %s: %s",
            campaign_id, e,
            exc_info=False
        )
        return False


def delete_campaign_status_redis(campaign_id):
    """
    Elimina la clave OML:CAMP:{campaign_id}:STATUS de Redis DB 0.

    Args:
        campaign_id: ID de la campaña

    Returns:
        bool: True si se eliminó o no existía, False en caso de error
    """
    try:
        redis_conn = create_redis_connection(db=0)
        key = f'OML:CAMP:{campaign_id}:STATUS'
        redis_conn.delete(key)
        return True
    except Exception as e:
        logger.warning(
            "delete_campaign_status_redis: error eliminando STATUS para campaña %s: %s",
            campaign_id, e,
            exc_info=False
        )
        return False
