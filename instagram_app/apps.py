# -*- coding: utf-8 -*-
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
    }
