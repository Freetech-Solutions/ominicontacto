# -*- coding: utf-8 -*-
# Copyright (C) 2025 Freetech Solutions

# This file is part of OMniLeads

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.

import asyncio
import functools
import json
import logging
import logging.config
import signal
import sys
import time
import typing
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.management import BaseCommand
from django.db import models

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from ominicontacto_app.services.redis.ha_lock import node_id, run_once
from orquestador_app.core.facebook.message_handler import (
    facebook_messenger_handler_messages)
from orquestador_app.core.instagram.message_handler import instagram_handler_messages
from orquestador_app.core.whatsapp.message_handler import (
    handle_gupshup_message,
    handle_meta_messages,
)
from instagram_app.models import CuentaInstagram as InstagramAccount
from instagram_app.services.redis.account import StreamDeCuentasInstagram
from facebook_meta_app.services.redis.page import StreamDePaginas
from whatsapp_app.models import ConfiguracionProveedor as ProviderConfig
from whatsapp_app.models import Linea as Line
from whatsapp_app.services.redis.linea import StreamDeLineas
from facebook_meta_app.models import PaginaMetaFacebook as Page

logger = logging.getLogger(__name__)

MSGS_ORCHESTRATOR_GROUP = 'msgs-orchestrator'
MSGS_ORCHESTRATOR_AUTOCLAIM_IDLE_MS = 60 * 1000
MSGS_ORCHESTRATOR_AUTOCLAIM_INTERVAL_SEC = 30
MSGS_ORCHESTRATOR_AUTOCLAIM_COUNT = 10
MSGS_ORCHESTRATOR_CONTROL_CHANNEL = 'OML:CHANNEL:MSGS_ORCHESTRATOR_CONTROL'


def slave_group_name(channel, pk):
    """One consumer group per (channel, entity) so shared streams cannot cross-deliver."""
    return '{0}:{1}:{2}'.format(MSGS_ORCHESTRATOR_GROUP, channel, pk)


def slave_consumer_name(channel, pk):
    return '{0}:{1}:{2}'.format(node_id(), channel, pk)


