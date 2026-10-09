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
Redis HA helpers for singleton workers.

Always uses Redis db 0 via create_redis_connection. Pub/sub listeners may
subscribe on another db; claim keys still live on db 0.
"""
from __future__ import unicode_literals

import hashlib
import json
import logging
import os
import socket
import threading
import time
import uuid

from ominicontacto_app.services.redis.connection import create_redis_connection

logger = logging.getLogger(__name__)

RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""

RENEW_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
else
  return 0
end
"""

POLL_INTERVAL = 0.05


def get_redis():
    return create_redis_connection(db=0)


def node_id():
    """
    Stable identity for this process across HA replicas.

    Prefer OML_NODE_ID (inventory_hostname from django.env): Podman pods
    without Hostname= often share the same gethostname() on every node.
    """
    configured = os.environ.get('OML_NODE_ID', '').strip()
    if configured:
        return configured
    return socket.gethostname()


def make_token():
    return '{0}:{1}'.format(node_id(), uuid.uuid4().hex)


def acquire(key, ttl, token, redis_conn=None):
    redis_conn = redis_conn or get_redis()
    return bool(redis_conn.set(key, token, nx=True, ex=int(ttl)))


def release(key, token, redis_conn=None):
    redis_conn = redis_conn or get_redis()
    try:
        return bool(redis_conn.eval(RELEASE_LUA, 1, key, token))
    except Exception:
        logger.exception('ha_lock.release failed key=%s', key)
        return False


def renew(key, token, ttl, redis_conn=None):
    """Extend lock TTL if we still own the token."""
    redis_conn = redis_conn or get_redis()
    try:
        return bool(redis_conn.eval(RENEW_LUA, 1, key, token, int(ttl)))
    except Exception:
        logger.exception('ha_lock.renew failed key=%s', key)
        return False


def event_ident(event_data):
    """
    Identity for claim_event across pub/sub replicas.

    Do not use campaign-scoped ``id`` alone: CAMP/WAIT/QUEUE/DISPOSITION/
    EXIT_ABANDON publishers put campaign_id in ``id``, which would drop every
    later event of that type for the claim TTL (even on a single node).

    Prefer per-occurrence fields (event_id/uuid/uniqueid/callid). Otherwise
    hash the full payload so the same delivery dedupes on all replicas while
    distinct publishes remain distinct when their fields differ.
    """
    if not isinstance(event_data, dict):
        event_data = {'raw': event_data}
    for field in ('event_id', 'uuid', 'uniqueid', 'callid'):
        value = event_data.get(field)
        if value is not None and value != '':
            parts = [str(value)]
            for extra in ('type', 'event', 'delta', 'reason'):
                extra_val = event_data.get(extra)
                if extra_val is not None and extra_val != '':
                    parts.append(str(extra_val))
            return ':'.join(parts)
    payload = json.dumps(event_data, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()


def claim_event(channel, event_data, ttl=120, redis_conn=None):
    """
    Try to claim an event for processing.

    Returns (claimed, key, token). On handler failure the caller must
    release(key, token) so another copy can retry within the TTL window.
    """
    redis_conn = redis_conn or get_redis()
    ident = event_ident(event_data)
    key = 'OML:HA:EVT:{0}:{1}'.format(channel, ident)
    token = make_token()
    return acquire(key, ttl, token, redis_conn=redis_conn), key, token


def try_slot(name, slot, ttl, redis_conn=None):
    """
    Non-blocking slot acquire for async callers.

    Returns (acquired, key, token). If already DONE, acquired is False and
    token is None. Caller must mark_done + release when work finishes.
    Long-running holders should call renew(key, token, ttl) periodically.
    """
    redis_conn = redis_conn or get_redis()
    key = 'OML:HA:SLOT:{0}:{1}'.format(name, slot)
    done_key = '{0}:DONE'.format(key)
    if redis_conn.get(done_key):
        return False, key, None
    token = make_token()
    if acquire(key, ttl, token, redis_conn=redis_conn):
        # Re-check after acquire: another node may have set DONE and released.
        if redis_conn.get(done_key):
            release(key, token, redis_conn=redis_conn)
            return False, key, None
        return True, key, token
    return False, key, None


def mark_done(key, ttl, redis_conn=None):
    redis_conn = redis_conn or get_redis()
    redis_conn.set('{0}:DONE'.format(key), '1', ex=int(ttl))


def _execute_under_lock(redis_conn, key, token, ttl, done_key, fn):
    """
    Run fn while renewing the lock; mark DONE on success.

    Returns True if fn ran, False if DONE appeared before fn.
    """
    stop = threading.Event()
    renew_every = max(POLL_INTERVAL, float(ttl) / 3.0)

    def _heartbeat():
        while not stop.wait(renew_every):
            if not renew(key, token, ttl, redis_conn=redis_conn):
                logger.warning('ha_lock.renew lost ownership key=%s', key)
                return

    thread = threading.Thread(
        target=_heartbeat, name='ha-lock-renew', daemon=True)
    thread.start()
    try:
        if redis_conn.get(done_key):
            return False
        fn()
        redis_conn.set(done_key, '1', ex=ttl)
        return True
    finally:
        stop.set()
        thread.join(timeout=renew_every + 1.0)
        release(key, token, redis_conn=redis_conn)


def run_once(name, slot, ttl, fn, redis_conn=None, poll_interval=POLL_INTERVAL):
    """
    Execute fn at most once for (name, slot) across the cluster.

    Returns True if this process executed fn, False otherwise.
    Wait is capped at ttl so a single-thread APScheduler is not blocked
    past the next tick window.

    While fn runs the lock is renewed (~ttl/3) so a slow body cannot lose
    the slot to a waiting peer.
    """
    redis_conn = redis_conn or get_redis()
    key = 'OML:HA:SLOT:{0}:{1}'.format(name, slot)
    done_key = '{0}:DONE'.format(key)
    ttl = int(ttl)

    if redis_conn.get(done_key):
        return False

    token = make_token()
    if acquire(key, ttl, token, redis_conn=redis_conn):
        return _execute_under_lock(redis_conn, key, token, ttl, done_key, fn)

    deadline = time.monotonic() + ttl
    retried = False
    while time.monotonic() < deadline:
        if redis_conn.get(done_key):
            return False
        if redis_conn.get(key) is None and not redis_conn.get(done_key):
            if retried:
                return False
            retried = True
            token = make_token()
            if acquire(key, ttl, token, redis_conn=redis_conn):
                return _execute_under_lock(
                    redis_conn, key, token, ttl, done_key, fn)
            return False
        time.sleep(poll_interval)

    return False
