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

from django.core.files.storage import default_storage
from rest_framework import response
from rest_framework import serializers
from rest_framework import viewsets

from ... import models
from ..permissions import ViewPermission


class RetrieveSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    account_id = serializers.IntegerField()

    date = serializers.DateTimeField()
    subject = serializers.CharField()
    from_mail = serializers.EmailField()
    from_name = serializers.CharField()
    to_mail = serializers.EmailField()
    to_name = serializers.CharField()
    body_html = serializers.CharField()
    body_text = serializers.CharField()
    message_id = serializers.CharField()
    in_reply_to = serializers.CharField()
    references = serializers.ListField(child=serializers.CharField())
    attachments = serializers.SerializerMethodField()

    def get_attachments(self, message):
        return [
            {
                "cid": attachment["cid"],
                "name": attachment["name"],
                "url": default_storage.url(attachment["path"]),
            }
            for attachment in message.attachments
        ]

    @classmethod
    def get_instance(cls, pk):
        queryset = models.Message.objects.only(
            "id",
            "account_id",
            "date",
            "subject",
            "from_mail",
            "from_name",
            "to_mail",
            "to_name",
            "body_html",
            "body_text",
            "message_id",
            "in_reply_to",
            "references",
            "attachments",
        )
        instance = queryset.get(pk=pk)
        return cls(instance=instance)


class ViewSet(viewsets.ViewSet):
    permission_classes = [
        ViewPermission,
    ]

    def retrieve(self, request, pk):
        serializer = RetrieveSerializer.get_instance(pk)
        self.check_object_permissions(request, serializer.instance)
        return response.Response(data=serializer.data)