class EventsProcessor(object):

    def __init__(self):
        self.master_jobs = []
        self.redis_client = None
        self.shutdown = asyncio.Event()
        self.slave_tasks = {}
        self.consumer_name = node_id()
        self._control_pubsub = None

    async def __aenter__(self):
        while not self.shutdown.is_set():
            try:
                self.redis_client = Redis(host=settings.REDIS_HOSTNAME, decode_responses=True)
                await self.redis_client.ping()
                logger.info("connect-to-redis %r", self.redis_client)
                break
            except Exception as exception:
                logger.exception("connect-to-redis %r", exception)
                await asyncio.sleep(1)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, functools.partial(self.loop_signal_handler, sig))
        await self._regenerate_master_streams()
        self.master_jobs.append(
            asyncio.create_task(
                self._listen_control_channel(),
                name="msgs-orchestrator-control (pubsub)",
            ))
        self.master_jobs.append(
            asyncio.create_task(
                self.read_stream(
                    "whatsapp_enabled_lines", self.handle_master_stream_message_whatsapp),
                name="whatsapp_enabled_lines (suscriber)",
            ))
        self.master_jobs.append(
            asyncio.create_task(
                self.read_stream(
                    "facebook_enabled_pages", self.handle_master_stream_message_page),
                name="facebook_enabled_pages (suscriber)",
            ))
        self.master_jobs.append(
            asyncio.create_task(
                self.read_stream(
                    "instagram_enabled_accounts", self.handle_master_stream_message_instagram),
                name="instagram_enabled_accounts (suscriber)",
            ))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.shutdown.set()
        tasks = []
        tasks.extend(self.master_jobs)
        tasks.extend(self.slave_tasks.values())
        for task in tasks:
            task.cancel()
            logger.info("task -> cancel")
            for info in task._repr_info()[1:]:
                logger.info("task    %s", info)
        if self._control_pubsub is not None:
            try:
                await self._control_pubsub.unsubscribe(
                    MSGS_ORCHESTRATOR_CONTROL_CHANNEL)
                await self._control_pubsub.aclose()
            except Exception:
                pass
        if self.redis_client:
            tasks.append(self.redis_client.aclose())
        await asyncio.gather(*tasks, return_exceptions=True)

    def loop_signal_handler(self, sig: signal.Signals):
        if sig == signal.SIGINT and sys.stderr.writable():
            sys.stderr.write("\b\b\r")
            sys.stderr.flush()
        logger.info("loop-signal-handler %r", sig)
        self.shutdown.set()

    async def _listen_control_channel(self):
        """Fan-out stop/control signals to every HA replica via Pub/Sub."""
        self._control_pubsub = self.redis_client.pubsub()
        await self._control_pubsub.subscribe(MSGS_ORCHESTRATOR_CONTROL_CHANNEL)
        logger.info(
            "msgs-orchestrator control subscribed channel=%s",
            MSGS_ORCHESTRATOR_CONTROL_CHANNEL,
        )
        try:
            while not self.shutdown.is_set():
                message = await self._control_pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    await asyncio.sleep(0.05)
                    continue
                data = message.get('data')
                if data in ('stop', b'stop') or (
                        isinstance(data, str) and 'stop' in data):
                    logger.info("msgs-orchestrator control stop received")
                    self.shutdown.set()
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("msgs-orchestrator control listener failed")

    async def _broadcast_stop(self):
        try:
            await self.redis_client.publish(
                MSGS_ORCHESTRATOR_CONTROL_CHANNEL, 'stop')
        except Exception:
            logger.exception("msgs-orchestrator control publish failed")
        self.shutdown.set()

    @staticmethod
    def _is_nogroup_error(exception):
        return 'NOGROUP' in str(exception)

    async def _ensure_consumer_group(self, stream_name: str, group_name: str):
        try:
            await self.redis_client.xgroup_create(
                stream_name,
                group_name,
                id='$',
                mkstream=True,
            )
            logger.info(
                "redis-stream-group-created stream=%r group=%r",
                stream_name, group_name,
            )
        except ResponseError as exception:
            if 'BUSYGROUP' not in str(exception):
                raise

    async def _deliver_and_ack(
            self, callback, event, stream_name, group_name, msgid):
        await callback(event)
        await self.redis_client.xack(stream_name, group_name, msgid)

    async def _drain_own_pending(
            self, stream_name: str, callback: typing.Callable,
            group_name: str, consumer_name: str):
        """Re-deliver this consumer's PEL (e.g. after task cancel mid-callback)."""
        while not self.shutdown.is_set():
            try:
                response = await self.redis_client.xreadgroup(
                    groupname=group_name,
                    consumername=consumer_name,
                    streams={stream_name: '0'},
                    count=MSGS_ORCHESTRATOR_AUTOCLAIM_COUNT,
                    block=None,
                )
            except ResponseError as exception:
                if self._is_nogroup_error(exception):
                    logger.warning(
                        "redis-stream drain-pending NOGROUP stream=%r "
                        "group=%r; recreating",
                        stream_name, group_name,
                    )
                    await self._ensure_consumer_group(stream_name, group_name)
                    return
                logger.info(
                    "redis-stream drain-pending skipped stream=%r err=%r",
                    stream_name, exception,
                )
                return
            if not response:
                return
            delivered = 0
            for _stream, messages in response:
                if not messages:
                    continue
                for msgid, event in messages:
                    delivered += 1
                    try:
                        await asyncio.shield(self._deliver_and_ack(
                            callback, event, stream_name, group_name, msgid))
                    except Exception:
                        logger.exception(
                            "redis-stream drain-pending handler failed "
                            "stream=%r id=%r",
                            stream_name, msgid,
                        )
            if delivered == 0:
                return

    async def _autoclaim_pending(
            self, stream_name: str, callback: typing.Callable,
            group_name: str, consumer_name: str):
        """Claim idle PEL entries; paginate until the cursor is exhausted."""
        start_id = '0-0'
        while not self.shutdown.is_set():
            try:
                result = await self.redis_client.xautoclaim(
                    name=stream_name,
                    groupname=group_name,
                    consumername=consumer_name,
                    min_idle_time=MSGS_ORCHESTRATOR_AUTOCLAIM_IDLE_MS,
                    start_id=start_id,
                    count=MSGS_ORCHESTRATOR_AUTOCLAIM_COUNT,
                )
            except ResponseError as exception:
                if self._is_nogroup_error(exception):
                    logger.warning(
                        "redis-stream-autoclaim NOGROUP stream=%r group=%r; "
                        "recreating",
                        stream_name, group_name,
                    )
                    await self._ensure_consumer_group(stream_name, group_name)
                    return
                # Stream/group still empty or Redis too old for XAUTOCLAIM.
                logger.info(
                    "redis-stream-autoclaim skipped stream=%r err=%r",
                    stream_name, exception,
                )
                return
            next_id = '0-0'
            messages = []
            if isinstance(result, (list, tuple)):
                if len(result) >= 1:
                    next_id = result[0] or '0-0'
                if len(result) >= 2 and isinstance(result[1], list):
                    messages = result[1]
            for msgid, event in messages:
                try:
                    await asyncio.shield(self._deliver_and_ack(
                        callback, event, stream_name, group_name, msgid))
                except Exception:
                    logger.exception(
                        "redis-stream-autoclaim handler failed stream=%r id=%r",
                        stream_name, msgid,
                    )
            if not messages:
                return
            if len(messages) < MSGS_ORCHESTRATOR_AUTOCLAIM_COUNT:
                return
            if next_id in ('0-0', 0, b'0-0'):
                return
            start_id = next_id

    async def read_stream(
            self, name: str, callback: typing.Callable, fromid="0-0",
            use_group=False, group_name=None, consumer_name=None):
        group_name = group_name or MSGS_ORCHESTRATOR_GROUP
        consumer_name = consumer_name or self.consumer_name
        logger.info(
            "redis-stream-reader %r start use_group=%s group=%s consumer=%s",
            name, use_group, group_name, consumer_name,
        )
        if use_group:
            await self._ensure_consumer_group(name, group_name)
            await self._drain_own_pending(
                name, callback, group_name, consumer_name)
            await self._autoclaim_pending(
                name, callback, group_name, consumer_name)
            last_autoclaim = time.monotonic()
            while not self.shutdown.is_set():
                try:
                    now = time.monotonic()
                    if (
                        now - last_autoclaim
                        >= MSGS_ORCHESTRATOR_AUTOCLAIM_INTERVAL_SEC
                    ):
                        await self._autoclaim_pending(
                            name, callback, group_name, consumer_name)
                        last_autoclaim = now
                    response = await self.redis_client.xreadgroup(
                        groupname=group_name,
                        consumername=consumer_name,
                        streams={name: '>'},
                        count=1,
                        block=1000 * 2,
                    )
                    if not response:
                        continue
                    for _stream, messages in response:
                        for msgid, event in messages:
                            try:
                                await asyncio.shield(self._deliver_and_ack(
                                    callback, event, name, group_name, msgid))
                            except Exception:
                                logger.exception(
                                    "redis-stream-group handler failed "
                                    "stream=%r id=%r",
                                    name, msgid,
                                )
                except asyncio.CancelledError:
                    logger.info("redis-stream-reader %r cancelled", name)
                    break
                except ResponseError as exception:
                    if self._is_nogroup_error(exception):
                        logger.warning(
                            "redis-stream-reader %r NOGROUP group=%r; recreating",
                            name, group_name,
                        )
                        try:
                            await self._ensure_consumer_group(name, group_name)
                        except Exception:
                            logger.exception(
                                "redis-stream-reader %r failed recreating group",
                                name,
                            )
                            await asyncio.sleep(1)
                        continue
                    logger.exception("redis-stream-reader %r %r", name, exception)
                    await asyncio.sleep(1)
                except Exception as exception:
                    logger.exception("redis-stream-reader %r %r", name, exception)
                    await asyncio.sleep(1)
            return

        streams = {
            name: fromid
        }
        while not self.shutdown.is_set():
            try:
                response = await self.redis_client.xread(streams, block=1000 * 2, count=1)
                if response:
                    for msgid, event in response[0][1]:
                        await callback(event)
                    streams[name] = msgid
            except asyncio.TimeoutError:
                logger.info("redis-stream-reader %r timeout", name)
            except asyncio.CancelledError:
                logger.info("redis-stream-reader %r cancelled", name)
                break
            except Exception as exception:
                logger.exception("redis-stream-reader %r %r", name, exception)
                await asyncio.sleep(1)

    async def _stop_slave_task(self, task_key):
        task = self.slave_tasks.pop(task_key, None)
        if task is None:
            return
        task.cancel()
        logger.info("task -> cancel %r", task_key)
        await asyncio.gather(task, return_exceptions=True)

    async def _ensure_slave_task(self, task_key, is_active, start_factory, task_name):
        """
        Start a slave reader once. If already running, leave it alone so a
        master-stream regenerate on another node does not cancel mid-callback.
        """
        existing = self.slave_tasks.get(task_key)
        if not is_active:
            if existing is not None:
                await self._stop_slave_task(task_key)
            return
        if existing is not None and not existing.done():
            logger.info("slave task already running %r", task_key)
            return
        if existing is not None:
            self.slave_tasks.pop(task_key, None)
        self.slave_tasks[task_key] = asyncio.create_task(
            start_factory(), name=task_name)

    async def handle_master_stream_message_whatsapp(self, message: dict):
        line_id = message.get("value")
        try:
            line = await self._get_line(line_id)
            task_key = ("whatsapp", line.pk)
            stream = line.get_stream_name

            async def start():
                return await self.read_stream(
                    stream,
                    functools.partial(self.handle_slave_streams_message_whatsapp, line),
                    fromid=settings.ORCHESTRATOR_SLAVE_STREAM_FROMID,
                    use_group=True,
                    group_name=slave_group_name('whatsapp', line.pk),
                    consumer_name=slave_consumer_name('whatsapp', line.pk),
                )

            await self._ensure_slave_task(
                task_key, line.is_active, start, f"{stream} (suscriber)")
        except (Line.DoesNotExist, Line.MultipleObjectsReturned) as exception:
            logger.error("process-main-stream-message %r %r", line_id, exception)
        else:
            logger.info("process-main-stream-message %r", line_id)

    async def handle_master_stream_message_page(self, message: dict):
        page_id = message.get("value")
        try:
            page = await self._get_page(page_id)
            task_key = ("facebook", page.pk)
            stream = page.get_stream_name

            async def start():
                return await self.read_stream(
                    stream,
                    functools.partial(self.handle_slave_streams_message_page, page),
                    fromid=settings.ORCHESTRATOR_SLAVE_STREAM_FROMID,
                    use_group=True,
                    group_name=slave_group_name('facebook', page.pk),
                    consumer_name=slave_consumer_name('facebook', page.pk),
                )

            await self._ensure_slave_task(
                task_key, page.is_active, start, f"{stream} (suscriber)")
        except (Page.DoesNotExist, Page.MultipleObjectsReturned) as exception:
            logger.error("process-main-stream-message %r %r", page_id, exception)
        else:
            logger.info("process-main-stream-message %r", page_id)

    async def handle_master_stream_message_instagram(self, message: dict):
        account_id = message.get("value")
        try:
            account = await self._get_instagram_account(account_id)
            task_key = ("instagram", account.pk)
            stream = account.get_stream_name

            async def start():
                return await self.read_stream(
                    stream,
                    functools.partial(
                        self.handle_slave_streams_message_instagram, account),
                    fromid=settings.ORCHESTRATOR_SLAVE_STREAM_FROMID,
                    use_group=True,
                    group_name=slave_group_name('instagram', account.pk),
                    consumer_name=slave_consumer_name('instagram', account.pk),
                )

            await self._ensure_slave_task(
                task_key, account.is_active, start, f"{stream} (suscriber)")
        except (
            InstagramAccount.DoesNotExist,
            InstagramAccount.MultipleObjectsReturned,
        ) as exception:
            logger.error("process-main-stream-message-instagram %r %r", account_id, exception)
        else:
            logger.info("process-main-stream-message-instagram %r", account_id)

    async def handle_slave_streams_message_whatsapp(self, line: Line, event: dict):
        try:
            if event.get("action") == "stop":
                await self._broadcast_stop()
                return
            payload = json.loads(event.get("value"))
            if line.provider_type == ProviderConfig.TIPO_GUPSHUP:
                await handle_gupshup_message(line, payload)
            elif line.provider_type == ProviderConfig.TIPO_META:
                await handle_meta_messages(line, payload)
        except Exception as exception:
            logger.error("handle_slave_streams_message %r %r", line.id, exception)
            logger.error("Event: %r", event)
            raise

    async def handle_slave_streams_message_page(self, page: Page, event: dict):
        try:
            if event.get("action") == "stop":
                await self._broadcast_stop()
                return
            print("Received event for page:", page.id)
            print("Event data:", event)
            payload = json.loads(event.get("value"))
            print("Payload data:", payload)
            await facebook_messenger_handler_messages(page, payload)
        except Exception as exception:
            logger.error("handle_slave_streams_message_page %r %r", page.id, exception)
            logger.error("Event: %r", event)
            raise

    async def handle_slave_streams_message_instagram(
            self, account: InstagramAccount, event: dict):
        try:
            if event.get("action") == "stop":
                await self._broadcast_stop()
                return
            payload = json.loads(event.get("value"))
            await instagram_handler_messages(account, payload)
        except Exception as exception:
            logger.error(
                "handle_slave_streams_message_instagram %r %r", account.id, exception)
            logger.error("Event: %r", event)
            raise

    @database_sync_to_async
    def _get_line(self, pk):
        queryset = (
            Line.objects_default.only(
                "pk",
                "is_active",
                "nombre",
                "numero",
                "configuracion",
                "proveedor",
            ).annotate(
                provider_type=models.F("proveedor__tipo_proveedor"),
            ).select_related(
                "proveedor",
            ).prefetch_related(
                "horario__validaciones_tiempo",
            )
        )
        return queryset.get(pk=pk)

    @database_sync_to_async
    def _get_page(self, pk):
        queryset = (
            Page.objects_default.only(
                "pk",
                "is_active",
                "page_id",
                "app_id",
                "name",
            ).prefetch_related(
                "horario__validaciones_tiempo",
            )
        )
        return queryset.get(pk=pk)

    @database_sync_to_async
    def _get_instagram_account(self, pk):
        queryset = (
            InstagramAccount.objects_default.only(
                "pk",
                "is_active",
                "ig_user_id",
                "app_id",
                "name",
                "destination",
                "horario",
            ).select_related(
                "destination",
                "horario",
            ).prefetch_related(
                "horario__validaciones_tiempo",
            )
        )
        return queryset.get(pk=pk)

    @database_sync_to_async
    def _regenerate_master_streams(self):
        regenerators = (
            ("whatsapp", StreamDeLineas().regenerar_stream),
            ("facebook", StreamDePaginas().regenerar_stream),
            ("instagram", StreamDeCuentasInstagram().regenerar_stream),
        )
        for channel, regenerate_stream in regenerators:
            try:
                # Cluster-wide: only one node seeds an empty master stream.
                seeded = run_once(
                    'msgs-orch-regen',
                    channel,
                    ttl=120,
                    fn=regenerate_stream,
                )
                logger.info(
                    "regenerate-master-stream %r done seeded=%s",
                    channel, seeded,
                )
            except Exception as exception:
                logger.exception("regenerate-master-stream %r %r", channel, exception)


class Command(BaseCommand):

    def handle(self, *args, **options):
        logging.config.dictConfig({
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "msg-formatter": {
                    "format": "%(levelname).3s | %(name)s (%(threadName)s) %(message)s"
                },
            },
            "handlers": {
                "msg-handler": {
                    "class": "logging.StreamHandler",
                    "formatter": "msg-formatter",
                },
            },
            "loggers": {
                "orquestador_app": {
                    "handlers": ["msg-handler"],
                    "level": "DEBUG" if options["verbosity"] > 1 else "INFO",
                    "propagate": False,
                },
            },
        })
        asyncio.run(self.ahandle(), debug=False)

    async def ahandle(self):
        async with EventsProcessor() as processor:
            await processor.shutdown.wait()
