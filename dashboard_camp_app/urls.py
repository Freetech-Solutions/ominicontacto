# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions
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
from django.urls import path
from django.contrib.auth.decorators import login_required

from dashboard_camp_app import views

urlpatterns = [
    path('dashboard/camp/',
         login_required(views.DashboardCampView.as_view()),
         name='dashboard_camp',
         ),
    path('dashboard/camp/metrics/',
         login_required(views.dashboard_camp_metrics),
         name='dashboard_camp_metrics',
         ),
    path('dashboard/camp/list/',
         login_required(views.dashboard_camp_list),
         name='dashboard_camp_list',
         ),
    path('dashboard/camp/contact-center/',
         login_required(views.DashboardContactCenterView.as_view()),
         name='dashboard_contact_center',
         ),
    path('dashboard/camp/contact-center/data/',
         login_required(views.dashboard_contact_center_data),
         name='dashboard_contact_center_data',
         ),
    path('dashboard/camp/contact-center/data/agentes/',
         login_required(views.dashboard_contact_center_agentes),
         name='dashboard_contact_center_agentes',
         ),
    path('dashboard/camp/contact-center/data/agentes-lista/',
         login_required(views.dashboard_contact_center_agentes_lista),
         name='dashboard_contact_center_agentes_lista',
         ),
    path('dashboard/camp/contact-center/data/llamadas/',
         login_required(views.dashboard_contact_center_llamadas),
         name='dashboard_contact_center_llamadas',
         ),
    path('dashboard/camp/contact-center/data/inbound-detalle/',
         login_required(views.dashboard_contact_center_inbound_detalle),
         name='dashboard_contact_center_inbound_detalle',
         ),
    path('dashboard/camp/contact-center/data/outbound-detalle/',
         login_required(views.dashboard_contact_center_outbound_detalle),
         name='dashboard_contact_center_outbound_detalle',
         ),
    path('dashboard/camp/dialer-camp/',
         login_required(views.DashboardDialerCampView.as_view()),
         name='dashboard_outbound_calls',
         ),
    path('dashboard/camp/camp-entrantes/',
         login_required(views.DashboardCampEntrantesView.as_view()),
         name='dashboard_inbound_calls',
         ),
]
