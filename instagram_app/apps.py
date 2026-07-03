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
from __future__ import unicode_literals

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InstagramAppConfig(AppConfig):
    name = 'instagram_app'

    def configuraciones_de_permisos(self):
        return [
            {'nombre': 'instagram_accounts_configuration',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'instagram_account',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'api_instagram_reports',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'api_campaign_instagram_report_conversations',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'api_campaign_instagram_report_conversation_detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
        ]

    informacion_de_permisos = {
        'instagram_accounts_configuration': {
            'descripcion': _('Configuración general de Instagram'),
            'version': '1.27.0',
        },
        'instagram_account': {
            'descripcion': _('Configuración de cuenta Instagram'),
            'version': '1.27.0',
        },
        'api_instagram_reports': {
            'descripcion': _('Reportes Instagram'),
            'version': '1.27.0',
        },
        'api_campaign_instagram_report_conversations': {
            'descripcion': _('Reportes Conversaciones Instagram'),
            'version': '1.27.0',
        },
        'api_campaign_instagram_report_conversation_detail': {
            'descripcion': _('Detalle de conversación Instagram para reportes'),
            'version': '1.27.0',
        },
    }
