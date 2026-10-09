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

"""Unit tests for ominicontacto_app.services.redis.ha_lock."""
from __future__ import unicode_literals

import time
import unittest
from unittest.mock import patch

from ominicontacto_app.services.redis import ha_lock


class FakeRedis(object):
    """Minimal Redis stand-in for ha_lock unit tests."""

    def __init__(self):
        self.store = {}
        self.ttls = {}
        self.expiry = {}

    def _expire_if_needed(self, key):
        deadline = self.expiry.get(key)
        if deadline is not None and time.monotonic() >= deadline:
            self.store.pop(key, None)
            self.ttls.pop(key, None)
            self.expiry.pop(key, None)

    def set(self, key, value, nx=False, ex=None):
        self._expire_if_needed(key)
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
            self.expiry[key] = time.monotonic() + float(ex)
        else:
            self.ttls.pop(key, None)
            self.expiry.pop(key, None)
        return True

    def get(self, key):
        self._expire_if_needed(key)
        return self.store.get(key)

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            self._expire_if_needed(key)
            if key in self.store:
                del self.store[key]
                self.ttls.pop(key, None)
                self.expiry.pop(key, None)
                deleted += 1
        return deleted

    def eval(self, script, numkeys, *args):
        # release / renew Lua used by ha_lock
        key = args[0]
        token = args[1]
        self._expire_if_needed(key)
        if 'expire' in script:
            ttl = int(args[2])
            if self.store.get(key) == token:
                self.ttls[key] = ttl
                self.expiry[key] = time.monotonic() + float(ttl)
                return 1
            return 0
        if self.store.get(key) == token:
            return self.delete(key)
        return 0


