import json


def _agent_id_from_key(key):
    prefix = 'OML:VOICEBOT-ACTIVE-CALLS:'
    if key.startswith(prefix):
        return key[len(prefix):]
    parts = key.split(':')
    return parts[-1] if parts else ''


def _row_id(agent_id, call_id):
    safe_call = str(call_id).replace(':', '-')
    return '{0}__{1}'.format(agent_id, safe_call)


def _snapshot_key(agent_id):
    return 'OML:GEAR:VB-SNAPSHOT:{0}'.format(agent_id)


def _active_calls_key(agent_id):
    return 'OML:VOICEBOT-ACTIVE-CALLS:{0}'.format(agent_id)


def _voicebot_streams(agent_key, agent_id):
    try:
        raw = execute('HGET', agent_key, 'VOICEBOT_STREAMS')
    except Exception:
        raw = None
    if raw:
        streams = [s for s in raw.split(',') if s]
        if streams:
            return streams

    streams = []
    try:
        sup_keys = execute('KEYS', 'OML:SUPERVISOR:*')
    except Exception:
        sup_keys = []
    if not sup_keys:
        return []

    agent_id_str = str(agent_id)
    for sup_key in sup_keys:
        try:
            sup_hash = execute('HGETALL', sup_key)
        except Exception:
            sup_hash = None
        if not sup_hash:
            continue
        if agent_id_str not in sup_hash and agent_id not in sup_hash:
            continue
        sup_id = sup_key.rsplit(':', 1)[-1]
        stream = 'supervisor_{0}_voicebots'.format(sup_id)
        if stream not in streams:
            streams.append(stream)
        try:
            existing = execute('HGET', agent_key, 'VOICEBOT_STREAMS')
            vb_list = existing.split(',') if existing else []
            if stream not in vb_list:
                vb_list.append(stream)
                execute('HSET', agent_key, 'VOICEBOT_STREAMS', ','.join(vb_list))
        except Exception:
            pass
    return streams


def _publish_to_streams(streams, payload_str):
    for stream in streams:
        execute(
            'XADD', stream, 'MAXLEN', '~', STREAM_LENGHT, '*',
            'value', payload_str,
        )


def _stream_payload_str(payload_dict):
    items = []
    for key, val in payload_dict.items():
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            items.append("'{}': {}".format(key, val))
        else:
            escaped = str(val).replace("'", "\\'")
            items.append("'{}': '{}'".format(key, escaped))
    return '{' + ', '.join(items) + '}'


def _payload_to_data(payload):
    if isinstance(payload, dict):
        return payload
    if payload is None:
        return {}
    try:
        return json.loads(payload)
    except Exception:
        return {}


def _build_upsert(agent_id, call_id, payload):
    data = _payload_to_data(payload)
    row = {
        'action': 'upsert',
        'row_id': _row_id(agent_id, call_id),
        'agent_id': int(agent_id) if str(agent_id).isdigit() else agent_id,
        'call_id': str(data.get('call_id') or call_id),
        'CAMPAIGN': str(data.get('campaign_id') or ''),
        'CONTACT_NUMBER': str(data.get('contact_number') or ''),
        'STATUS': str(data.get('status') or 'ONCALL'),
        'TIMESTAMP': data.get('timestamp') or 0,
        'bridge_id': str(data.get('bridge_id') or ''),
        'node_id': str(data.get('node_id') or ''),
    }
    return _stream_payload_str(row)


def _current_hash(x, key):
    value = x.get('value')
    if isinstance(value, dict):
        return value
    try:
        raw = execute('HGETALL', key)
    except Exception:
        raw = None
    return raw if raw else {}


def _update_snapshot(agent_id, current):
    snap_key = _snapshot_key(agent_id)
    execute('DEL', snap_key)
    if not current:
        return
    for call_id, payload_str in current.items():
        if isinstance(payload_str, dict):
            payload_str = json.dumps(payload_str)
        execute('HSET', snap_key, call_id, payload_str)


def process_event(x):
    key = x['key']
    agent_id = _agent_id_from_key(key)
    if not agent_id:
        return

    agent_key = 'OML:AGENT:{0}'.format(agent_id)
    streams = _voicebot_streams(agent_key, agent_id)
    if not streams:
        return

    snap_key = _snapshot_key(agent_id)
    previous = execute('HGETALL', snap_key) or {}
    current = _current_hash(x, key)

    for call_id in previous:
        if call_id not in current:
            delete_payload = _stream_payload_str({
                'action': 'delete',
                'row_id': _row_id(agent_id, call_id),
            })
            _publish_to_streams(streams, delete_payload)

    for call_id, payload_str in current.items():
        _publish_to_streams(streams, _build_upsert(agent_id, call_id, payload_str))

    _update_snapshot(agent_id, current)


STREAM_LENGHT = %d

GearsBuilder(desc='sup_voicebot') \
    .foreach(process_event) \
    .register('OML:VOICEBOT-ACTIVE-CALLS:*', keyTypes=['hash'], mode='sync')
