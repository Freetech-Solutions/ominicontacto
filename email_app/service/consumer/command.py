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
import linecache
import logging
import os
import signal
import sys
import threading
import traceback
import aioconsole

from ... import models
from .account import AccountConsumer
from .channel import ChannelConsumer

log = logging.getLogger(__name__)


class CommandConsumer:
    def __init__(
        self,
        account_consumer: AccountConsumer,
        channel_consumer: ChannelConsumer,
        shutdown_requested: asyncio.Event,
    ):
        self.account_consumer = account_consumer
        self.channel_consumer = channel_consumer
        self.shutdown_requested = shutdown_requested
        self.tasks_map: dict[signal.Signals | str, signal.Signals | asyncio.Task] = {}

    @property
    def tasks(self):
        return [item for item in self.tasks_map.values() if isinstance(item, asyncio.Task)]

    def check_result(self, task: asyncio.Task):
        try:
            result = task.result()
            log.debug("check-result task=%r result=%r", task.get_name(), result)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("check-result exception task=%r", task.get_name())

    def receive_signal_sighup(self):
        log.info("received %r ~> requesting reconnect", signal.SIGHUP)

        async def coro():
            tasks = [
                *self.account_consumer.tasks,
                *self.channel_consumer.tasks,
            ]
            self.account_consumer.unsubscribe()
            channels_clears = self.channel_consumer.unsubscribe()
            await asyncio.gather(*tasks, return_exceptions=True)
            async for account in models.Account.objects.filter(active=True):
                self.account_consumer.subscribe(account)
            for channel, clear in channels_clears:
                self.channel_consumer.subscribe(channel, clear)

        asyncio.create_task(coro())

    def receive_signal_sigint(self):
        if sys.stderr.writable():
            sys.stderr.write("\b\b\r")
            sys.stderr.flush()
        log.info("received %r ~> requesting shutdown", signal.SIGINT)
        self.shutdown_requested.set()

    def receive_signal_sigusr1(self):
        log.info("received %r ~> showing stats for running tasks", signal.SIGUSR1)
        print()
        for task in sorted(asyncio.all_tasks(), key=lambda task: task.get_name()):
            for part in task._repr_info():
                print(f"• {part}")
            extracted_list = []
            checked = set()
            for f in task.get_stack():
                lineno = f.f_lineno
                co = f.f_code
                filename = co.co_filename
                name = co.co_name
                if filename not in checked:
                    checked.add(filename)
                    linecache.checkcache(filename)
                line = linecache.getline(filename, lineno, f.f_globals)
                extracted_list.append((filename, lineno, name, line))
            exc = task._exception
            if not extracted_list:
                print("• no stack")
            elif exc is not None:
                print("• traceback (most recent call last):")
            else:
                print("• stack (most recent call last):")
            for item in traceback.StackSummary.from_list(extracted_list).format():
                print(item, end="")
            if exc is not None:
                for line in traceback.format_exception_only(exc.__class__, exc):
                    print(line, end="")
            print(flush=True)

    def subscribe(self, keybind, signals):
        if keybind and sys.stdin.isatty() and "keybind" not in self.tasks_map:
            log.info("subscribe keybind")
            task = asyncio.create_task(self.asubscribe(), name="cmd-keybind")
            task.add_done_callback(self.check_result)
            self.tasks_map["keybind"] = task

        if signals and threading.current_thread() is threading.main_thread():
            loop = asyncio.get_running_loop()
            handlers = {
                signal.SIGHUP: self.receive_signal_sighup,
                signal.SIGINT: self.receive_signal_sigint,
                signal.SIGUSR1: self.receive_signal_sigusr1,
            }
            for sig in (sig for sig in signals if sig.name not in self.tasks_map):
                handler = handlers.get(sig)
                if handler:
                    log.info("subscribe signal=%r", sig.name)
                    loop.add_signal_handler(sig, handler)
                    self.tasks_map[sig.name] = sig
                else:
                    log.info("unknown signal=%r", sig.name)

    def unsubscribe(self):
        loop = asyncio.get_running_loop()
        while self.tasks_map:
            name, item = self.tasks_map.popitem()
            if isinstance(item, asyncio.Task):
                log.info("unsubscribe task=%r", name)
                item.cancel()
            elif isinstance(item, signal.Signals):
                log.info("unsubscribe signal=%r", name)
                loop.remove_signal_handler(item)

    async def asubscribe(self):
        while True:
            try:
                result = await aioconsole.ainput("", use_stderr=True)
                if result == "?":
                    print("c ~> clear screen")
                    print("q ~> request shutdown")
                    print("r ~> request reconnect")
                    print("s ~> show stats for running tasks")
                elif result == "c":
                    os.system("clear")
                elif result == "q":
                    os.kill(os.getpid(), signal.SIGINT)
                elif result == "r":
                    os.kill(os.getpid(), signal.SIGHUP)
                elif result == "s":
                    os.kill(os.getpid(), signal.SIGUSR1)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("check-result exception")
