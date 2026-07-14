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

from constance import config as constance_config
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files.storage import default_storage
from django.utils.translation import ugettext as _
from rest_framework import decorators
from rest_framework import response
from rest_framework import serializers
from rest_framework import viewsets
from ominicontacto_app.models import User

"""
this viewset is related to webui-app, although right now it is included in email_app
in the future must be moved to e.g. api_app
"""


class PayloadSerializer(serializers.Serializer):
    class Brand(serializers.Serializer):
        logo_full = serializers.SerializerMethodField()

        def get_logo_full(self, config):
            prop = config["logo_full"]
            cval = self.context["cget"](prop)
            dval = self.context["dget"](prop)
            if cval != dval:
                val = self.context["curl"](cval)
            else:
                val = self.context["durl"](dval)
            return serializers.URLField().to_representation(val)

    brand = Brand()

    class AnonymousUser(serializers.Serializer):
        id = serializers.IntegerField()
        is_anonymous = serializers.BooleanField()
        is_authenticated = serializers.BooleanField()

    class AuthenticatedUser(serializers.Serializer):
        id = serializers.IntegerField()
        username = serializers.CharField()
        first_name = serializers.CharField()
        last_name = serializers.CharField()
        is_anonymous = serializers.BooleanField()
        is_authenticated = serializers.BooleanField()
        is_agent = serializers.BooleanField(source="is_agente")
        is_supervisor = serializers.BooleanField()

    class AgentUser(AuthenticatedUser):
        class AgentProfile(serializers.Serializer):
            id = serializers.IntegerField()

        profile = AgentProfile(source="agenteprofile")

    class SupervisorUser(AuthenticatedUser):
        class SupervisorProfile(serializers.Serializer):
            id = serializers.IntegerField()

        profile = SupervisorProfile(source="supervisorprofile")

    user = AnonymousUser()

    def get_fields(self):
        fields = super().get_fields()
        user: User = self.instance["user"]
        if user.is_authenticated:
            if user.is_agente:
                fields["user"] = self.AgentUser()
            elif user.is_supervisor:
                fields["user"] = self.SupervisorUser()
        return fields

    @classmethod
    def get_instance(cls, request):
        return cls(
            instance={
                "brand": {"logo_full": "IC_LOGO_FULL"},
                "user": request.user,
            },
            context={
                "dget": lambda key: settings.CONSTANCE_CONFIG[key][0],  # default
                "cget": lambda key: getattr(constance_config, key),  # current
                "durl": staticfiles_storage.url,
                "curl": default_storage.url,
            },
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True, write_only=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        self.instance = authenticate(**attrs)
        if self.instance is None:
            raise serializers.ValidationError(_("Invalid credentials or deactivated Account."))
        return attrs

    @classmethod
    def get_instance(cls, data):
        return cls(data=data)


class ViewSet(viewsets.ViewSet):
    @decorators.action(detail=False, methods=["post"], permission_classes=[])
    def login(self, request):
        serializer = LoginSerializer.get_instance(request.data)
        serializer.is_valid(raise_exception=True)
        logout(request)
        login(request, serializer.instance)
        serializer = PayloadSerializer.get_instance(request)
        return response.Response(data=serializer.data)

    @decorators.action(detail=False, permission_classes=[])
    def payload(self, request):
        serializer = PayloadSerializer.get_instance(request)
        return response.Response(data=serializer.data)
