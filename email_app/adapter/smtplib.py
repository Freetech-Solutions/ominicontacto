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
import ssl
from smtplib import SMTP
from smtplib import SMTP_SSL

from ..crypter import decrypt
from ._utils import AUTH_BASIC
from ._utils import AUTH_XOAUTH2
from ._utils import PROTOCOL_SMTP
from ._utils import PROTOCOL_SMTP_WITH_SSL
from ._utils import PROTOCOL_SMTP_WITH_TLS

log = logging.getLogger(__name__)
log_smtplib = logging.getLogger("smtplib")

# NOTE: smtplib calls _print_debug with non-string args too (e.g. the DATA
# phase does `_print_debug('data:', (code, repl))` and connect passes a
# `(host, port)` tuple), so each arg MUST be stringified — a plain
# `" ".join(args)` raises TypeError mid-send and aborts delivery.
SMTP._print_debug = lambda self, *args: log_smtplib.debug(
    "%s", " ".join(str(arg) for arg in args))

# Never block a worker indefinitely on a stalled SMTP dialog (connect / STARTTLS
# / AUTH / DATA). The socket timeout applies to every blocking operation, so a
# hung relay fails fast with a clear error instead of pinning the worker until
# the upstream gateway (nginx) times out. Critical for stability under load.
DEFAULT_SMTP_TIMEOUT = 20  # seconds


def client(config, **kwargs):
    host = config["host"]
    port = config["port"]
    protocol = config["protocol"]
    if protocol == PROTOCOL_SMTP:
        raise ValueError(f"Unhandled protocol={protocol!r}")
    elif protocol == PROTOCOL_SMTP_WITH_SSL:
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_check_hostname = config.get("ssl_check_hostname")
        if ssl_check_hostname is not None:
            ssl_context.check_hostname = ssl_check_hostname
        timeout = config.get("timeout", kwargs.get("timeout", DEFAULT_SMTP_TIMEOUT))
        client = SMTP_SSL(host, port, context=ssl_context, timeout=timeout)
        client.set_debuglevel(1)
    elif protocol == PROTOCOL_SMTP_WITH_TLS:
        timeout = config.get("timeout", kwargs.get("timeout", DEFAULT_SMTP_TIMEOUT))
        client = SMTP(host, port, timeout=timeout)
        client.set_debuglevel(1)
        client.starttls()
    else:
        raise ValueError(f"Unknown protocol={protocol!r}")
    return client


def login(client: SMTP, config):
    auth_type = config["auth_type"]
    if auth_type == AUTH_BASIC:
        username = config["username"]
        password = decrypt(config["password"])
        client.login(username, password)
    elif auth_type == AUTH_XOAUTH2:
        raise ValueError(f"Unhandled auth_type={auth_type!r}")
    else:
        raise ValueError(f"Unknown auth_type={auth_type!r}")


def verify(client: SMTP, config):
    client.verify(config["from_addr"])


def send(client: SMTP, config, message):
    """Send an already-built email.message.EmailMessage through the connected
    (and authenticated) SMTP client."""
    client.send_message(message)
