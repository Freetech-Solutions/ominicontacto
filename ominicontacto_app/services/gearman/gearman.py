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
Servicio para disparar Gearman tasks
"""

from gearman import GearmanClient
import json
import os  # TODO: Utilizar django.settings
import logging

logger = logging.getLogger(__name__)

# TODO: Utilizar django.settings
gearman_host = os.getenv('GEARMAN_HOST', 'gearman')
gearman_port = os.getenv('GEARMAN_PORT', '4730')
gearman_server = f"{gearman_host}:{gearman_port}"


# ───── Funciones auxiliares ─────
def send_task(task_name: bytes, job_data: dict):
    try:
        gm_client = GearmanClient([gearman_server])
        logger.debug(f"Enviando tarea '{task_name}' a {gearman_server}: {job_data}")
        gm_client.submit_job(
            task_name,
            json.dumps(job_data).encode('utf-8'),
            wait_until_complete=False
        )
        return
    except Exception as e:
        logger.error(f"Error al enviar tarea '{task_name}': {e}")
        return e
