# -*- coding: utf-8 -*-
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
#
from __future__ import unicode_literals

from django.test import SimpleTestCase

from email_app.models.message import Message, parse

RAW_EMAIL = (
    b"From: Rodrigo Montiel <rodrigo.montiel@freetechsolutions.com.ar>\r\n"
    b"To: Soporte <soporte@example.com>\r\n"
    b"Subject: testing envio\r\n"
    b"Message-ID: <abc123@mail.gmail.com>\r\n"
    b"Date: Wed, 25 Jun 2026 14:04:00 -0300\r\n"
    b"Content-Type: text/plain; charset=UTF-8\r\n"
    b"\r\n"
    b"testing envio -- Rodrigo Montiel Ing. en Telecomunicaciones.\r\n"
)


class MessageParseTest(SimpleTestCase):
    """parse() debe aceptar content_bytes como bytearray (recién bajado por
    IMAP), memoryview (leído de un BinaryField vía psycopg2) o bytes, sin
    lanzar AttributeError ('bytearray' object has no attribute 'tobytes')."""

    def _assert_parsed(self, data):
        self.assertEqual(data["subject"], "testing envio")
        self.assertEqual(data["from_mail"], "rodrigo.montiel@freetechsolutions.com.ar")
        self.assertEqual(data["to_mail"], "soporte@example.com")

    def test_parse_accepts_bytearray(self):
        # bytearray es justo el tipo que rompía hydrate() en el servicio de sync.
        data = parse(Message(content_bytes=bytearray(RAW_EMAIL)))
        self._assert_parsed(data)

    def test_parse_accepts_memoryview(self):
        data = parse(Message(content_bytes=memoryview(RAW_EMAIL)))
        self._assert_parsed(data)

    def test_parse_accepts_bytes(self):
        data = parse(Message(content_bytes=RAW_EMAIL))
        self._assert_parsed(data)
