# -*- coding: utf-8 -*-
"""
Lectura de llamadas voicebot activas desde Redis (OML:VOICEBOT-ACTIVE-CALLS:{agent_id}).
"""

from __future__ import unicode_literals

import json
import logging

logger = logging.getLogger(__name__)

VOICEBOT_ACTIVE_CALLS_KEY = 'OML:VOICEBOT-ACTIVE-CALLS:{agent_id}'


def get_voicebot_call_from_hash(redis_connection, agent_id, call_id):
    """
    Resuelve node_id y call_id desde el hash de llamadas voicebot activas.

    Returns:
        dict | None: {call_id, node_id, status, bridge_id, campaign_id, contact_number}
    """
    if not redis_connection or not agent_id or not call_id:
        return None

    active_key = VOICEBOT_ACTIVE_CALLS_KEY.format(agent_id=agent_id)
    try:
        payload_raw = redis_connection.hget(active_key, str(call_id))
    except Exception as e:
        logger.warning(
            'Error leyendo %s campo %s: %s',
            active_key,
            call_id,
            e,
        )
        return None

    payload_str = _normalize_redis_value(payload_raw)
    if not payload_str:
        return None

    try:
        data = json.loads(payload_str)
    except (ValueError, TypeError) as e:
        logger.warning('JSON inválido en %s campo %s: %s', active_key, call_id, e)
        return None

    return {
        'call_id': str(data.get('call_id') or call_id),
        'node_id': str(data.get('node_id') or '').strip(),
        'status': str(data.get('status') or ''),
        'bridge_id': str(data.get('bridge_id') or ''),
        'campaign_id': str(data.get('campaign_id') or ''),
        'contact_number': str(data.get('contact_number') or ''),
    }


def _normalize_redis_value(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return value


def _agent_display_name(agente):
    user = getattr(agente, 'user', None)
    if user:
        nombre = (user.get_full_name() or '').strip()
        if nombre:
            return nombre
        username = getattr(user, 'username', '') or ''
        if username:
            return username
    return 'Bot {0}'.format(agente.id)


def get_voicebot_active_call_rows(redis_connection, agentes_voicebot, campaign_id=None):
    """
    Retorna una fila por llamada voicebot activa.

    Args:
        redis_connection: cliente Redis db=0
        agentes_voicebot: iterable de AgenteProfile (voicebot=True)
        campaign_id: filtrar por campaña (opcional)

    Returns:
        list[dict]: filas con row_id, agent_id, nombre, CAMPAIGN, CONTACT_NUMBER,
                    STATUS, TIMESTAMP, call_id, is_voicebot
    """
    if not redis_connection or not agentes_voicebot:
        return []

    campaign_filter = str(campaign_id) if campaign_id is not None else None
    rows = []

    for agente in agentes_voicebot:
        agent_id = agente.id
        nombre = _agent_display_name(agente)
        active_key = VOICEBOT_ACTIVE_CALLS_KEY.format(agent_id=agent_id)

        try:
            raw_calls = redis_connection.hgetall(active_key) or {}
        except Exception as e:
            logger.warning(
                'Error leyendo %s para agente %s: %s',
                active_key,
                agent_id,
                e,
            )
            continue

        for call_id_raw, payload_raw in raw_calls.items():
            call_id = _normalize_redis_value(call_id_raw)
            payload_str = _normalize_redis_value(payload_raw)
            if not call_id or not payload_str:
                continue

            try:
                data = json.loads(payload_str)
            except (ValueError, TypeError) as e:
                logger.warning(
                    'JSON inválido en %s campo %s: %s',
                    active_key,
                    call_id,
                    e,
                )
                continue

            row_campaign = str(data.get('campaign_id') or '')
            if campaign_filter and row_campaign != campaign_filter:
                continue

            row_call_id = str(data.get('call_id') or call_id)
            timestamp = data.get('timestamp') or 0
            try:
                timestamp = int(timestamp)
            except (ValueError, TypeError):
                timestamp = 0

            rows.append({
                'row_id': '{0}__{1}'.format(agent_id, row_call_id.replace(':', '-')),
                'agent_id': agent_id,
                'id': agent_id,
                'nombre': nombre,
                'CAMPAIGN': row_campaign,
                'CONTACT_NUMBER': str(data.get('contact_number') or ''),
                'STATUS': str(data.get('status') or 'ONCALL'),
                'TIMESTAMP': timestamp,
                'call_id': row_call_id,
                'is_voicebot': True,
            })

    return rows
