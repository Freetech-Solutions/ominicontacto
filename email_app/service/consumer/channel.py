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
from channels.layers import get_channel_layer
from django.core import serializers

from .account import AccountConsumer

channel_layer = get_channel_layer()


log = logging.getLogger(__name__)


class ChannelConsumer:
    def __init__(self, account_consumer: AccountConsumer):
        self.tasks_map: dict[str, (asyncio.Task, bool)] = {}
        self.account_consumer = account_consumer

    @property
    def tasks(self):
        return [value[0] for value in self.tasks_map.values()]

    def check_result(self, task: asyncio.Task):
        try:
            result = task.result()
            log.debug("check-result task=%r result=%r", task.get_name(), result)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.exception("check-result task=%r exception=%r", task.get_name(), exc)

    def subscribe(self, channel, clear=False):
        if channel not in self.tasks_map:
            log.info("subscribe channel=%r", channel)
            task = asyncio.create_task(self.asubscribe(channel, clear), name=f"chn-{channel}")
            task.add_done_callback(self.check_result)
            self.tasks_map[channel] = (task, clear)

    def unsubscribe(self, channel=None):
        if channel is None:
            channels = []
            while self.tasks_map:
                name, (task, clear) = self.tasks_map.popitem()
                log.info("unsubscribe channel=%r", name)
                task.cancel()
                channels.append((name, clear))
            return channels
        else:
            if channel in self.tasks_map:
                log.info("unsubscribe channel=%r", channel)
                task, clear = self.tasks_map.pop(channel)
                task.cancel()

    async def asubscribe(self, channel, clear):
        if clear and channel_layer.__class__.__name__ == "RedisChannelLayer":
            key = f"{channel_layer.prefix}{channel}"
            actx_manager = channel_layer.connection(channel_layer.consistent_hash(key))
            async with actx_manager as redis:
                await redis.zremrangebyrank(key, 0, -1)
        while True:
            try:
                event = await channel_layer.receive(channel)
                if event.get("model") == "email_app.account":
                    account = next(serializers.deserialize("python", [event])).object
                    acc = account.pk
                    event_type = event.get("type")
                    log.debug("channel received acc=%r type=%r", acc, event_type)
                    if event_type == "signal:post-save":
                        self.account_consumer.unsubscribe(account)
                        if account.active:
                            self.account_consumer.subscribe(account)
                    elif event_type == "unsubscribe":
                        self.account_consumer.unsubscribe(account)
                    elif event_type == "subscribe":
                        self.account_consumer.subscribe(account)
                    else:
                        log.warning("channel unhandled acc=%r type=%r", acc, event_type)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("exception=%r", exc)
