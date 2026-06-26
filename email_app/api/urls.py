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

from django.conf.urls import include
from django.urls import path
from rest_framework import routers

from .v1 import account as account_v1
from .v1 import conversation as conversation_v1
from .v1 import message as message_v1
from .v1 import self as self_v1

router_v1 = routers.SimpleRouter(trailing_slash=False)

router_v1.register("accounts", account_v1.ViewSet, "account")
router_v1.register("conversations", conversation_v1.ViewSet, "conversation")
router_v1.register("messages", message_v1.ViewSet, "message")
router_v1.register("self", self_v1.ViewSet, "self")


api_urls = [
    path("v1/", include((router_v1.urls, "v1"), namespace="v1")),
]
