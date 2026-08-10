# -*- coding: utf-8 -*-
# Copyright (C) 2026 Freetech Solutions

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
Envía samples de ACW (After Call Work) al dialer vía Gearman process-event.

Solo process-event → Redis DB3 CAMP:{id}:ACW. No toca acd-log-processor / logger.
"""
from __future__ import unicode_literals

import json
import logging
import time

import gearman
from django.conf import settings

from ominicontacto_app.models import Campana

logger = logging.getLogger(__name__)

PROCESS_EVENT_JOB = 'process-event'


def _gearman_client():
    servers = getattr(settings, 'GEARMAN_JOB_SERVERS', None) or []
    if not servers:
        return None
    try:
        return gearman.GearmanClient(servers)
    except Exception:
        logger.exception('acw_metrics: no se pudo crear GearmanClient')
        return None


def is_dialer_campaign(campaign_id):
    """True si campaign_id existe y es campaña dialer."""
    try:
        cid = int(campaign_id)
    except (TypeError, ValueError):
        return False
    if cid <= 0:
        return False
    return Campana.objects.filter(id=cid, type=Campana.TYPE_DIALER).exists()


def submit_exit_acw(campaign_id, acw_duration, agent_id=None):
    """
    Encola Dial EXIT_ACW hacia process-event.
    Nunca lanza: fallos de Gearman se loguean y se ignoran.
    """
    try:
        cid = int(campaign_id)
        duration = max(0.0, float(acw_duration))
    except (TypeError, ValueError):
        logger.debug(
            'acw_metrics: sample inválido campaign=%s duration=%s',
            campaign_id, acw_duration,
        )
        return False
    if cid <= 0:
        return False
    if not is_dialer_campaign(cid):
        logger.debug('acw_metrics: campaña %s no es dialer; skip', cid)
        return False

    ts = int(time.time())
    callid = 'acw-{0}-{1}'.format(agent_id or '0', ts)
    payload = {
        'type': 'Dial',
        'dialstatus': 'EXIT_ACW',
        'call_type': 'to_pstn',
        'id_campaign': str(cid),
        'contact_id': '0',
        'phone_number': '0',
        'acw_duration': duration,
        'callid': callid,
    }
    client = _gearman_client()
    if client is None:
        logger.warning(
            'acw_metrics: Gearman no disponible; omitiendo EXIT_ACW camp=%s',
            cid,
        )
        return False
    try:
        client.submit_job(
            PROCESS_EVENT_JOB,
            json.dumps(payload).encode('utf-8'),
            background=True,
            wait_until_complete=False,
        )
        logger.info(
            'acw_metrics: EXIT_ACW enviado camp=%s acw_duration=%s callid=%s',
            cid, duration, callid,
        )
        return True
    except Exception:
        logger.exception(
            'acw_metrics: error enviando EXIT_ACW camp=%s duration=%s',
            cid, duration,
        )
        return False
