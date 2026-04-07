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
Helpers para el endpoint agents_kpis_v2: redondeo consistente y validación de invariantes.
"""

import logging

logger = logging.getLogger(__name__)

# Tolerancia en segundos para invariantes (edge cases de redondeo/intervalos)
INVARIANT_TOLERANCE_SECONDS = 1


def round_seconds(value, ndigits=3):
    """
    Redondea un valor de segundos (None, int o float) a ndigits decimales.
    Devuelve float; para availability se usa int en el bloque final.
    """
    if value is None:
        return 0.0
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return 0.0


def round_ratio(value, ndigits=4):
    """Redondea un ratio (None, int o float) a ndigits decimales."""
    if value is None:
        return 0.0
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return 0.0


def validate_agent_kpis_v2_invariants(item, strict=False):
    """
    Valida invariantes matemáticas por fila (agent_id, date).
    - Invariante 1: ready_seconds + pause_seconds + acw_seconds == session_seconds (tolerancia 1s).
    - Invariante 2: SUM(pause_breakdown[].seconds) == pause_seconds (tolerancia 1s).

    Si strict=True y falla alguna, lanza ValueError.
    Si strict=False y falla, solo registra WARNING y no rompe.
    """
    availability = item.get('availability') or {}
    session_seconds = int(availability.get('session_seconds') or 0)
    ready_seconds = int(availability.get('ready_seconds') or 0)
    pause_seconds = int(availability.get('pause_seconds') or 0)
    acw_seconds = int(availability.get('acw_seconds') or 0)

    agent_id = item.get('agent_id')
    date = item.get('date')

    # Invariante 1: ready + pause + acw == session
    sum_states = ready_seconds + pause_seconds + acw_seconds
    diff1 = abs(sum_states - session_seconds)
    if diff1 > INVARIANT_TOLERANCE_SECONDS:
        msg = (
            "agents_kpis_v2 invariant 1 failed: agent_id={}, date={}: "
            "ready_seconds + pause_seconds + acw_seconds = {} != session_seconds = {} (diff={})"
        ).format(agent_id, date, sum_states, session_seconds, diff1)
        if strict:
            raise ValueError(msg)
        logger.warning(msg)

    # Validación liviana: pause_seconds > 0 con pause_breakdown vacío es inconsistente (solo log, no excepción)
    pause_breakdown = availability.get('pause_breakdown') or []
    if pause_seconds > 0 and not pause_breakdown:
        logger.warning(
            "agents_kpis_v2: pause_seconds=%s > 0 but pause_breakdown is empty (agent_id=%s, date=%s)",
            pause_seconds, agent_id, date,
        )

    # Invariante 2: SUM(pause_breakdown.seconds) == pause_seconds
    sum_breakdown = sum(b.get('seconds', 0) for b in pause_breakdown)
    diff2 = abs(sum_breakdown - pause_seconds)
    if diff2 > INVARIANT_TOLERANCE_SECONDS:
        msg = (
            "agents_kpis_v2 invariant 2 failed: agent_id={}, date={}: "
            "sum(pause_breakdown.seconds) = {} != pause_seconds = {} (diff={})"
        ).format(agent_id, date, sum_breakdown, pause_seconds, diff2)
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
