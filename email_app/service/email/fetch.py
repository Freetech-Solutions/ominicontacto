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

import asyncio
import logging
import signal
from channels.layers import get_channel_layer

from ... import models
from ..consumer.account import AccountConsumer
from ..consumer.channel import ChannelConsumer
from ..consumer.command import CommandConsumer

channel_layer = get_channel_layer()
input_channel = "email-account"


log = logging.getLogger(__name__)


class EmailFetchService:
    def __init__(self):
        self.shutdown_requested = asyncio.Event()
        self.account_consumer = AccountConsumer()
        self.channel_consumer = ChannelConsumer(self.account_consumer)
        self.command_consumer = CommandConsumer(
            self.account_consumer,
            self.channel_consumer,
            self.shutdown_requested,
        )

    async def __aenter__(self):
        log.debug("starting")
        async for account in models.Account.objects.filter(active=True):
            self.account_consumer.subscribe(account)
        self.channel_consumer.subscribe(input_channel)
        self.command_consumer.subscribe(
            True,
            {
                signal.SIGHUP,
                signal.SIGINT,
                signal.SIGUSR1,
            },
        )
        log.debug("started")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        log.debug("terminating")
        tasks = [
            *self.account_consumer.tasks,
            *self.channel_consumer.tasks,
            *self.command_consumer.tasks,
        ]
        self.account_consumer.unsubscribe()
        self.channel_consumer.unsubscribe()
        self.command_consumer.unsubscribe()
        await asyncio.gather(*tasks, return_exceptions=True)
        log.debug("terminated")

    @staticmethod
    async def emit(event):
        await channel_layer.send(input_channel, event)
