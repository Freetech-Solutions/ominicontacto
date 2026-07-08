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

import logging
import re
import socket
import ssl

from ..crypter import decrypt
from ..vendor.imaplib import IMAP4
from ..vendor.imaplib import IMAP4_SSL
from ._utils import AUTH_BASIC
from ._utils import AUTH_XOAUTH2
from ._utils import FETCH_IDLE
from ._utils import FETCH_POLL
from ._utils import PROTOCOL_IMAP
from ._utils import PROTOCOL_IMAP_WITH_SSL
from ._utils import PROTOCOL_IMAP_WITH_TLS

log = logging.getLogger(__name__)
log_imaplib = logging.getLogger("imaplib")


def imap4_mesg(self, s, secs=None):
    if " LOGIN " in s:
        s = re.sub(r'(\S+) LOGIN (\S+) "(.+)"', '\\1 LOGIN \\2 "*****"', s, 1)
    log_imaplib.debug(s)


IMAP4._mesg = imap4_mesg


def client(config, **kwargs):
    host = config["host"]
    port = config["port"]
    protocol = config["protocol"]
    if protocol == PROTOCOL_IMAP:
        raise ValueError(f"Unhandled protocol={protocol!r}")
    elif protocol == PROTOCOL_IMAP_WITH_SSL:
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_check_hostname = config.get("ssl_check_hostname")
        if ssl_check_hostname is not None:
            ssl_context.check_hostname = ssl_check_hostname
        timeout = config.get("timeout", kwargs.get("timeout", socket._GLOBAL_DEFAULT_TIMEOUT))
        client = IMAP4_SSL(host, port, ssl_context=ssl_context, timeout=timeout)
        client.debug = 5
    elif protocol == PROTOCOL_IMAP_WITH_TLS:
        raise ValueError(f"Unhandled protocol={protocol!r}")
    else:
        raise ValueError(f"Unknown protocol={protocol!r}")
    return client


def login(client: IMAP4, config):
    auth_type = config["auth_type"]
    if auth_type == AUTH_BASIC:
        username = config["username"]
        password = decrypt(config["password"])
        typ, dat = client.login(username, password)
        log.info("login typ=%r dat=%r", typ, dat)
    elif auth_type == AUTH_XOAUTH2:
        raise ValueError(f"Unhandled auth_type={auth_type!r}")
    else:
        raise ValueError(f"Unknown auth_type={auth_type!r}")


def logout(client: IMAP4):
    typ, dat = client.logout()
    log.info("logout typ=%r dat=%r", typ, dat)


def examine_mailbox(client: IMAP4, config):
    mailbox = config["mailbox"]
    typ, dat = client.select(mailbox, readonly=True)
    if typ == "NO":
        raise Exception(*dat)


def validate_fetch_mode(client: IMAP4, config):
    fetch_mode = config["fetch_mode"]
    if fetch_mode == FETCH_IDLE:
        if "IDLE" not in client.capabilities:
            raise ValueError(f"Unsupported fetch_mode={fetch_mode!r}")
    elif fetch_mode == FETCH_POLL:
        pass  # poll doesnt require any capability from server, so its always valid
    else:
        raise ValueError(f"Unknown fetch_mode={fetch_mode!r}")
