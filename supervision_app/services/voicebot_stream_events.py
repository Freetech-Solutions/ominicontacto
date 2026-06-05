# -*- coding: utf-8 -*-
"""
Lógica pura para eventos de stream voicebot (upsert/delete por llamada).
Usada en tests; el gear RedisGears replica esta lógica inline.
"""

from __future__ import unicode_literals

import json

VOICEBOT_SNAPSHOT_KEY = 'OML:GEAR:VB-SNAPSHOT:{agent_id}'


def agent_id_from_active_calls_key(key):
    prefix = 'OML:VOICEBOT-ACTIVE-CALLS:'
    if key.startswith(prefix):
        return key[len(prefix):]
    parts = key.split(':')
    return parts[-1] if parts else ''


def row_id(agent_id, call_id):
    safe_call = str(call_id).replace(':', '-')
    return '{0}__{1}'.format(agent_id, safe_call)


def stream_payload_str(payload_dict):
    items = []
    for key, val in payload_dict.items():
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            items.append("'{}': {}".format(key, val))
        else:
            escaped = str(val).replace("'", "\\'")
            items.append("'{}': '{}'".format(key, escaped))
    return '{' + ', '.join(items) + '}'


def build_upsert_event(agent_id, call_id, payload_str):
    if isinstance(payload_str, dict):
        data = payload_str
    else:
        try:
            data = json.loads(payload_str)
        except (ValueError, TypeError):
            data = {}
    return {
        'action': 'upsert',
        'row_id': row_id(agent_id, call_id),
        'agent_id': int(agent_id) if str(agent_id).isdigit() else agent_id,
        'call_id': str(data.get('call_id') or call_id),
        'CAMPAIGN': str(data.get('campaign_id') or ''),
        'CONTACT_NUMBER': str(data.get('contact_number') or ''),
        'STATUS': str(data.get('status') or 'ONCALL'),
        'TIMESTAMP': data.get('timestamp') or 0,
        'bridge_id': str(data.get('bridge_id') or ''),
        'node_id': str(data.get('node_id') or ''),
    }


def build_delete_event(agent_id, call_id):
    return {
        'action': 'delete',
        'row_id': row_id(agent_id, call_id),
    }


def diff_voicebot_hash_events(agent_id, previous, current):
    """
    Compara snapshot previo vs hash actual y retorna eventos upsert/delete.

    Args:
        agent_id: id del agente voicebot
        previous: dict call_id -> payload JSON str
        current: dict call_id -> payload JSON str

    Returns:
        list[dict]: eventos en orden delete primero, luego upsert
    """
    previous = previous or {}
    current = current or {}
    events = []

    for call_id in previous:
        if call_id not in current:
            events.append(build_delete_event(agent_id, call_id))

    for call_id, payload_str in current.items():
        events.append(build_upsert_event(agent_id, call_id, payload_str))

    return events
