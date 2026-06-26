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

import json
from email.utils import formataddr
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from email_app import models
from email_app.service.inbound import ingest_inbound_message
from email_app.service.notify import notify_new_email_conversation
from email_app.service.outbound import build_reply_mime
from ominicontacto_app.models import Campana
from ominicontacto_app.tests.factories import (
    CampanaFactory, QueueFactory, QueueMemberFactory,
    COLUMNAS_DB_DEFAULT, COLUMNAS_DB_DEFAULT_EMAIL)
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class EmailAgentChannelTest(OMLBaseTest):

    def setUp(self):
        super(EmailAgentChannelTest, self).setUp()
        self.agente = self.crear_agente_profile()
        self.agente.grupo.email_habilitado = True
        self.agente.grupo.save()

        self.account = models.Account.objects.create(name="acc", active=True, settings={})
        self.campana = CampanaFactory.create(estado=Campana.ESTADO_ACTIVA)
        models.CampaignAccount.objects.create(campaign=self.campana, account=self.account)
        # enroll the agent into the campaign so it appears in its general inbox
        queue = QueueFactory.create(campana=self.campana)
        QueueMemberFactory(member=self.agente, queue_name=queue)

        self.client.login(username=self.agente.user.username, password=PASSWORD)

    def _inbound_message(self, message_id, in_reply_to="", references=None, stamp="s"):
        return models.Message.objects.create(
            account=self.account,
            content_bytes=b"",
            content_stamp=stamp,
            mailbox_uidva="1:1",
            subject="testing envio",
            from_mail="cliente@example.com",
            from_name="Cliente",
            to_mail="",
            to_name="",
            body_html="",
            body_text="",
            message_id=message_id,
            in_reply_to=in_reply_to,
            references=references or [],
        )

    def _conversation(self, **kwargs):
        defaults = dict(
            account=self.account,
            campana=self.campana,
            thread_key="<root@example.com>",
        )
        defaults.update(kwargs)
        return models.ConversacionEmail.objects.create(**defaults)

    # --- Inbound grouping ("recibir") --------------------------------------

    def test_ingest_creates_conversation_and_links_message(self):
        msg = self._inbound_message("<root@example.com>", stamp="s1")
        conversation, created = ingest_inbound_message(msg)
        self.assertTrue(created)
        msg.refresh_from_db()
        self.assertEqual(msg.conversation_id, conversation.id)
        self.assertEqual(msg.direction, models.Message.DIRECTION_INBOUND)
        self.assertEqual(conversation.campana_id, self.campana.id)
        self.assertIsNone(conversation.agent_id)  # lands in the general inbox

    def test_ingest_groups_same_thread_into_one_conversation(self):
        first = self._inbound_message("<root@example.com>", stamp="s1")
        reply = self._inbound_message(
            "<reply@example.com>", in_reply_to="<root@example.com>",
            references=["<root@example.com>"], stamp="s2")
        conv1, created1 = ingest_inbound_message(first)
        conv2, created2 = ingest_inbound_message(reply)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(conv1.id, conv2.id)
        self.assertEqual(conv1.mensajes.count(), 2)

    def test_ingest_reopens_conversation_after_answered(self):
        conv = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_ANSWERED,
            thread_key="<root@example.com>")
        reply = self._inbound_message(
            "<reply2@example.com>", references=["<root@example.com>"], stamp="rs")
        conv2, created = ingest_inbound_message(reply)
        self.assertFalse(created)
        self.assertEqual(conv2.id, conv.id)
        conv.refresh_from_db()
        self.assertEqual(conv.status, models.ConversacionEmail.STATUS_REOPENED)
        self.assertIsNone(conv.agent_id)  # back to the general inbox

    # --- Inbox listing (Asignado / Inbox General) -------------------------

    def test_list_assigned_tab(self):
        conv = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_IN_PROGRESS,
            thread_key="<a@e>")
        resp = self.client.get(reverse("email:api:v1:conversation-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(conv.id, [c["id"] for c in resp.json()["assigned"]])

    def test_list_general_new_subtab(self):
        conv = self._conversation(
            agent=None, status=models.ConversacionEmail.STATUS_NEW, thread_key="<b@e>")
        resp = self.client.get(reverse("email:api:v1:conversation-list"))
        self.assertIn(conv.id, [c["id"] for c in resp.json()["general"]["new"]])

    def test_list_general_waiting_client_subtab(self):
        conv = self._conversation(
            agent=None, status=models.ConversacionEmail.STATUS_ANSWERED, thread_key="<w@e>")
        resp = self.client.get(reverse("email:api:v1:conversation-list"))
        ids = [c["id"] for c in resp.json()["general"]["waiting_client"]]
        self.assertIn(conv.id, ids)

    def test_list_includes_campaign_name(self):
        conv = self._conversation(
            agent=None, status=models.ConversacionEmail.STATUS_NEW, thread_key="<cn@e>")
        resp = self.client.get(reverse("email:api:v1:conversation-list"))
        row = next(c for c in resp.json()["general"]["new"] if c["id"] == conv.id)
        self.assertEqual(row["campaign_name"], self.campana.nombre)

    # --- Realtime notifications --------------------------------------------

    @patch("notification_app.notification.AgentNotifier")
    @patch("email_app.service.notify._campaign_agent_user_ids", return_value=[101])
    def test_notify_unassigned_emits_new_conversation(self, _ids, mock_cls):
        """A fresh/reopened, still-unassigned mail alerts every campaign agent
        through the general inbox."""
        notifier = mock_cls.return_value
        notifier.notify_email_new_conversation = AsyncMock()
        conv = self._conversation(
            agent=None, status=models.ConversacionEmail.STATUS_NEW, thread_key="<nn@e>")
        async_to_sync(notify_new_email_conversation)(conv, True, None)
        notifier.notify_email_new_conversation.assert_awaited_once_with(
            101, conversation=conv)

    @patch("notification_app.notification.AgentNotifier")
    def test_notify_assigned_reply_emits_new_message(self, mock_cls):
        """A client reply on an already-assigned conversation notifies only its
        owner (so the open thread / assigned tab updates)."""
        notifier = mock_cls.return_value
        notifier.notify_email_new_message = AsyncMock()
        conv = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_IN_PROGRESS,
            thread_key="<ar@e>")
        conv.agent = self.agente  # cache to avoid a DB hit inside the async fn
        async_to_sync(notify_new_email_conversation)(conv, False, None)
        notifier.notify_email_new_message.assert_awaited_once_with(
            self.agente.user_id, conv)

    def _msg_in(self, conv, message_id, stamp):
        msg = self._inbound_message(message_id, stamp=stamp)
        msg.conversation = conv
        msg.save()
        return msg

    def test_inbox_list_is_n_plus_1_free(self):
        """Adding more conversations (each with messages) must NOT increase the
        number of SQL queries the inbox makes — counts are annotated, bodies are
        not loaded. Guards the stability requirement for thousands of queued
        emails."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        url = reverse("email:api:v1:conversation-list")
        c0 = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_IN_PROGRESS,
            thread_key="<n0@e>")
        self._msg_in(c0, "<n0a@e>", "n0a")
        self._msg_in(c0, "<n0b@e>", "n0b")
        with CaptureQueriesContext(connection) as first:
            self.client.get(url)

        for i in range(1, 6):
            ci = self._conversation(
                agent=self.agente, status=models.ConversacionEmail.STATUS_IN_PROGRESS,
                thread_key="<n{0}@e>".format(i))
            self._msg_in(ci, "<n{0}a@e>".format(i), "n{0}a".format(i))
            self._msg_in(ci, "<n{0}b@e>".format(i), "n{0}b".format(i))
        with CaptureQueriesContext(connection) as second:
            self.client.get(url)

        self.assertEqual(len(first.captured_queries), len(second.captured_queries))

    # --- Attend (asignar: inbox general -> personal) -----------------------

    def test_attend_assigns_unassigned_conversation(self):
        conv = self._conversation(
            agent=None, status=models.ConversacionEmail.STATUS_NEW, thread_key="<c@e>")
        url = reverse("email:api:v1:conversation-attend", args=[conv.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        conv.refresh_from_db()
        self.assertEqual(conv.agent_id, self.agente.id)
        self.assertEqual(conv.status, models.ConversacionEmail.STATUS_ASSIGNED)

    def test_retrieve_owner_marks_in_progress(self):
        conv = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_ASSIGNED,
            thread_key="<ip@e>")
        url = reverse("email:api:v1:conversation-detail", args=[conv.pk])
        self.client.get(url)
        conv.refresh_from_db()
        self.assertEqual(conv.status, models.ConversacionEmail.STATUS_IN_PROGRESS)

    def test_retrieve_forbidden_when_not_owner(self):
        """An agent must NOT read a general-inbox (unassigned) conversation
        without taking it first."""
        conv = self._conversation(
            agent=None, status=models.ConversacionEmail.STATUS_NEW, thread_key="<noown@e>")
        url = reverse("email:api:v1:conversation-detail", args=[conv.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_attend_conflict_when_owned_by_other_agent(self):
        other = self.crear_agente_profile()
        conv = self._conversation(
            agent=other, status=models.ConversacionEmail.STATUS_ASSIGNED, thread_key="<d@e>")
        url = reverse("email:api:v1:conversation-attend", args=[conv.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    # --- Release (desasignar -> vuelve a la cola como nuevo) ---------------

    def test_release_returns_conversation_to_general_new(self):
        conv = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_IN_PROGRESS,
            thread_key="<rel@e>")
        url = reverse("email:api:v1:conversation-release", args=[conv.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        conv.refresh_from_db()
        self.assertIsNone(conv.agent_id)
        self.assertEqual(conv.status, models.ConversacionEmail.STATUS_NEW)
        self.assertFalse(conv.atendida)
        # reaparece en el inbox general (subtab Nuevo)
        listing = self.client.get(reverse("email:api:v1:conversation-list")).json()
        self.assertIn(conv.id, [c["id"] for c in listing["general"]["new"]])

    # --- Guardar contacto (email: telefono NO obligatorio) -----------------

    def test_contact_save_does_not_require_phone(self):
        conv = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_IN_PROGRESS,
            thread_key="<ctc@e>")
        url = reverse("email:api:v1:conversation-contact", args=[conv.pk])
        # Obtengo nombres de columnas de base de datos a editar
        nombre = str(COLUMNAS_DB_DEFAULT[1])
        email = str(COLUMNAS_DB_DEFAULT[COLUMNAS_DB_DEFAULT_EMAIL])
        # no se envía "_telefono" — para email basta el correo
        resp = self.client.post(
            url, data=json.dumps({nombre: "Juan", email: "juan@example.com"}),
            content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        conv.refresh_from_db()
        self.assertIsNotNone(conv.contacto_id)
        self.assertEqual(conv.contacto.telefono, "")

    def test_disposition_autocreates_contact_from_email(self):
        """Qualifying a conversation with no contact must not force the contact
        form: a minimal contact is auto-created from the sender's email."""
        from email_app.api.v1.conversation import ViewSet
        conv = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_IN_PROGRESS,
            client_mail="nuevo@example.com", thread_key="<auto@e>")
        self.assertIsNone(conv.contacto_id)
        contacto = ViewSet()._ensure_email_contacto(conv)
        self.assertIsNotNone(contacto.pk)
        self.assertEqual(contacto.email, "nuevo@example.com")
        self.assertEqual(contacto.telefono, "")
        self.assertEqual(contacto.bd_contacto_id, self.campana.bd_contacto_id)

    # --- Mark as read ------------------------------------------------------

    def test_mark_as_read(self):
        conv = self._conversation(agent=self.agente, atendida=True, thread_key="<e@e>")
        msg = self._inbound_message("<e@e>", stamp="s3")
        msg.conversation = conv
        msg.is_read = False
        msg.save()
        url = reverse("email:api:v1:conversation-mark-as-read", args=[conv.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        msg.refresh_from_db()
        self.assertTrue(msg.is_read)

    # --- Permission --------------------------------------------------------

    def test_requires_email_enabled_group(self):
        self.agente.grupo.email_habilitado = False
        self.agente.grupo.save()
        url = reverse("email:api:v1:conversation-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # --- Reply (responder + threading + adjuntos) --------------------------

    def test_build_reply_mime_threading_and_attachment(self):
        config = {"from_addr": "campania@example.com"}
        conv = self._conversation(
            subject="testing envio", client_mail="cliente@example.com", thread_key="<root@e>")
        last = self._inbound_message(
            "<root@e>", references=["<root@e>"], stamp="u1")
        upload = SimpleUploadedFile("doc.txt", b"hello", content_type="text/plain")
        mime = build_reply_mime(config, conv, last, "cuerpo", "", [upload])
        self.assertEqual(mime["To"], "cliente@example.com")
        self.assertTrue(mime["Subject"].startswith("Re:"))
        self.assertEqual(mime["In-Reply-To"], "<root@e>")
        self.assertIn("<root@e>", mime["References"])
        names = [part.get_filename() for part in mime.iter_attachments()]
        self.assertIn("doc.txt", names)

    def test_rewrite_inline_cids(self):
        from email_app.api.v1.conversation import rewrite_inline_cids
        html = '<p>Hola</p><img src="cid:img1@host"><img src="cid:missing">'
        attachments = [{"cid": "<img1@host>", "name": "a.png", "path": "email/x/a.png"}]
        out = rewrite_inline_cids(html, attachments)
        self.assertNotIn("cid:img1@host", out)   # rewritten to the stored URL
        self.assertIn("a.png", out)
        self.assertIn("cid:missing", out)        # unknown cid left untouched

    def test_build_from_header_policy(self):
        from email_app.service.outbound import build_from_header
        cfg = {"from_addr": "soporte@fts.com"}
        agent_name = self.agente.user.get_full_name() or self.agente.user.username
        # 1. no display name -> bare address
        self.assertEqual(build_from_header(cfg, None), "soporte@fts.com")
        # 2. general name only
        self.assertEqual(
            build_from_header({**cfg, "from_name": "Equipo de Devops"}, self.agente),
            formataddr(("Equipo de Devops", "soporte@fts.com")))
        # 3. general name + agent name
        self.assertEqual(
            build_from_header(
                {**cfg, "from_name": "Soporte", "include_agent_name": True},
                self.agente),
            formataddr(("Soporte ({0})".format(agent_name), "soporte@fts.com")))
        # 4. agent name only (no general name)
        self.assertEqual(
            build_from_header({**cfg, "include_agent_name": True}, self.agente),
            formataddr((agent_name, "soporte@fts.com")))

    def test_build_reply_mime_cc_and_bcc(self):
        config = {"from_addr": "campania@example.com"}
        conv = self._conversation(
            subject="asunto", client_mail="cliente@example.com", thread_key="<cc@e>")
        mime = build_reply_mime(
            config, conv, None, "cuerpo", "", [],
            cc="copia@example.com", bcc="oculta@example.com")
        self.assertEqual(mime["Cc"], "copia@example.com")
        self.assertEqual(mime["Bcc"], "oculta@example.com")

    @patch("email_app.service.outbound.deliver")
    def test_reply_creates_outbound_message(self, mock_deliver):
        self.account.settings = {"outbound": {"from_addr": "campania@example.com"}}
        self.account.save()
        conv = self._conversation(
            agent=self.agente, atendida=True, subject="testing envio",
            client_mail="cliente@example.com", thread_key="<root@e>")
        inbound = self._inbound_message("<root@e>", stamp="ri")
        inbound.conversation = conv
        inbound.save()

        url = reverse("email:api:v1:conversation-reply", args=[conv.pk])
        resp = self.client.post(url, {"body_text": "hola, respondo"})

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(mock_deliver.called)
        outbound = conv.mensajes.filter(direction=models.Message.DIRECTION_OUTBOUND).first()
        self.assertIsNotNone(outbound)
        self.assertEqual(outbound.to_mail, "cliente@example.com")
        self.assertTrue(outbound.subject.startswith("Re:"))
        self.assertEqual(outbound.sender.get("agent_id"), self.agente.user_id)
        # default mode "keep" -> sigue en gestión (inbox personal)
        conv.refresh_from_db()
        self.assertEqual(conv.agent_id, self.agente.id)
        self.assertEqual(conv.status, models.ConversacionEmail.STATUS_IN_PROGRESS)

    @patch("email_app.service.outbound.deliver")
    def test_reply_unassign_releases_to_general_inbox(self, mock_deliver):
        self.account.settings = {"outbound": {"from_addr": "campania@example.com"}}
        self.account.save()
        conv = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_IN_PROGRESS,
            subject="testing envio", client_mail="cliente@example.com", thread_key="<un@e>")
        url = reverse("email:api:v1:conversation-reply", args=[conv.pk])
        resp = self.client.post(url, {"body_text": "respondo y suelto", "mode": "unassign"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        conv.refresh_from_db()
        self.assertIsNone(conv.agent_id)  # vuelve al inbox general
        self.assertEqual(conv.status, models.ConversacionEmail.STATUS_ANSWERED)

    def test_reply_requires_body(self):
        conv = self._conversation(
            agent=self.agente, status=models.ConversacionEmail.STATUS_IN_PROGRESS,
            thread_key="<empty@e>")
        url = reverse("email:api:v1:conversation-reply", args=[conv.pk])
        resp = self.client.post(url, {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
