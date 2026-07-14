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

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from email_app import models
from ominicontacto_app.models import User
from ominicontacto_app.tests.factories import CampanaFactory
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class CampaignEmailReportTest(OMLBaseTest):
    """Supervisor-facing 'Reportes Email' / 'Conversaciones Email' endpoints."""

    def setUp(self):
        super(CampaignEmailReportTest, self).setUp()
        self.admin = self.crear_supervisor_profile(rol=User.ADMINISTRADOR)
        self.client.login(username=self.admin.user.username, password=PASSWORD)
        self.campana = CampanaFactory.create()
        self.account = models.Account.objects.create(name="cuenta-rep", active=True)
        self.now = timezone.now()

    def _conversacion(self, **kwargs):
        defaults = dict(
            account=self.account, campana=self.campana,
            thread_key="<t@e>", client_mail="cliente@example.com",
            timestamp=self.now, date_last_interaction=self.now,
        )
        defaults.update(kwargs)
        return models.ConversacionEmail.objects.create(**defaults)

    def _mensaje(self, conv, direction, stamp, **kwargs):
        defaults = dict(
            account=self.account, conversation=conv, direction=direction,
            content_stamp=stamp, mailbox_uidva="1:%s" % stamp, date=self.now,
        )
        defaults.update(kwargs)
        return models.Message.objects.create(**defaults)

    def _range_payload(self):
        day = self.now.date().isoformat()
        return {"start_date": day, "end_date": day}

    # --- Reporte general ---------------------------------------------------

    def test_report_counts_emails_and_conversations(self):
        attended = self._conversacion(
            atendida=True, status=models.ConversacionEmail.STATUS_ANSWERED)
        self._conversacion(
            atendida=False, status=models.ConversacionEmail.STATUS_NEW,
            client_mail="otro@example.com", thread_key="<t2@e>")
        self._mensaje(attended, models.Message.DIRECTION_INBOUND, "in1")
        self._mensaje(attended, models.Message.DIRECTION_OUTBOUND, "out1")
        self._mensaje(
            attended, models.Message.DIRECTION_OUTBOUND, "out2",
            status="error", fail_reason="rejected")

        url = reverse("email:api:v1:campaign-report", args=[self.campana.pk])
        response = self.client.post(
            url, self._range_payload(), content_type="application/json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["correos_recibidos"], 1)
        self.assertEqual(data["correos_enviados"], 2)
        self.assertEqual(data["correos_fallidos"], 1)
        self.assertEqual(data["conversaciones_iniciadas"], 2)
        self.assertEqual(data["conversaciones_atendidas"], 1)
        self.assertEqual(data["conversaciones_sin_atender"], 1)
        self.assertEqual(data["conversaciones_respondidas"], 1)
        self.assertIn("dispositions", data)

    # --- Conversaciones (listado + filtros) --------------------------------

    def test_conversations_list_and_email_filter(self):
        self._conversacion(client_mail="ana@example.com", thread_key="<a@e>")
        self._conversacion(client_mail="beto@example.com", thread_key="<b@e>")

        url = reverse(
            "email:api:v1:campaign-conversations", args=[self.campana.pk])
        # sin filtro de email -> ambas
        payload = self._range_payload()
        payload["agents"] = []
        response = self.client.post(
            url, payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)

        # filtro por email -> solo una, con campos email-appropriate
        payload["email"] = "ana"
        response = self.client.post(
            url, payload, content_type="application/json")
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["client_mail"], "ana@example.com")
        self.assertEqual(body[0]["account_name"], "cuenta-rep")
        self.assertIn("messages", body[0])
        self.assertIn("received", body[0])
        self.assertIn("sent", body[0])

    def test_conversation_detail_returns_thread(self):
        conv = self._conversacion(thread_key="<d@e>")
        self._mensaje(
            conv, models.Message.DIRECTION_INBOUND, "d1",
            subject="hola", from_mail="cliente@example.com")
        self._mensaje(
            conv, models.Message.DIRECTION_OUTBOUND, "d2",
            subject="re: hola", from_mail="soporte@example.com")
        url = reverse(
            "email:api:v1:campaign-conversation-detail",
            args=[self.campana.pk, conv.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["messages"], 2)
        self.assertEqual(len(data["mensajes"]), 2)

    def test_agents_endpoint_returns_list(self):
        url = reverse("email:api:v1:campaign-agents", args=[self.campana.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.json(), list)

    def test_report_requires_authentication(self):
        self.client.logout()
        url = reverse("email:api:v1:campaign-report", args=[self.campana.pk])
        response = self.client.post(
            url, self._range_payload(), content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
