# -*- coding: utf-8 -*-
"""Unit tests for orquestador_app.core.conversation_lock."""
from __future__ import unicode_literals

import threading
import time
import unittest
from unittest.mock import patch

from orquestador_app.core.conversation_lock import (
    ConversationLockTimeout,
    hold_conversation_lock,
)
from ominicontacto_app.services.redis import ha_lock


class FakeRedis(object):
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
        return True

    def get(self, key):
        self._expire_if_needed(key)
        return self.store.get(key)

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                self.ttls.pop(key, None)
                self.expiry.pop(key, None)
                deleted += 1
        return deleted

    def eval(self, script, numkeys, *args):
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


class ConversationLockTests(unittest.TestCase):

    def setUp(self):
        self.redis = FakeRedis()
        self._patcher = patch.object(ha_lock, 'get_redis', return_value=self.redis)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_serializes_critical_section_for_same_peer(self):
        order = []
        barrier = threading.Event()

        def first():
            with hold_conversation_lock('whatsapp', '1:54911', ttl=5, wait=2):
                order.append('a-enter')
                barrier.set()
                time.sleep(0.25)
                order.append('a-exit')

        def second():
            self.assertTrue(barrier.wait(timeout=1))
            with hold_conversation_lock('whatsapp', '1:54911', ttl=5, wait=2):
                order.append('b-enter')
                order.append('b-exit')

        t1 = threading.Thread(target=first)
        t2 = threading.Thread(target=second)
        t1.start()
        t2.start()
        t1.join(timeout=3)
        t2.join(timeout=3)
        self.assertEqual(order, ['a-enter', 'a-exit', 'b-enter', 'b-exit'])

    def test_timeout_when_lock_held(self):
        held = threading.Event()
        done = threading.Event()

        def holder():
            with hold_conversation_lock('whatsapp', '2:x', ttl=5, wait=1):
                held.set()
                done.wait(timeout=2)

        t = threading.Thread(target=holder)
        t.start()
        self.assertTrue(held.wait(timeout=1))
        with self.assertRaises(ConversationLockTimeout):
            with hold_conversation_lock('whatsapp', '2:x', ttl=5, wait=0.2):
                pass
        done.set()
        t.join(timeout=2)

    def test_fail_open_when_acquire_raises(self):
        with patch.object(ha_lock, 'acquire', side_effect=RuntimeError('redis down')):
            ran = []
            with hold_conversation_lock('whatsapp', '3:y', ttl=1, wait=0.1):
                ran.append(1)
            self.assertEqual(ran, [1])

    def test_lock_key_namespace(self):
        with hold_conversation_lock('facebook', '9:user', ttl=5, wait=1) as key:
            self.assertEqual(key, 'OML:HA:CONV:facebook:9:user')
            self.assertIn(key, self.redis.store)


if __name__ == '__main__':
    unittest.main()
