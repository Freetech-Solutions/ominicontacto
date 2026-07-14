# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

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
#
from rest_framework import serializers

from instagram_app.models import ConversationInstagramApp, MessageInstagramApp


class MessageInstagramAppSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    message_id = serializers.CharField()
    conversation = serializers.PrimaryKeyRelatedField(
        queryset=ConversationInstagramApp.objects.all())
    contact_data = serializers.SerializerMethodField()
    timestamp = serializers.DateTimeField()
    content = serializers.SerializerMethodField()
    origin = serializers.CharField(source='origen')
    sender = serializers.JSONField()
    type = serializers.CharField()
    status = serializers.CharField()
    fail_reason = serializers.CharField()
    file = serializers.FileField(allow_null=True)

    def get_contact_data(self, obj):
        contact_data = self.context.get('contact_data')
        if contact_data is not None:
            return contact_data
        if obj.conversation and obj.conversation.client:
            return obj.conversation.client.obtener_datos()
        return {}

    def get_content(self, obj):
        if obj.type == 'message' and 'quick_reply' in obj.content:
            return obj.content.get('text', '')
        return obj.content


class MessageInstagramAppAttachmentSerializer(serializers.ModelSerializer):
    message_id = serializers.CharField(required=False)

    class Meta:
        model = MessageInstagramApp
        fields = [
            'id',
            'message_id',
            'conversation',
            'sender',
            'file'
        ]
