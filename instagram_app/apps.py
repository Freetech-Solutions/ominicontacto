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
            {'nombre': 'api_instagram_reports',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'api_campaign_instagram_report_conversations',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'api_campaign_instagram_report_conversation_detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'instagram:account-configuration-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'instagram:account-configuration-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'instagram:templates-instagram-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'instagram:templates-instagram-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'instagram:conversation-list',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-mark-as-read',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-detail',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-assign-contact',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-attend-chat',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-messages',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-reactive-expired-conversation',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-send-message-attachment',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-send-message-template',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-send-message-text',
             'roles': ['Agente']},
            {'nombre': 'instagram:conversation-send-message-whatsapp-template',
             'roles': ['Agente']},
            {'nombre': 'instagram:disposition-list',
             'roles': ['Agente']},
            {'nombre': 'instagram:disposition-options',
             'roles': ['Agente']},
            {'nombre': 'instagram:disposition-detail',
             'roles': ['Agente']},
            {'nombre': 'instagram:disposition-history',
             'roles': ['Agente']},
            {'nombre': 'instagram:contact-list',
             'roles': ['Agente']},
            {'nombre': 'instagram:contact-detail',
             'roles': ['Agente']},
            {'nombre': 'instagram:contact-create-contact-from-conversation',
             'roles': ['Agente']},
            {'nombre': 'instagram:contact-db-fields',
             'roles': ['Agente']},
            {'nombre': 'instagram:contact-search',
             'roles': ['Agente']},
            {'nombre': 'instagram:contact-suggest-match',
             'roles': ['Agente']},
            {'nombre': 'instagram:transfer-agents',
             'roles': ['Agente']},
            {'nombre': 'instagram:transfer-to-agent',
             'roles': ['Agente']},
            {'nombre': 'instagram:templates-list',
             'roles': ['Agente']},
        ]

    informacion_de_permisos = {
        'instagram_accounts_configuration': {
            'descripcion': _('Configuración general de Instagram'),
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
        'instagram:account-configuration-list':
            {'descripcion': _('Lista de cuentas, campañas y horarios de Instagram'),
             'version': '2.6.6'},
        'instagram:account-configuration-detail':
            {'descripcion': _('Detalle de cuenta de Instagram'), 'version': '2.6.6'},
        'instagram:templates-instagram-list':
            {'descripcion': _('Lista de plantillas Instagram'), 'version': '2.6.6'},
        'instagram:templates-instagram-detail':
            {'descripcion': _('Detalle de plantilla Instagram'), 'version': '2.6.6'},
        'instagram:conversation-list':
            {'descripcion': _('Conversaciones Instagram del agente'), 'version': '2.6.6'},
        'instagram:conversation-mark-as-read':
            {'descripcion': _('Marcar conversación Instagram como leída'), 'version': '2.6.6'},
        'instagram:conversation-detail':
            {'descripcion': _('Detalle de conversación Instagram'), 'version': '2.6.6'},
        'instagram:conversation-assign-contact':
            {'descripcion': _('Asignar contacto a conversación Instagram'), 'version': '2.6.6'},
        'instagram:conversation-attend-chat':
            {'descripcion': _('Atender conversación Instagram'), 'version': '2.6.6'},
        'instagram:conversation-messages':
            {'descripcion': _('Mensajes de una conversación Instagram'), 'version': '2.6.6'},
        'instagram:conversation-reactive-expired-conversation':
            {'descripcion': _('Reactivar conversación Instagram expirada'), 'version': '2.6.6'},
        'instagram:conversation-send-message-attachment':
            {'descripcion': _('Enviar adjunto en conversación Instagram'), 'version': '2.6.6'},
        'instagram:conversation-send-message-template':
            {'descripcion': _('Enviar plantilla en conversación Instagram'), 'version': '2.6.6'},
        'instagram:conversation-send-message-text':
            {'descripcion': _('Enviar texto en conversación Instagram'), 'version': '2.6.6'},
        'instagram:conversation-send-message-whatsapp-template':
            {'descripcion': _('Enviar plantilla WhatsApp en conversación Instagram'),
             'version': '2.6.6'},
        'instagram:disposition-list':
            {'descripcion': _('Calificar conversación Instagram'), 'version': '2.6.6'},
        'instagram:disposition-options':
            {'descripcion': _('Opciones de calificación de conversación Instagram'),
             'version': '2.6.6'},
        'instagram:disposition-detail':
            {'descripcion': _('Detalle de calificación de conversación Instagram'),
             'version': '2.6.6'},
        'instagram:disposition-history':
            {'descripcion': _('Historial de calificaciones de conversación Instagram'),
             'version': '2.6.6'},
        'instagram:contact-list':
            {'descripcion': _('Lista contactos de la campaña'), 'version': '2.6.6'},
        'instagram:contact-detail':
            {'descripcion': _('Obtiene un contacto de la campaña'), 'version': '2.6.6'},
        'instagram:contact-create-contact-from-conversation':
            {'descripcion': _('Crea un contacto desde una conversación Instagram'),
             'version': '2.6.6'},
        'instagram:contact-db-fields':
            {'descripcion': _('Campos de la base de contactos de la campaña'), 'version': '2.6.6'},
        'instagram:contact-search':
            {'descripcion': _('Busca contactos de la campaña'), 'version': '2.6.6'},
        'instagram:contact-suggest-match':
            {'descripcion': _('Sugiere contactos para una conversación Instagram'),
             'version': '2.6.6'},
        'instagram:transfer-agents':
            {'descripcion': _('Agentes a los que transferir una conversación Instagram'),
             'version': '2.6.6'},
        'instagram:transfer-to-agent':
            {'descripcion': _('Transfiere una conversación Instagram a un agente'),
             'version': '2.6.6'},
        'instagram:templates-list':
            {'descripcion': _('Templates de Instagram por campaña'), 'version': '2.6.6'},
    }
