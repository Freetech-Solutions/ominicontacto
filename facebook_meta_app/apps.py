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


class FacebookMetaAppConfig(AppConfig):
    name = 'facebook_meta_app'

    def configuraciones_de_permisos(self):
        return [
            # Configuración general de Messenger
            {'nombre': 'messenger_meta_configuration',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},

            # Plantillas de mensaje
            {'nombre': 'facebook_message_templates_configuration',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'facebook_message_template_groups',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},

            # API v1 / routers
            {'nombre': 'destination',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'api_facebook_reports',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'api_campaign_facebook_report_conversations',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'facebook:contact-list',
             'roles': ['Agente']},
            {'nombre': 'facebook:contact-detail',
             'roles': ['Agente']},
            {'nombre': 'facebook:contact-create-contact-from-conversation',
             'roles': ['Agente']},
            {'nombre': 'facebook:contact-db-fields',
             'roles': ['Agente']},
            {'nombre': 'facebook:contact-search',
             'roles': ['Agente']},
            {'nombre': 'facebook:contact-suggest-match',
             'roles': ['Agente']},
            {'nombre': 'facebook:transfer-agents',
             'roles': ['Agente']},
            {'nombre': 'facebook:transfer-to-agent',
             'roles': ['Agente']},

            # Templates
            {'nombre': 'facebook:templates-list',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-list',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-active-conversations',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-agent-chats-lists',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-closed-conversations',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-mark-as-read',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-assign-contact',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-attend-chat',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-close-conversation',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-messages',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-send-message-attachment',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-send-message-template',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-send-message-text',
             'roles': ['Agente']},
            {'nombre': 'facebook:conversation-detail',
             'roles': ['Agente', 'Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'facebook:disposition-list',
             'roles': ['Agente']},
            {'nombre': 'facebook:disposition-options',
             'roles': ['Agente']},
            {'nombre': 'facebook:disposition-detail',
             'roles': ['Agente']},
            {'nombre': 'facebook:disposition-history',
             'roles': ['Agente']},
            {'nombre': 'facebook:page-configuration-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'facebook:page-configuration-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'facebook:campaign-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'facebook:templates-messenger-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'facebook:templates-messenger-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'facebook:templates-group-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'facebook:templates-group-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
        ]

    informacion_de_permisos = {
        'messenger_meta_configuration': {
            'descripcion': _('Configuración general de Messenger'),
            'version': '1.26.0'
        },
        'facebook_message_templates_configuration': {
            'descripcion': _('Configuración de plantillas de mensajes'),
            'version': '1.26.0'
        },
        'facebook_message_template_groups': {
            'descripcion': _('Grupos de plantillas de mensajes'),
            'version': '1.26.0'
        },
        'destination': {'descripcion': _('Destinos'), 'version': '1.26.0'},
        'api_facebook_reports': {'descripcion': _('Reportes Meta/Facebook'), 'version': '2.6.4'},
        'api_campaign_facebook_report_conversations': {
            'descripcion': _('Reportes Conversaciones Meta/Facebook'),
            'version': '2.6.4'},
        'facebook:contact-list':
            {'descripcion': _('Lista contactos de la campaña'), 'version': '2.6.6'},
        'facebook:contact-detail':
            {'descripcion': _('Obtiene un contacto de la campaña'), 'version': '2.6.6'},
        'facebook:contact-create-contact-from-conversation':
            {'descripcion': _('Crea un contacto desde una conversación Facebook'),
             'version': '2.6.6'},
        'facebook:contact-db-fields':
            {'descripcion': _('Campos de la base de contactos de la campaña'), 'version': '2.6.6'},
        'facebook:contact-search':
            {'descripcion': _('Busca contactos de la campaña'), 'version': '2.6.6'},
        'facebook:contact-suggest-match':
            {'descripcion': _('Sugiere contactos para una conversación Facebook'),
             'version': '2.6.6'},
        'facebook:transfer-agents':
            {'descripcion': _('Agentes a los que transferir una conversación Facebook'),
             'version': '2.6.6'},
        'facebook:transfer-to-agent':
            {'descripcion': _('Transfiere una conversación Facebook a un agente'),
             'version': '2.6.6'},
        'facebook:templates-list':
            {'descripcion': _('Templates de Facebook por campaña'), 'version': '2.6.6'},
        'facebook:conversation-list':
            {'descripcion': _('Conversaciones Facebook del agente'), 'version': '2.6.6'},
        'facebook:conversation-active-conversations':
            {'descripcion': _('Conversaciones Facebook activas'), 'version': '2.6.6'},
        'facebook:conversation-agent-chats-lists':
            {'descripcion': _('Listas de chats Facebook del agente'), 'version': '2.6.6'},
        'facebook:conversation-closed-conversations':
            {'descripcion': _('Conversaciones Facebook cerradas'), 'version': '2.6.6'},
        'facebook:conversation-mark-as-read':
            {'descripcion': _('Marcar conversación Facebook como leída'), 'version': '2.6.6'},
        'facebook:conversation-assign-contact':
            {'descripcion': _('Asignar contacto a conversación Facebook'), 'version': '2.6.6'},
        'facebook:conversation-attend-chat':
            {'descripcion': _('Atender conversación Facebook'), 'version': '2.6.6'},
        'facebook:conversation-close-conversation':
            {'descripcion': _('Cerrar conversación Facebook'), 'version': '2.6.6'},
        'facebook:conversation-messages':
            {'descripcion': _('Mensajes de una conversación Facebook'), 'version': '2.6.6'},
        'facebook:conversation-send-message-attachment':
            {'descripcion': _('Enviar adjunto en conversación Facebook'), 'version': '2.6.6'},
        'facebook:conversation-send-message-template':
            {'descripcion': _('Enviar plantilla en conversación Facebook'), 'version': '2.6.6'},
        'facebook:conversation-send-message-text':
            {'descripcion': _('Enviar texto en conversación Facebook'), 'version': '2.6.6'},
        'facebook:conversation-detail':
            {'descripcion': _('Detalle de conversación Facebook'), 'version': '2.6.6'},
        'facebook:disposition-list':
            {'descripcion': _('Calificar conversación Facebook'), 'version': '2.6.6'},
        'facebook:disposition-options':
            {'descripcion': _('Opciones de calificación de conversación Facebook'),
             'version': '2.6.6'},
        'facebook:disposition-detail':
            {'descripcion': _('Detalle de calificación de conversación Facebook'),
             'version': '2.6.6'},
        'facebook:disposition-history':
            {'descripcion': _('Historial de calificaciones de conversación Facebook'),
             'version': '2.6.6'},
        'facebook:page-configuration-list':
            {'descripcion': _('Lista de páginas de Facebook'), 'version': '2.6.6'},
        'facebook:page-configuration-detail':
            {'descripcion': _('Detalle de página de Facebook'), 'version': '2.6.6'},
        'facebook:campaign-list':
            {'descripcion': _('Campañas disponibles para páginas de Facebook'), 'version': '2.6.6'},
        'facebook:templates-messenger-list':
            {'descripcion': _('Lista de plantillas Messenger'), 'version': '2.6.6'},
        'facebook:templates-messenger-detail':
            {'descripcion': _('Detalle de plantilla Messenger'), 'version': '2.6.6'},
        'facebook:templates-group-list':
            {'descripcion': _('Lista de grupos de plantillas Messenger'), 'version': '2.6.6'},
        'facebook:templates-group-detail':
            {'descripcion': _('Detalle de grupo de plantillas Messenger'), 'version': '2.6.6'},
    }