class HaLockRunOnceTests(unittest.TestCase):

    def setUp(self):
        self.redis = FakeRedis()
        self._patcher = patch.object(ha_lock, 'get_redis', return_value=self.redis)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_run_once_executes_only_one_of_two(self):
        calls = []

        def fn():
            calls.append(1)

        self.assertTrue(ha_lock.run_once('clock', 1, ttl=5, fn=fn, poll_interval=0.01))
        self.assertFalse(ha_lock.run_once('clock', 1, ttl=5, fn=fn, poll_interval=0.01))
        self.assertEqual(calls, [1])
        self.assertEqual(self.redis.get('OML:HA:SLOT:clock:1:DONE'), '1')
        self.assertIn('OML:HA:SLOT:clock:1:DONE', self.redis.ttls)

    def test_run_once_retries_when_lock_gone_without_done(self):
        import threading

        calls = []
        self.redis.store['OML:HA:SLOT:clock:2'] = 'dead-token'

        def drop_lock():
            time.sleep(0.05)
            self.redis.store.pop('OML:HA:SLOT:clock:2', None)

        threading.Thread(target=drop_lock, daemon=True).start()
        self.assertTrue(
            ha_lock.run_once(
                'clock', 2, ttl=2, fn=lambda: calls.append(1), poll_interval=0.01)
        )
        self.assertEqual(calls, [1])
        self.assertEqual(self.redis.get('OML:HA:SLOT:clock:2:DONE'), '1')

    def test_run_once_wait_capped_by_ttl(self):
        self.redis.store['OML:HA:SLOT:clock:3'] = 'other'
        started = time.monotonic()
        executed = ha_lock.run_once(
            'clock', 3, ttl=1, fn=lambda: None, poll_interval=0.05)
        elapsed = time.monotonic() - started
        self.assertFalse(executed)
        self.assertLess(elapsed, 2.0)

    def test_run_once_rechecks_done_after_acquire(self):
        """TOCTOU: DONE appears after GET and before/during acquire."""
        calls = []
        original_acquire = ha_lock.acquire

        def acquire_after_done(key, ttl, token, redis_conn=None):
            # Simulate peer finishing between our GET DONE and SET NX.
            self.redis.store['OML:HA:SLOT:clock:4:DONE'] = '1'
            self.redis.ttls['OML:HA:SLOT:clock:4:DONE'] = 5
            return original_acquire(key, ttl, token, redis_conn=redis_conn)

        with patch.object(ha_lock, 'acquire', side_effect=acquire_after_done):
            executed = ha_lock.run_once(
                'clock', 4, ttl=5, fn=lambda: calls.append(1), poll_interval=0.01)
        self.assertFalse(executed)
        self.assertEqual(calls, [])

    def test_try_slot_rechecks_done_after_acquire(self):
        original_acquire = ha_lock.acquire

        def acquire_after_done(key, ttl, token, redis_conn=None):
            self.redis.store['OML:HA:SLOT:async:1:DONE'] = '1'
            return original_acquire(key, ttl, token, redis_conn=redis_conn)

        with patch.object(ha_lock, 'acquire', side_effect=acquire_after_done):
            acquired, key, token = ha_lock.try_slot('async', 1, ttl=5)
        self.assertFalse(acquired)
        self.assertIsNone(token)
        self.assertNotIn(key, self.redis.store)

    def test_renew_extends_ttl_when_token_matches(self):
        key = 'OML:HA:SLOT:clock:renew'
        token = 'owner-token'
        self.redis.set(key, token, nx=True, ex=2)
        first_expiry = self.redis.expiry[key]
        time.sleep(0.05)
        self.assertTrue(ha_lock.renew(key, token, ttl=5))
        self.assertEqual(self.redis.ttls[key], 5)
        self.assertGreater(self.redis.expiry[key], first_expiry)
        self.assertFalse(ha_lock.renew(key, 'other-token', ttl=5))

    def test_run_once_renew_prevents_peer_during_long_fn(self):
        """Without renew, lock EX would let a peer steal mid-fn."""
        import threading

        calls = []
        results = []

        def slow_fn():
            calls.append('holder')
            time.sleep(1.2)

        def peer_fn():
            calls.append('peer')

        def run_holder():
            results.append(ha_lock.run_once(
                'clock', 8, ttl=1, fn=slow_fn, poll_interval=0.05))

        def run_peer():
            time.sleep(0.15)
            results.append(ha_lock.run_once(
                'clock', 8, ttl=1, fn=peer_fn, poll_interval=0.05))

        holder = threading.Thread(target=run_holder)
        peer = threading.Thread(target=run_peer)
        holder.start()
        peer.start()
        holder.join(timeout=4)
        peer.join(timeout=4)
        self.assertEqual(calls, ['holder'])
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.redis.get('OML:HA:SLOT:clock:8:DONE'), '1')

    def test_claim_event_same_occurrence_once(self):
        event = {'uniqueid': 'u-42', 'type': 'CAMP', 'id': 5, 'event': 'DIAL'}
        claimed_a, key_a, token_a = ha_lock.claim_event('OML:CHANNEL:CALLEVENTS', event)
        claimed_b, key_b, token_b = ha_lock.claim_event('OML:CHANNEL:CALLEVENTS', event)
        self.assertTrue(claimed_a)
        self.assertFalse(claimed_b)
        self.assertEqual(key_a, key_b)
        self.assertTrue(ha_lock.release(key_a, token_a))
        claimed_c, _, _ = ha_lock.claim_event('OML:CHANNEL:CALLEVENTS', event)
        self.assertTrue(claimed_c)

    def test_claim_event_different_uniqueids_are_distinct(self):
        claimed_a, _, _ = ha_lock.claim_event(
            'ch', {'uniqueid': 'u1', 'type': 'CAMP', 'id': 5, 'event': 'DIAL'})
        claimed_b, _, _ = ha_lock.claim_event(
            'ch', {'uniqueid': 'u2', 'type': 'CAMP', 'id': 5, 'event': 'DIAL'})
        self.assertTrue(claimed_a)
        self.assertTrue(claimed_b)

    def test_event_ident_prefers_event_id(self):
        ident = ha_lock.event_ident({'event_id': 'e1', 'id': 9, 'type': 'X'})
        self.assertEqual(ident, 'e1:X')

    def test_event_ident_ignores_campaign_id_alone(self):
        """Campaign-scoped id must not become the claim identity."""
        camp_dial = {'type': 'CAMP', 'id': 5, 'event': 'DIAL', 'call_type': '2'}
        camp_connect = {'type': 'CAMP', 'id': 5, 'event': 'CONNECT', 'call_type': '2'}
        wait_a = {'type': 'WAIT', 'id': 5, 'time': 12}
        wait_b = {'type': 'WAIT', 'id': 5, 'time': 20}
        self.assertNotEqual(ha_lock.event_ident(camp_dial), ha_lock.event_ident(camp_connect))
        self.assertNotEqual(ha_lock.event_ident(wait_a), ha_lock.event_ident(wait_b))
        # Same delivery (identical payload) still dedupes across replicas.
        self.assertEqual(ha_lock.event_ident(camp_dial), ha_lock.event_ident(dict(camp_dial)))

    def test_event_ident_uses_callid_for_queue(self):
        enter = {
            'type': 'QUEUE', 'id': '5', 'size': 1, 'delta': '1',
            'callid': 'c-1', 'timestamp': 1.0,
        }
        leave = {
            'type': 'QUEUE', 'id': '5', 'size': 0, 'delta': '-1',
            'callid': 'c-1', 'reason': 'ANSWERED', 'timestamp': 2.0,
        }
        other = {
            'type': 'QUEUE', 'id': '5', 'size': 1, 'delta': '1',
            'callid': 'c-2', 'timestamp': 1.0,
        }
        self.assertTrue(ha_lock.event_ident(enter).startswith('c-1:'))
        self.assertNotEqual(ha_lock.event_ident(enter), ha_lock.event_ident(leave))
        self.assertNotEqual(ha_lock.event_ident(enter), ha_lock.event_ident(other))


class HaLockClaimUtilityTests(unittest.TestCase):
    """claim_event remains available; listeners use Streams consumer groups."""

    def setUp(self):
        self.redis = FakeRedis()
        self._patcher = patch.object(ha_lock, 'get_redis', return_value=self.redis)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_two_claims_one_handler(self):
        managed = []
        event = {'uniqueid': 'abc-123', 'type': 'WAIT', 'id': 5, 'time': 12}

        for _ in range(2):
            claimed, key, token = ha_lock.claim_event('OML:CHANNEL:CALLEVENTS', event)
            if claimed:
                try:
                    managed.append(event['uniqueid'])
                except Exception:
                    ha_lock.release(key, token)
                    raise

        self.assertEqual(managed, ['abc-123'])


class HaLockNodeIdTests(unittest.TestCase):

    def test_node_id_prefers_oml_node_id_env(self):
        with patch.dict('os.environ', {'OML_NODE_ID': 'test_ait_Node-1'}):
            self.assertEqual(ha_lock.node_id(), 'test_ait_Node-1')

    def test_make_token_uses_oml_node_id(self):
        with patch.dict('os.environ', {'OML_NODE_ID': 'test_ait_Node-2'}):
            token = ha_lock.make_token()
        self.assertTrue(token.startswith('test_ait_Node-2:'))
