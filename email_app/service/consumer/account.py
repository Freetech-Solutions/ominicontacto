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

from ... import models
from ...adapter import aioimaplib
from ..inbound import aingest_inbound_message
from ..notify import notify_new_email_conversation

log = logging.getLogger(__name__)


class AccountConsumer:
    def __init__(self):
        self.tasks_map: dict[int, asyncio.Task] = {}

    @property
    def tasks(self):
        return self.tasks_map.values()

    def check_result(self, task: asyncio.Task):
        try:
            result = task.result()
            log.debug("check-result task=%r result=%r", task.get_name(), result)
        except asyncio.CancelledError:
            pass
        # except asyncio.TimeoutError: pass
        except Exception as exc:
            log.exception("check-result task=%r exception=%r", task.get_name(), exc)

    def subscribe(self, account: "models.Account"):
        acc = account.pk
        if acc not in self.tasks_map:
            log.info("subscribe acc=%r", acc)
            task = asyncio.create_task(self.asubscribe(account), name=f"acc-{acc}")
            task.add_done_callback(self.check_result)
            self.tasks_map[acc] = task

    def unsubscribe(self, account=None):
        if account is None:
            while self.tasks_map:
                name, task = self.tasks_map.popitem()
                log.info("unsubscribe acc=%r", name)
                task.cancel()
        else:
            acc = account.pk
            if acc in self.tasks_map:
                log.info("unsubscribe acc=%r", acc)
                task = self.tasks_map.pop(acc)
                task.cancel()

    async def asubscribe(self, account: "models.Account"):
        client = await aioimaplib.client(account)
        await aioimaplib.login(client, account)
        try:
            while True:
                await self.fetch(client, account)
                await self.fetch_cooldown(client, account)
        except asyncio.CancelledError:
            await aioimaplib.logout(client)
            raise

    async def fetch(self, client: aioimaplib.IMAP4, account: "models.Account"):
        account.insights.setdefault("mailbox", account.settings["inbound"]["mailbox"])
        account.insights.setdefault("uidnext", 1)
        account.insights.setdefault("uidvalidity", 0)

        acc = account.pk
        local = account.insights
        cloud = await aioimaplib.examine_mailbox(client, account)

        log.debug("fetch-check acc=%r cloud=%r local=%r", acc, cloud, local)

        if cloud["mailbox"] != local["mailbox"] or cloud["uidvalidity"] != local["uidvalidity"]:
            if since := account.settings["inbound"].get("since"):
                uid_chunks = await get_uids_since("fetch-full", client, acc, since)
            else:
                sset = "1:*"
                uid_chunks = await get_uids_in("fetch-full", client, acc, sset)
        else:
            if cloud["uidnext"] > local["uidnext"]:
                sset = f"{local['uidnext']}:*"
                uid_chunks = await get_uids_in("fetch-incr", client, acc, sset)
            else:
                uid_chunks = await get_uids_noop("fetch-incr", acc, tuple())

        uidvalidity = cloud["uidvalidity"]
        for uids in uid_chunks:
            log.debug("fetch-chunk acc=%r uids=%r", acc, uids)
            async for uid, content_bytes, content_stamp in aioimaplib.fetch(client, uids):
                message, created = await models.Message.objects.aget_or_create(
                    content_stamp=content_stamp,
                    defaults={
                        "account": account,
                        "content_bytes": content_bytes,
                        "mailbox_uidva": f"{uidvalidity}:{uid}",
                    },
                )
                if created:
                    # @todo move this to the task/consumer message handler
                    message.hydrate()
                    # agent-channel: group into a conversation and notify agents.
                    # Best-effort: a failure here must not break message ingestion.
                    try:
                        conversation, conv_created = await aingest_inbound_message(message)
                        await notify_new_email_conversation(conversation, conv_created, message)
                    except Exception as exc:
                        log.exception("email-ingest acc=%r exception=%r", acc, exc)
            local["mailbox"] = cloud["mailbox"]
            local["uidnext"] = max(uids) + 1
            local["uidvalidity"] = uidvalidity
            await models.Account.objects.filter(pk=acc).aupdate(insights=local)

    async def fetch_cooldown(self, client: aioimaplib.IMAP4, account: "models.Account"):
        acc = account.pk
        fetch_mode = account.settings["inbound"]["fetch_mode"]
        if fetch_mode == "idle":
            log.debug("fetch-cooldown acc=%r mode=idle", acc)
            await aioimaplib.idle_cooldown(client, account)
        elif fetch_mode == "poll":
            interval = account.settings["inbound"]["poll_interval"]
            log.debug("fetch-cooldown acc=%r mode=poll interval=%r", acc, interval)
            await asyncio.sleep(interval)
        else:
            raise ValueError(f"fetch-cooldown: unknown fetch_mode={fetch_mode!r}")


async def get_uids_in(head, client, acc, sset):
    uids = tuple(await aioimaplib.get_uids_in(client, sset))
    log.debug("%s acc=%r sset=%r uids=%r", head, acc, sset, len(uids))
    return uids


async def get_uids_noop(head, acc, uids):
    log.debug("%s acc=%r uids=%r", head, acc, len(uids))
    return uids


async def get_uids_since(head, client, acc, since):
    uids = tuple(await aioimaplib.get_uids_since(client, since))
    log.debug("%s acc=%r since=%r uids=%r", head, acc, since, len(uids))
    return uids
