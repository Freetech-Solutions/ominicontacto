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
        if obj.conversation and obj.conversation.client:
            return obj.conversation.client.obtener_datos()
        return {}

    def get_content(self, obj):
        if obj.type == 'message' and 'quick_reply' in obj.content:
            return obj.content.get('text', '')
        return obj.content


class MessageInstagramAppAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageInstagramApp
        fields = [
            'id',
            'conversation',
            'sender',
            'file'
        ]
