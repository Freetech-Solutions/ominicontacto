# -*- coding: utf-8 -*-
# Copyright (C) 2026 Freetech Solutions
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

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from email_app.service.consumer.account import AccountConsumer


class AccountConsumerTest(SimpleTestCase):

    def test_asubscribe_reconnects_after_fetch_timeout(self):
        async_to_sync(self._assert_reconnects_after_fetch_timeout)()

    async def _assert_reconnects_after_fetch_timeout(self):
        account = SimpleNamespace(pk=16, settings={"inbound": {}}, insights={})
        consumer = AccountConsumer(reconnect_delay=0)
        first_client = object()
        second_client = object()
        second_fetch_started = asyncio.Event()
        block_second_fetch = asyncio.Event()
        fetch_calls = 0

        async def fetch(client, account):
            nonlocal fetch_calls
            fetch_calls += 1
            if fetch_calls == 1:
                raise asyncio.TimeoutError()
            second_fetch_started.set()
            await block_second_fetch.wait()

        consumer.fetch = fetch
        consumer.fetch_cooldown = AsyncMock()

        with patch(
            "email_app.service.consumer.account.aioimaplib.client",
            new=AsyncMock(side_effect=[first_client, second_client]),
        ) as client_mock, patch(
            "email_app.service.consumer.account.aioimaplib.login",
            new=AsyncMock(),
        ) as login_mock, patch(
            "email_app.service.consumer.account.aioimaplib.logout",
            new=AsyncMock(),
        ) as logout_mock, patch(
            "email_app.service.consumer.account.aioimaplib.close",
        ) as close_mock, patch(
            "email_app.service.consumer.account.log.exception",
        ) as log_exception_mock:
            task = asyncio.create_task(consumer.asubscribe(account), name="acc-16")
            await asyncio.wait_for(second_fetch_started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertEqual(client_mock.await_count, 2)
        self.assertEqual(login_mock.await_count, 2)
        self.assertEqual(logout_mock.await_count, 1)
        self.assertTrue(log_exception_mock.called)
        close_mock.assert_any_call(first_client)
        close_mock.assert_any_call(second_client)

    def test_check_result_removes_finished_task_from_map(self):
        async_to_sync(self._assert_check_result_removes_finished_task_from_map)()

    async def _assert_check_result_removes_finished_task_from_map(self):
        consumer = AccountConsumer()

        async def boom():
            raise RuntimeError("connection died")

        task = asyncio.create_task(boom(), name="acc-16")
        consumer.tasks_map[16] = task
        with patch("email_app.service.consumer.account.log.exception"):
            task.add_done_callback(lambda task: consumer.check_result(16, task))
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        self.assertNotIn(16, consumer.tasks_map)
