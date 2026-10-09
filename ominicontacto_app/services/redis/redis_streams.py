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
from __future__ import unicode_literals

import json
import os

import redis
from django.conf import settings

from ominicontacto_app.services.redis.connection import create_redis_connection

# Supervision / dialer event streams (Redis DB 2)
STREAM_CALLEVENTS = 'OML:STREAM:CALLEVENTS'
STREAM_DISPOSITIONEVENTS = 'OML:STREAM:DISPOSITIONEVENTS'
STREAM_DIALER = 'OML:STREAM:DIALER'

GROUP_SUPERVISION_EVENTS = 'supervision-events'
GROUP_OMNIDIALER_EVENTS = 'omnidialer-events'

EVENT_STREAM_DB = 2
DEFAULT_EVENT_STREAM_MAXLEN = 10000


def event_stream_maxlen():
    try:
        return int(os.getenv('OML_EVENT_STREAM_MAXLEN', DEFAULT_EVENT_STREAM_MAXLEN))
    except (TypeError, ValueError):
        return DEFAULT_EVENT_STREAM_MAXLEN


class RedisStreams(object):

    def __init__(self, connection=None):
        super(RedisStreams, self).__init__()
        self.connection = connection
        if connection is None:
            self.connection = redis.Redis(
                host=settings.REDIS_HOSTNAME,
                port=settings.CONSTANCE_REDIS_CONNECTION['port'],
                decode_responses=True,
            )

    def write_stream(self, stream_name, content, max_stream_length=100):
        self.connection.execute_command(
            'XADD', stream_name, 'MAXLEN', '~', max_stream_length, '*', 'value', content)

    def write_event(self, stream_name, event_data, max_stream_length=None):
        """XADD a JSON event payload for supervision/dialer streams."""
        if max_stream_length is None:
            max_stream_length = event_stream_maxlen()
        if not isinstance(event_data, str):
            event_data = json.dumps(event_data)
        self.write_stream(stream_name, event_data, max_stream_length=max_stream_length)

    def flush(self, stream_name):
        self.connection.xtrim(name=stream_name, maxlen=0, approximate=False)

    def expire(self, stream_name, seconds=None):
        if seconds is None:
            seconds = 60 * 60 * 24 * 2
        self.connection.expire(stream_name, seconds)


def get_event_streams(connection=None):
    """RedisStreams bound to calldata/event DB (2)."""
    conn = connection or create_redis_connection(db=EVENT_STREAM_DB)
    return RedisStreams(connection=conn)
