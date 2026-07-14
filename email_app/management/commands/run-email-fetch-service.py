# Copyright (C) 2026 Freetech Solutions

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
import contextlib
import logging
import logging.config
import os
import aiomonitor
from django.core.management import BaseCommand
from django.utils import autoreload

from ...service.email.fetch import EmailFetchService

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--with-aiodebug", action="store_true")
        parser.add_argument("--with-aiomonitor", action="store_true")
        parser.add_argument("--with-autoreload", action="store_true")
        parser.add_argument("--loggers")

    def config_logging(self, loggers):
        FSFILE = {"handlers": ["fsfile"], "level": "INFO", "propagate": False}
        STDERR = {"handlers": ["stderr"], "level": "INFO", "propagate": False}
        logging.config.dictConfig(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {"format": "%(levelname).3s | %(name)s:%(lineno)s => %(message)s"},
                },
                "handlers": {
                    "fsfile": {
                        "class": "logging.handlers.TimedRotatingFileHandler",
                        "filename": "/tmp/efs-protocol.log",
                        "when": "midnight",
                        "backupCount": 7,
                        "encoding": "utf-8",
                        "formatter": "default",
                    },
                    "stderr": {"class": "logging.StreamHandler", "formatter": "default"},
                },
                "loggers": {
                    "aioimaplib": FSFILE,
                    "asyncio": STDERR,
                    "email_app": STDERR,
                    "imaplib": FSFILE,
                    "mailparser": STDERR,
                    "smtplib": FSFILE,
                },
            }
        )
        if loggers:
            for logger in loggers.split(";"):
                level, names = logger.split(":", 1)
                for name in names.split(","):
                    logging.getLogger(name).setLevel(level)

    def handle(self, *args, **options):
        self.config_logging(options["loggers"])
        coro = self.ahandle(options["with_aiomonitor"])
        debug = options["with_aiodebug"]
        if options["with_autoreload"]:
            autoreload.run_with_reloader(asyncio.run, coro, debug=debug)
        else:
            asyncio.run(coro, debug=debug)

    async def ahandle(self, with_aiomonitor):
        log.info("start pid=%r", os.getpid())
        if with_aiomonitor:
            monitor = aiomonitor.start_monitor(asyncio.get_running_loop(), hook_task_factory=True)
        else:
            monitor = contextlib.nullcontext()
        email_fetch_service = EmailFetchService()
        with monitor:
            async with email_fetch_service:
                await email_fetch_service.shutdown_requested.wait()
