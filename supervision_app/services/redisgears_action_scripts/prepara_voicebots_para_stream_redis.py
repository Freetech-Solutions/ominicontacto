import json


def prepara_voicebots_para_stream_redis(x):
    POSICION_ID_EN_CLAVE_REDIS = 15
    supervisor_id = x['key'][POSICION_ID_EN_CLAVE_REDIS:]
    stream = 'supervisor_{0}_%s'.format(supervisor_id)
    for v in x['value'].keys():
        agent_key = 'OML:AGENT:{0}'.format(v)
        if execute('exists', agent_key) != 1:
            continue
        voicebot_flag = execute('HGET', agent_key, 'VOICEBOT')
        active_calls_key = 'OML:VOICEBOT-ACTIVE-CALLS:{0}'.format(v)
        has_active_calls = execute('exists', active_calls_key) == 1
        if voicebot_flag != '1' and not has_active_calls:
            continue
        vb_streams = execute('HGET', agent_key, 'VOICEBOT_STREAMS')
        vb_streams_list = vb_streams.split(',') if vb_streams else []
        if stream not in vb_streams_list:
            vb_streams_list.append(stream)
            execute('HSET', agent_key, 'VOICEBOT_STREAMS', ','.join(vb_streams_list))
        sup_value = json.loads(x['value'][v])
        agent_group = sup_value['grupo']
        execute(
            'HSET', agent_key, 'GROUP', agent_group,
            'CAMPANAS', sup_value['campana'], 'id', v,
        )
        if voicebot_flag != '1':
            execute('HSET', agent_key, 'VOICEBOT', '1')
    if execute('exists', stream) == 0:
        execute('XADD', stream, '*', 'start', '{"value": "false"}')


GearsBuilder() \
    .map(prepara_voicebots_para_stream_redis) \
    .run('OML:SUPERVISOR:%s')
