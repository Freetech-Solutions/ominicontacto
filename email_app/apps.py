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
            "descripcion": _("Obtiene los detalles de la cuenta de correo"),
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
        "email:api:v1:account-messages": {
            "descripcion": _("Lista los mensajes de la cuenta de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:account-purge-history": {
            "descripcion": _("Purga el historial de la cuenta de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:account-resync": {
            "descripcion": _("Resincroniza la cuenta de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:account-template": {
            "descripcion": _("Plantilla de la cuenta de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:message-detail": {
            "descripcion": _("Obtiene un mensaje de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-list": {
            "descripcion": _("Lista las conversaciones de correo del agente"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-detail": {
            "descripcion": _("Obtiene una conversación de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-attend": {
            "descripcion": _("Atiende una conversación de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-contact": {
            "descripcion": _("Contacto de una conversación de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-contact-fields": {
            "descripcion": _("Campos de contacto de una conversación de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-disposition": {
            "descripcion": _("Califica una conversación de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-disposition-options": {
            "descripcion": _("Opciones de calificación de una conversación de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-mark-as-read": {
            "descripcion": _("Marca una conversación de correo como leída"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-release": {
            "descripcion": _("Libera una conversación de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:conversation-reply": {
            "descripcion": _("Responde una conversación de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:campaign-report": {
            "descripcion": _("Reporte de campaña de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:campaign-agents": {
            "descripcion": _("Agentes de campaña de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:campaign-conversations": {
            "descripcion": _("Conversaciones de campaña de correo"),
            "version": "2.6.6",
        },
        "email:api:v1:campaign-conversation-detail": {
            "descripcion": _("Detalle de conversación de campaña de correo"),
            "version": "2.6.6",
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
            {
                "nombre": "email:api:v1:account-messages",
                "roles": ["Administrador", "Gerente"],
            },
            {
                "nombre": "email:api:v1:account-purge-history",
                "roles": ["Administrador", "Gerente"],
            },
            {
                "nombre": "email:api:v1:account-resync",
                "roles": ["Administrador", "Gerente"],
            },
            {
                "nombre": "email:api:v1:account-template",
                "roles": ["Administrador", "Gerente"],
            },
            {
                "nombre": "email:api:v1:message-detail",
                "roles": ["Administrador", "Gerente"],
            },
            {
                "nombre": "email:api:v1:conversation-list",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:conversation-detail",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:conversation-attend",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:conversation-contact",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:conversation-contact-fields",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:conversation-disposition",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:conversation-disposition-options",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:conversation-mark-as-read",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:conversation-release",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:conversation-reply",
                "roles": ["Agente"],
            },
            {
                "nombre": "email:api:v1:campaign-report",
                "roles": ["Administrador", "Gerente", "Supervisor", "Referente"],
            },
            {
                "nombre": "email:api:v1:campaign-agents",
                "roles": ["Administrador", "Gerente", "Supervisor", "Referente"],
            },
            {
                "nombre": "email:api:v1:campaign-conversations",
                "roles": ["Administrador", "Gerente", "Supervisor", "Referente"],
            },
            {
                "nombre": "email:api:v1:campaign-conversation-detail",
                "roles": ["Administrador", "Gerente", "Supervisor", "Referente"],
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
