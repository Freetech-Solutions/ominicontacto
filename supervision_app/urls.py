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

from django.urls import path
from django.contrib.auth.decorators import login_required
from supervision_app.views import (
    SupervisionAgentesView,
    SupervisionCampanasEntrantesView,
    SupervisionCampanasSalientesView,
    SupervisionCampanasDialerView,
    DashboardContactCenterView,
    DashboardContactCenterCampaignView,
    DashboardPanelDialerView,
    DashboardPanelDialerCampaignView,
    dashboard_contact_center_data,
    dashboard_contact_center_agentes,
    dashboard_contact_center_agentes_lista,
    dashboard_contact_center_bots_campana,
    dashboard_contact_center_llamadas,
    dashboard_panel_dialer_estado,
    supervision_voicebot_llamadas,
)

urlpatterns = [
    path('supervision/agentes/',
         login_required(SupervisionAgentesView.as_view()),
         name='supervision_agentes',
         ),
    path('supervision/agentes/data/voicebot-llamadas/',
         login_required(supervision_voicebot_llamadas),
         name='supervision_voicebot_llamadas',
         ),
    path('supervision/campanas/entrantes/',
         login_required(SupervisionCampanasEntrantesView.as_view()),
         name='supervision_campanas_entrantes',
         ),
    path('supervision/campanas/salientes/',
         login_required(SupervisionCampanasSalientesView.as_view()),
         name='supervision_campanas_salientes',
         ),
    path('supervision/campanas/dialer/',
         login_required(SupervisionCampanasDialerView.as_view()),
         name='supervision_campanas_dialer',
         ),
    # Rutas de Dashboard (Panel General)
    path('supervision/<int:id_camp>/panel-general/',
         login_required(DashboardContactCenterCampaignView.as_view()),
         name='supervision_contact_center_campaign',
         ),
    path('supervision/panel-general/',
         login_required(DashboardContactCenterView.as_view()),
         name='supervision_contact_center',
         ),
    path('supervision/panel-general/data/',
         login_required(dashboard_contact_center_data),
         name='supervision_contact_center_data',
         ),
    path('supervision/panel-general/data/agentes/',
         login_required(dashboard_contact_center_agentes),
         name='supervision_contact_center_agentes',
         ),
    path('supervision/panel-general/data/agentes-lista/',
         login_required(dashboard_contact_center_agentes_lista),
         name='supervision_contact_center_agentes_lista',
         ),
    path('supervision/panel-general/data/bots-campana/',
         login_required(dashboard_contact_center_bots_campana),
         name='supervision_contact_center_bots_campana',
         ),
    path('supervision/panel-general/data/llamadas/',
         login_required(dashboard_contact_center_llamadas),
         name='supervision_contact_center_llamadas',
         ),
    # Panel Dialer (sin Inbound / Outbound)
    path('supervision/<int:id_camp>/panel-dialer/',
         login_required(DashboardPanelDialerCampaignView.as_view()),
         name='supervision_panel_dialer_campaign',
         ),
    path('supervision/panel-dialer/',
         login_required(DashboardPanelDialerView.as_view()),
         name='supervision_panel_dialer',
         ),
    path('supervision/panel-dialer/data/estado-discador/',
         login_required(dashboard_panel_dialer_estado),
         name='supervision_panel_dialer_estado',
         ),
]
