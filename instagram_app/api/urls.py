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
import instagram_app.api.v1.account_configuration
import instagram_app.api.v1.contact
import instagram_app.api.v1.conversation
import instagram_app.api.v1.disposition
import instagram_app.api.v1.reporte
import instagram_app.api.v1.templates
import instagram_app.api.v1.templates_instagram
import instagram_app.api.v1.transfer

from django.urls import path

from instagram_app.api import ViewSetRouter


router = ViewSetRouter(trailing_slash=False)

routes = (
    (r"account", instagram_app.api.v1.account_configuration.ViewSet),
    (r"campaigns", instagram_app.api.v1.account_configuration.CampaignViewSet),
    (r"schedules", instagram_app.api.v1.account_configuration.ScheduleViewSet),
    (r"chat", instagram_app.api.v1.conversation.ViewSet),
    (r"contact/(?P<campana_pk>[^/.]+)", instagram_app.api.v1.contact.ViewSet),
    (r"disposition_chat", instagram_app.api.v1.disposition.ViewSet),
    (r"transfer", instagram_app.api.v1.transfer.ViewSet),
    (r"templates/(?P<campana_pk>[^/.]+)", instagram_app.api.v1.templates.ViewSet),
    (r"templates_instagram", instagram_app.api.v1.templates_instagram.ViewSet),
)

for prefix, viewset in routes:
    router.register(prefix, viewset)

urlpatterns = [
    path(
        'reports/',
        instagram_app.api.v1.reporte.ReportAPIView.as_view(),
        name='api_instagram_reports',
    ),
    path(
        'chat/<int:campaing_id>/filter_chats',
        instagram_app.api.v1.conversation.ReportConversationAPIView.as_view(),
        name='api_campaign_instagram_report_conversations',
    ),
    path(
        'chat/<int:pk>/report_detail',
        instagram_app.api.v1.conversation.ReportConversationDetailAPIView.as_view(),
        name='api_campaign_instagram_report_conversation_detail',
    ),
] + router.urls
