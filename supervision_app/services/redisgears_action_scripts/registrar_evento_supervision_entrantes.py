def process_event(x):
    STREAM_LENGTH = %d  # noqa: #E999
    POSICION_ID_EN_CLAVE_REDIS = 25
    value = x['value']
    if value is not None:
        campaign_id = x['key'][POSICION_ID_EN_CLAVE_REDIS:]
        streams = []
        try:
            data_redis_key = 'OML:SUPERVISION_CAMPAIGN_STREAMS:' + campaign_id
            streams = execute('HGET', data_redis_key, 'STREAMS')
            streams = streams.split(',')
        except:
            pass
        for stream in streams:
            if execute('exists', stream) == 1 and value is not None:
                value['id'] = campaign_id
                execute('XADD', stream, 'MAXLEN', '~', STREAM_LENGTH, '*', 'value', value)


GearsBuilder(desc='sup_entrantes') \
    .map(process_event) \
    .register('%s', keyTypes=['hash'])
