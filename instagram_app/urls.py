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
from django.conf.urls import include
from django.contrib.auth.decorators import login_required
from django.urls import path

from instagram_app.api.urls import urlpatterns as api_urlpatterns
from instagram_app.views import InstagramAccountConfigurationView


urlpatterns = [
    path('connections/instagram/accounts/',
         login_required(InstagramAccountConfigurationView.as_view()),
         name='instagram_accounts_configuration'),
    path('api/v1/instagram/', include((api_urlpatterns, 'instagram_app'), namespace='instagram')),
]
