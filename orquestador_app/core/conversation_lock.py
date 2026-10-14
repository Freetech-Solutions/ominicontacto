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
Serialize inbound conversation create/lookup across HA replicas.

msgs-orchestrator uses Redis Streams consumer groups, so two nodes may
handle consecutive messages from the same peer in parallel. Without a
per-conversation lock, both can create a conversation and send welcome.
"""
from __future__ import unicode_literals

import logging
import threading
import time
from contextlib import contextmanager

from ominicontacto_app.services.redis import ha_lock

logger = logging.getLogger(__name__)

DEFAULT_TTL_SEC = 30
DEFAULT_WAIT_SEC = 30
POLL_INTERVAL = 0.05


class ConversationLockTimeout(Exception):
    """Raised when the lock could not be acquired before wait expired."""


@contextmanager
def hold_conversation_lock(
        channel, peer_id, ttl=DEFAULT_TTL_SEC, wait=DEFAULT_WAIT_SEC):
    """
    Hold an exclusive Redis lock for (channel, peer_id).

    Renews while the block runs. On Redis errors during acquire, logs and
    proceeds without a lock (fail-open) so chat is not bricked if Redis
    blips. On contention past ``wait``, raises ConversationLockTimeout so
    the stream consumer can skip XACK and retry later.
    """
    key = 'OML:HA:CONV:{0}:{1}'.format(channel, peer_id)
    token = ha_lock.make_token()
    ttl = int(ttl)
    deadline = time.monotonic() + float(wait)
    acquired = False

    while time.monotonic() < deadline:
        try:
            if ha_lock.acquire(key, ttl, token):
                acquired = True
                break
        except Exception:
            logger.exception(
                'conversation_lock.acquire failed key=%s; proceeding unlocked',
                key,
            )
            yield None
            return
        time.sleep(POLL_INTERVAL)

    if not acquired:
        raise ConversationLockTimeout(key)

    stop = threading.Event()
    renew_every = max(POLL_INTERVAL, float(ttl) / 3.0)

    def _heartbeat():
        while not stop.wait(renew_every):
            if not ha_lock.renew(key, token, ttl):
                logger.warning('conversation_lock.renew lost key=%s', key)
                return

    thread = threading.Thread(
        target=_heartbeat, name='conv-lock-renew', daemon=True)
    thread.start()
    try:
        yield key
    finally:
        stop.set()
        thread.join(timeout=renew_every + 1.0)
        ha_lock.release(key, token)
