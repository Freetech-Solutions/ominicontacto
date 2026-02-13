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
import socket
from smtplib import SMTP

from ..crypter import decrypt
from ._utils import AUTH_BASIC
from ._utils import AUTH_XOAUTH2
from ._utils import PROTOCOL_SMTP
from ._utils import PROTOCOL_SMTP_WITH_SSL
from ._utils import PROTOCOL_SMTP_WITH_TLS

log = logging.getLogger(__name__)
log_smtplib = logging.getLogger("smtplib")

SMTP._print_debug = lambda self, *args: log_smtplib.debug("%s", " ".join(args))


def client(config, **kwargs):
    host = config["host"]
    port = config["port"]
    protocol = config["protocol"]
    if protocol == PROTOCOL_SMTP:
        raise ValueError(f"Unhandled protocol={protocol!r}")
    elif protocol == PROTOCOL_SMTP_WITH_SSL:
        raise ValueError(f"Unhandled protocol={protocol!r}")
    elif protocol == PROTOCOL_SMTP_WITH_TLS:
        timeout = config.get("timeout", kwargs.get("timeout", socket._GLOBAL_DEFAULT_TIMEOUT))
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
