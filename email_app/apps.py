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

from django import apps
from django.utils.translation import gettext_lazy as _


class AppConfig(apps.AppConfig):
    name = "email_app"

    informacion_de_permisos = {
        "email:api:v1:account-detail": {
            "descripcion": _("Optiene los detalles de la cuenta de correo"),
            "version": "0.0.0",
        },
        "email:api:v1:account-list": {
            "descripcion": _("Lista las cuentas de correo"),
            "version": "0.0.0",
        },
        "email:api:v1:account-test": {
            "descripcion": _("Prueba los datos de la cuenta de correo"),
            "version": "0.0.0",
        },
    }

    def configuraciones_de_permisos(self):
        return [
            {
                "nombre": "email:api:v1:account-detail",
                "roles": ["Administrador", "Gerente"],
            },
            {
                "nombre": "email:api:v1:account-list",
                "roles": ["Administrador", "Gerente"],
            },
            {
                "nombre": "email:api:v1:account-test",
                "roles": ["Administrador", "Gerente"],
            },
        ]

    def supervision_menu_items(self, request, permissions):
        """
        Due to curent impl limitations, the menu items belonging to this app are added by:
        - configuracion_telefonia_app
        """
        return []

    def ready(self):
        pass
