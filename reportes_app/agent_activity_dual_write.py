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
Escritura de eventos de actividad de agente en AgentActivityEventV2.

- write_agent_activity_event_v2: eventos de sesión/pausa/despausa (SESSION_LOGIN,
  SESSION_LOGOUT, PAUSEALL, UNPAUSEALL). Recibe event/pausa_id con la misma
  semántica que el modelo legacy para compatibilidad con AgentPresenceManager.
- write_hold_activity_event_v2: hold/unhold (STATE_ON_HOLD, STATE_OFF_HOLD).
- write_agent_activity_event_v2_synthetic: eventos sintéticos (ej. cierre por timeout)
  con source obligatorio.

Mapping event -> event_type:
- SESSION_LOGIN  -> SESSION_LOGIN
- SESSION_LOGOUT -> SESSION_LOGOUT
- PAUSEALL pausa_id vacío o '0' -> STATE_ACW (pause=None, aux_code=None)
- PAUSEALL otro -> STATE_PAUSED (pause FK o aux_code + metadata)
- UNPAUSEALL -> STATE_READY (pause=None, aux_code=None)
"""

from reportes_app.models import ActividadAgenteLog, AgentActivityEventV2

SOURCE_HEARTBEAT_TIMEOUT = 'HB_TIMEOUT'
SOURCE_HEARTBEAT_RECOVER = 'HB_RECOVER'
SOURCE_SESSION_EXPIRED = 'SESS_EXPIRED'


def write_agent_activity_event_v2(agente_id, event, pausa_id, ts):
    """
    Crea un registro en AgentActivityEventV2 para un evento de sesión/pausa/despausa.

    :param agente_id: int
    :param event: str (SESSION_LOGIN | SESSION_LOGOUT | PAUSEALL | UNPAUSEALL)
    :param pausa_id: str | None (UNPAUSEALL siempre None; PAUSEALL opcional)
    :param ts: datetime para el campo ts
    """
    if event not in (
        ActividadAgenteLog.SESSION_LOGIN,
        ActividadAgenteLog.SESSION_LOGOUT,
        ActividadAgenteLog.PAUSE,
        ActividadAgenteLog.UNPAUSE,
    ):
        return

    event_type = None
    pause = None
    aux_code = None
    metadata = {}

    if event == ActividadAgenteLog.SESSION_LOGIN:
        event_type = AgentActivityEventV2.EventType.SESSION_LOGIN
    elif event == ActividadAgenteLog.SESSION_LOGOUT:
        event_type = AgentActivityEventV2.EventType.SESSION_LOGOUT
    elif event == ActividadAgenteLog.UNPAUSE:
        # UNPAUSEALL -> STATE_READY; nunca pause/aux_code
        event_type = AgentActivityEventV2.EventType.STATE_READY
    elif event == ActividadAgenteLog.PAUSE:
        if not pausa_id or pausa_id == '0':
            # ACW: sin pause/aux_code
            event_type = AgentActivityEventV2.EventType.STATE_ACW
        else:
            event_type = AgentActivityEventV2.EventType.STATE_PAUSED
            try:
                pid = int(pausa_id)
            except (TypeError, ValueError):
                pid = None
            if pid is not None:
                from ominicontacto_app.models import Pausa
                pausa = Pausa.objects.filter(pk=pid).first()
                if pausa is not None:
                    pause = pausa
                else:
                    aux_code = pausa_id
                    metadata['invalid_pause_id'] = True
            else:
                aux_code = pausa_id

    if event_type is None:
        return

    AgentActivityEventV2.objects.create(
        agente_id=agente_id,
        ts=ts,
        event_type=event_type,
        pause=pause,
        aux_code=aux_code,
        metadata=metadata,
    )


def write_hold_activity_event_v2(agente_id, ts, event_type, callid=None, **metadata_extra):
    """
    Crea un registro en AgentActivityEventV2 para un evento de hold/unhold del agente.
    Se invoca desde HoldCallView y ApiEventoHold tras persistir el evento en LlamadaLog.

    :param agente_id: int
    :param ts: datetime para el campo ts
    :param event_type: AgentActivityEventV2.EventType.STATE_ON_HOLD o STATE_OFF_HOLD
    :param callid: str | None (se guarda en metadata para correlación con la llamada)
    :param metadata_extra: dict adicional para metadata (opcional)
    """
    metadata = dict(metadata_extra)
    if callid is not None:
        metadata['callid'] = callid
    AgentActivityEventV2.objects.create(
        agente_id=agente_id,
        ts=ts,
        event_type=event_type,
        pause=None,
        aux_code=None,
        source=None,
        metadata=metadata,
    )


def write_agent_activity_event_v2_synthetic(agente_id, event_type, ts, source, metadata=None):
    """
    Crea un evento sintético en AgentActivityEventV2 sin pasar por ActividadAgenteLog.

    :param agente_id: int
    :param event_type: valor de AgentActivityEventV2.EventType
    :param ts: datetime
    :param source: str corto (max_length del campo source en V2)
    :param metadata: dict opcional
    :raises ValueError: source inválido o event_type inválido
    """
    if not source:
        raise ValueError('source is required for synthetic activity events')
    max_len = AgentActivityEventV2._meta.get_field('source').max_length
    if len(source) > max_len:
        raise ValueError('source exceeds max length {}'.format(max_len))

    valid_event_types = set([choice[0] for choice in AgentActivityEventV2.EventType.choices])
    if event_type not in valid_event_types:
        raise ValueError('invalid event_type for synthetic activity event')

    AgentActivityEventV2.objects.create(
        agente_id=agente_id,
        ts=ts,
        event_type=event_type,
        pause=None,
        aux_code=None,
        source=source,
        metadata=metadata or {},
    )
