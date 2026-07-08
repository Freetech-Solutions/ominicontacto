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

from asgiref.sync import async_to_sync
from asgiref.sync import sync_to_async
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from ._utils import alters_data


class QuerySet(models.QuerySet):
    def __aiter__(self):
        async def generator():
            await sync_to_async(self._fetch_all)()
            for item in self._result_cache:
                yield item

        return generator()

    async def aget(self, *args, **kwargs):
        return await sync_to_async(self.get)(*args, **kwargs)

    @alters_data
    async def aupdate(self, **kwargs):
        return await sync_to_async(self.update)(**kwargs)


class Account(models.Model):
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    settings: dict = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    insights: dict = models.JSONField(default=dict, encoder=DjangoJSONEncoder)

    class Meta:
        ordering = ["id"]

    objects = QuerySet.as_manager()

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<id={self.id!r} a={self.active!r}>"

    @alters_data
    async def asave(self, **kwargs):
        return await sync_to_async(self.save)(**kwargs)

    def resync(self):
        if self.active:
            self.emit_email_fetch_service_account_event("unsubscribe")
        else:
            self.active = True
            self.__class__.objects.filter(pk=self.pk).update(active=True)
        self.emit_email_fetch_service_account_event("subscribe")

    def emit_email_fetch_service_account_event(self, event_type: str):
        all_fields = ["active", "insights", "settings"]
        min_fields = ["active"]
        if event_type == "signal:post-save":
            fields = all_fields if self.active else min_fields
        elif event_type == "subscribe":
            fields = all_fields
        elif event_type == "unsubscribe":
            fields = min_fields
        event = serializers.serialize("python", [self], fields=fields)[0]
        event["type"] = event_type
        # Imported lazily: keep the IMAP fetch stack (aioimaplib, channels
        # consumers) OUT of the model-load path so that simply importing
        # email_app.models — which Django does at startup in EVERY process,
        # including daphne and the web server — does not drag in that stack.
        from ..service.email.fetch import EmailFetchService
        async_to_sync(EmailFetchService.emit)(event)


@receiver(post_save, sender=Account, dispatch_uid="email-account.post-save", weak=False)
def email_account_post_save_signal_handler(instance: Account, **kwargs):
    instance.emit_email_fetch_service_account_event("signal:post-save")
