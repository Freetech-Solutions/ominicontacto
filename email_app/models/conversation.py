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

from django.db import models
from django.utils import timezone


class QuerySet(models.QuerySet):
    pass


class ConversacionEmail(models.Model):
    """An email thread grouped for agent attention, mirroring
    ConversacionWhatsapp. Inbound messages of the same thread (by
    references/in-reply-to/message-id, scoped to account + client address) are
    grouped here.

    Lifecycle (``status``):
        new          -> Nuevo / En cola              (inbound, unassigned)
        assigned     -> Asignado                     (an agent took it)
        in_progress  -> En gestión                   (the agent opened/works it)
        answered     -> Respondido / Pendiente cliente (replied & released to the
                                                       general inbox)
        reopened     -> Reabierto / En cola          (the client wrote again)
        closed       -> Cerrado con calificación     (dispositioned)

    ``agent`` is null while the conversation sits in the campaign general inbox
    (new/reopened/answered) and set while an agent owns it (assigned/in_progress).
    """

    STATUS_NEW = "new"
    STATUS_ASSIGNED = "assigned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_ANSWERED = "answered"
    STATUS_REOPENED = "reopened"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = (
        (STATUS_NEW, "new"),
        (STATUS_ASSIGNED, "assigned"),
        (STATUS_IN_PROGRESS, "in_progress"),
        (STATUS_ANSWERED, "answered"),
        (STATUS_REOPENED, "reopened"),
        (STATUS_CLOSED, "closed"),
    )
    # statuses that live in the campaign general inbox (agent is null)
    GENERAL_INBOX_QUEUED = (STATUS_NEW, STATUS_REOPENED)
    GENERAL_INBOX_WAITING = (STATUS_ANSWERED,)
    # statuses that reopen when the client writes again
    REOPENABLE = (STATUS_ANSWERED, STATUS_CLOSED)

    account = models.ForeignKey(
        to="email_app.Account",
        on_delete=models.PROTECT,
        related_name="conversations",
    )
    campana = models.ForeignKey(
        to="ominicontacto_app.Campana",
        on_delete=models.SET_NULL,
        related_name="email_conversations",
        null=True,
    )
    contacto = models.ForeignKey(
        to="ominicontacto_app.Contacto",
        on_delete=models.SET_NULL,
        related_name="email_conversations",
        null=True,
    )
    agent = models.ForeignKey(
        to="ominicontacto_app.AgenteProfile",
        on_delete=models.SET_NULL,
        related_name="email_conversations",
        null=True,
    )
    conversation_disposition = models.ForeignKey(
        to="ominicontacto_app.HistoricalCalificacionCliente",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
    )

    # thread grouping key (root message-id of the thread)
    thread_key = models.CharField(max_length=254, db_index=True)
    subject = models.CharField(max_length=254, blank=True, default="")
    client_mail = models.CharField(max_length=254, blank=True, default="")
    client_name = models.CharField(max_length=100, blank=True, default="")

    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True
    )
    # kept for compatibility; True while an agent owns the conversation
    atendida = models.BooleanField(default=False)
    is_disposition = models.BooleanField(default=False)

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    date_last_interaction = models.DateTimeField(null=True)

    objects = QuerySet.as_manager()

    class Meta:
        ordering = ["-date_last_interaction", "-id"]

    def __str__(self):
        return f"{self.subject} <{self.client_mail}>"

    def assign_to(self, agent):
        """Take the conversation from the general inbox into ``agent``'s
        personal inbox (Asignado)."""
        self.agent = agent
        self.status = self.STATUS_ASSIGNED
        self.atendida = True
        self.save(update_fields=["agent", "status", "atendida"])
        return True

    def mark_in_progress(self):
        """The owning agent opened the conversation (En gestión)."""
        if self.status == self.STATUS_ASSIGNED:
            self.status = self.STATUS_IN_PROGRESS
            self.save(update_fields=["status"])
