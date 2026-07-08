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
import re
import ssl
from datetime import datetime
from hashlib import sha256
from itertools import islice
from babel.dates import format_date

from .. import models
from ..crypter import decrypt
from ..vendor.aioimaplib import IMAP4
from ..vendor.aioimaplib import IMAP4_SSL
from ..vendor.aioimaplib import STOP_WAIT_SERVER_PUSH
from ._utils import AUTH_BASIC
from ._utils import AUTH_XOAUTH2
from ._utils import PROTOCOL_IMAP
from ._utils import PROTOCOL_IMAP_WITH_SSL
from ._utils import PROTOCOL_IMAP_WITH_TLS

log = logging.getLogger(__name__)


CHUNKS_SIZE = 25
TIMEOUT = IMAP4.TIMEOUT_SECONDS


try:
    from itertools import batched
except ImportError:
    def batched(iterable, size=CHUNKS_SIZE):
        return iter(lambda: tuple(islice(iterable, size)), tuple())


async def client(account: "models.Account", **kwargs) -> IMAP4:
    host = account.settings["inbound"]["host"]
    port = account.settings["inbound"]["port"]
    protocol = account.settings["inbound"]["protocol"]
    if protocol == PROTOCOL_IMAP:
        raise ValueError(f"Unhandled protocol={protocol!r}")
    elif protocol == PROTOCOL_IMAP_WITH_SSL:
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_check_hostname = account.settings["inbound"].get("ssl_check_hostname")
        if ssl_check_hostname is not None:
            ssl_context.check_hostname = ssl_check_hostname
        timeout = account.settings["inbound"].get("timeout", kwargs.get("timeout", TIMEOUT))
        client = IMAP4_SSL(host, port, ssl_context=ssl_context, timeout=timeout)
        await client.wait_hello_from_server()
    elif protocol == PROTOCOL_IMAP_WITH_TLS:
        raise ValueError(f"Unhandled protocol={protocol!r}")
    else:
        raise ValueError(f"Unknown protocol={protocol!r}")
    return client


async def examine_mailbox(client: IMAP4, account: "models.Account"):
    acc = account.pk
    mailbox = account.settings["inbound"]["mailbox"]
    response = await client.examine(mailbox)
    if response.result != "OK":
        raise Exception([line.decode() for line in response.lines])
    UIDVALIDITY = re.compile(rb"OK \[UIDVALIDITY (?P<uidvalidity>\d+)\]")
    UIDNEXT = re.compile(rb"OK \[UIDNEXT (?P<uidnext>\d+)\]")
    uidvalidity = None
    uidnext = None
    for line in response.lines:
        if (uidvalidity is None) and (match := UIDVALIDITY.match(line)):
            uidvalidity = int(match.group("uidvalidity"))
        if (uidnext is None) and (match := UIDNEXT.match(line)):
            uidnext = int(match.group("uidnext"))
    log.debug("examine acc=%r mbox=%r next=%r validity=%r", acc, mailbox, uidnext, uidvalidity)
    return {
        "mailbox": mailbox,
        "uidnext": uidnext,
        "uidvalidity": uidvalidity,
    }


async def fetch(client: IMAP4, uids: list[int]):
    response = await client.uid("FETCH", f"{uids[0]}:{uids[-1]}", "(UID BODY.PEEK[])")
    if response.result != "OK":
        raise Exception([line.decode() for line in response.lines])
    if len(response.lines) > 2:
        FETCH_UID = re.compile(rb"\d+ FETCH \(UID (?P<uid>\d+) .+")
        response_lines = iter(response.lines[:-1])
        for head, content_bytes, _ in iter(lambda: tuple(islice(response_lines, 3)), tuple()):
            uid = int(FETCH_UID.match(head).group("uid"))
            content_stamp = sha256(content_bytes).hexdigest()
            yield (uid, content_bytes, content_stamp)


async def get_uids_in(client: IMAP4, imap_sequence_set: str, chunks_size=CHUNKS_SIZE):
    """Response(result='OK', lines=[b'1 2 3', b'SEARCH completed (took 2 ms)'])"""
    response = await client.uid_search("UID", imap_sequence_set)
    if response.result != "OK":
        raise Exception([line.decode() for line in response.lines])
    if len(response.lines) > 1:
        return batched((int(uid) for uid in response.lines[0].decode().split()), chunks_size)
    return ()


async def get_uids_since(client: IMAP4, iso8601date: str, chunks_size=CHUNKS_SIZE):
    """Response(result='OK', lines=[b'1 2 3', b'SEARCH completed (took 2 ms)'])"""
    rfc3501date = format_date(datetime.fromisoformat(iso8601date), "dd-MMM-yyyy", locale="en")
    response = await client.uid_search("SINCE", rfc3501date)
    if response.result != "OK":
        raise Exception([line.decode() for line in response.lines])
    if len(response.lines) > 1:
        return batched((int(uid) for uid in response.lines[0].decode().split()), chunks_size)
    return ()


async def idle_cooldown(client: IMAP4, account: "models.Account"):
    EXISTS = re.compile(rb"(?P<exists>\d+) EXISTS")
    acc = account.pk
    duration = account.settings["inbound"]["idle_duration"]
    while True:
        log.debug("fetch-cooldown-idle acc=%r duration=%r", acc, duration)
        task = await client.idle_start(duration)
        try:
            while client.has_pending_idle():
                try:
                    lines = await client.wait_server_push()
                except asyncio.TimeoutError:
                    log.exception("idle-cooldown")
                    break
                if lines == STOP_WAIT_SERVER_PUSH:
                    break
                for line in lines:
                    if match := EXISTS.match(line):
                        return {k: int(v) for k, v in match.groupdict().items()}
        finally:
            client.idle_done()
            await asyncio.wait_for(task, 1)


async def login(client: IMAP4, account: "models.Account"):
    auth_type = account.settings["inbound"]["auth_type"]
    if auth_type == AUTH_BASIC:
        username = account.settings["inbound"]["username"]
        password = decrypt(account.settings["inbound"]["password"], raise_exception=True)
        response = await client.login(username, password)
        if response.result != "OK":
            raise Exception([line.decode() for line in response.lines])
    elif auth_type == AUTH_XOAUTH2:
        raise ValueError(f"Unhandled auth_type={auth_type!r}")
    else:
        raise ValueError(f"Unknown auth_type={auth_type!r}")


async def logout(client: IMAP4):
    await client.logout()
