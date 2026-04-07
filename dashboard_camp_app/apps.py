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
from __future__ import unicode_literals

from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.apps import AppConfig


class DashboardCampAppConfig(AppConfig):
    name = 'dashboard_camp_app'

    def supervision_menu_items(self, request, permissions):
        if 'dashboard_camp' in permissions:
            return [{
                'order': 850,
                'label': _('Dashboards'),
                'icon': 'icon-graph',
                'id': 'menuDashboardCamp',
                'children': [
                    {
                        'label': _('Panel general'),
                        'url': reverse('dashboard_contact_center'),
                    },
                    # Temporalmente ocultas
                    # {
                    #     'label': _('Outbound Calls'),
                    #     'url': reverse('dashboard_outbound_calls'),
                    # },
                    # {
                    #     'label': _('Camp Entrantes'),
                    #     'url': reverse('dashboard_inbound_calls'),
                    # }
                ]
            }]
        return None

    def configuraciones_de_permisos(self):
        return [
            {'nombre': 'dashboard_camp',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
        ]

    informacion_de_permisos = {
        'dashboard_camp':
            {'descripcion': _('Dashboard de campañas'), 'version': '1.23.0'},
    }
