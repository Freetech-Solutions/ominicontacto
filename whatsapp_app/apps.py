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

from django.utils.translation import gettext_lazy as _
from django.apps import AppConfig


class WhatsappAppConfig(AppConfig):
    name = 'whatsapp_app'

    def configuraciones_de_permisos(self):
        return [
            {'nombre': 'whatsapp_providers_configuration',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'whatsapp_lines_configuration',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'message_templates_configuration',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'whatsapp_message_template_groups',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'proveedor-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'proveedor-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'linea-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'linea-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'destino-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'plantilla-mensaje-list',
             'roles': ['Administrador', 'Gerente', 'Agente', 'Supervisor']},
            {'nombre': 'plantilla-mensaje-detail',
             'roles': ['Administrador', 'Gerente', 'Agente', 'Supervisor']},
            {'nombre': 'template-whatsapp-list',
             'roles': ['Administrador', 'Gerente', 'Agente', 'Supervisor']},
            {'nombre': 'template-whatsapp-sincronizar-templates',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'template-whatsapp-status-change',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'campana-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Agente']},
            {'nombre': 'grupo-plantilla-whatsapp-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'grupo-plantilla-whatsapp-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'configuracion-whatsapp-campana-list',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'configuracion-whatsapp-campana-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'whatsapp_reports',
             'roles': ['Administrador', 'Gerente', 'Supervisor']},
            {'nombre': 'conversacion-list',
             'roles': ['Agente']},
            {'nombre': 'conversacion-agent-chats-lists',
             'roles': ['Agente']},
            {'nombre': 'conversacion-filter-chats',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Agente']},  # TODO: Agente la usa?
            {'nombre': 'conversacion-detail',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Agente']},
            {'nombre': 'conversacion-attend-chat',
             'roles': ['Agente']},
            {'nombre': 'conversacion-messages',
             'roles': ['Agente']},
            {'nombre': 'conversacion-reactive-expired-conversation',
             'roles': ['Agente']},
            {'nombre': 'conversacion-send-message-attachment',
             'roles': ['Agente']},
            {'nombre': 'conversacion-send-message-text',
             'roles': ['Agente']},
            {'nombre': 'conversacion-send-message-template',
             'roles': ['Agente']},
            {'nombre': 'conversacion-send-message-whatsapp-template',
             'roles': ['Agente']},
            {'nombre': 'whatsapp:transfer-agents',
             'roles': ['Agente']},
            {'nombre': 'whatsapp:transfer-to-agent',
             'roles': ['Agente']},
            {'nombre': 'whatsapp:transfer-campaigns',
             'roles': ['Agente']},
            {'nombre': 'whatsapp:transfer-to-campaign',
             'roles': ['Agente']},
            {'nombre': 'conversacion-assign-contact',
             'roles': ['Agente']},
            {'nombre': 'contacto-search',
             'roles': ['Agente']},
            {'nombre': 'contacto-list',
             'roles': ['Agente']},
            {'nombre': 'contacto-detail',
             'roles': ['Agente']},
            {'nombre': 'contacto-create-contact-from-conversation',
             'roles': ['Agente']},
            {'nombre': 'contacto-db-fields',
             'roles': ['Agente']},
            {'nombre': 'calificacion-list',
             'roles': ['Agente']},
            {'nombre': 'calificacion-options',
             'roles': ['Agente']},
            {'nombre': 'calificacion-detail',
             'roles': ['Agente']},
            {'nombre': 'calificacion-history',
             'roles': ['Agente']},
            {'nombre': 'template-list',
             'roles': ['Agente']},
            {'nombre': 'conversacion-mark-as-read',
             'roles': ['Agente']},
            {'nombre': 'conversacion-send-initing-conversation',
             'roles': ['Agente']},
            {'nombre': 'template-whatsapp-detail',
             'roles': ['Administrador', 'Gerente', 'Agente', 'Supervisor']},
        ]

    informacion_de_permisos = {
        'conversacion-mark-as-read':
            {'descripcion': _('conversacion-mark-as-read'), 'version': '2.6.6'},
        'conversacion-send-initing-conversation':
            {'descripcion': _('conversacion-send-initing-conversation'), 'version': '2.6.6'},
        'template-whatsapp-detail':
            {'descripcion': _('template-whatsapp-detail'), 'version': '2.6.6'},
        'whatsapp_providers_configuration':
            {'descripcion': _('whatsapp_providers_configuration'),
             'version': '1.26.0'},
        'whatsapp_lines_configuration':
            {'descripcion': _('whatsapp_lines_configuration'),
             'version': '1.26.0'},
        'message_templates_configuration':
            {'descripcion': _('message_templates_configuration'),
             'version': '1.26.0'},
        'whatsapp_message_template_groups':
            {'descripcion': _('whatsapp_message_template_groups'),
             'version': '1.26.0'},
        'proveedor-list':
            {'descripcion': _('proveedor-list'),
             'version': '1.26.0'},
        'proveedor-detail':
            {'descripcion': _('proveedor-detail'),
             'version': '1.26.0'},
        'linea-list':
            {'descripcion': _('linea-list'),
             'version': '1.26.0'},
        'linea-detail':
            {'descripcion': _('linea-detail'),
             'version': '1.26.0'},
        'destino-list':
            {'descripcion': _('destino-list'),
             'version': '1.26.0'},
        'plantilla-mensaje-list':
            {'descripcion': _('plantilla-mensaje-list'),
             'version': '1.26.0'},
        'plantilla-mensaje-detail':
            {'descripcion': _('plantilla-mensaje-detail'),
             'version': '1.26.0'},
        'template-whatsapp-list':
            {'descripcion': _('template-whatsapp-list'),
             'version': '1.26.0'},
        'template-whatsapp-sincronizar-templates':
            {'descripcion': _('template-whatsapp-sincronizar-templates'),
             'version': '1.26.0'},
        'template-whatsapp-status-change':
            {'descripcion': _('template-whatsapp-status-change'),
             'version': '1.26.0'},
        'campana-list':
            {'descripcion': _('campana-list'),
             'version': '1.26.0'},
        'grupo-plantilla-whatsapp-list':
            {'descripcion': _('grupo-plantilla-whatsapp-listp'),
             'version': '1.26.0'},
        'grupo-plantilla-whatsapp-detail':
            {'descripcion': _('grupo-plantilla-whatsapp-detail'),
             'version': '1.26.0'},
        'configuracion-whatsapp-campana-list':
            {'descripcion': _('configuracion-whatsapp-campana-list'),
             'version': '1.26.0'},
        'configuracion-whatsapp-campana-detail':
            {'descripcion': _('configuracion-whatsapp-campana-detai'),
             'version': '1.26.0'},
        'conversacion-list':
            {'descripcion': _('conversacion-list'),
             'version': '1.26.0'},
        'conversacion-filter-chats':
            {'descripcion': _('conversacion-filter-chats'),
             'version': '1.26.0'},
        'conversacion-detail':
            {'descripcion': _('conversacion-detail'),
             'version': '1.26.0'},
        'conversacion-agent-chats-lists':
            {'descripcion': _('conversacion-agent-chats-lists'),
             'version': '1.26.0'},
        'conversacion-attend-chat':
            {'descripcion': _('conversacion-attend-chat'),
             'version': '1.26.0'},
        'conversacion-messages':
            {'descripcion': _('conversacion-messages'),
             'version': '1.26.0'},
        'conversacion-reactive-expired-conversation':
            {'descripcion': _('conversacion-reactive-expired-conversation'),
             'version': '1.26.0'},
        'conversacion-send-message-attachment':
            {'descripcion': _('conversacion-send-message-attachment'),
             'version': '1.26.0'},
        'conversacion-send-message-text':
            {'descripcion': _('conversacion-send-message-text'),
             'version': '1.26.0'},
        'conversacion-send-message-template':
            {'descripcion': _('conversacion-send-message-template'),
             'version': '1.26.0'},
        'conversacion-send-message-whatsapp-template':
            {'descripcion': _('conversacion-send-message-whatsapp-template'),
             'version': '1.26.0'},
        'whatsapp:transfer-to-agent':
            {'descripcion': _('Transfiere una conversación WhatsApp a un agente'),
             'version': '2.6.6'},
        'whatsapp:transfer-agents':
            {'descripcion': _('Agentes a los que transferir una conversación WhatsApp'),
             'version': '2.6.6'},
        'whatsapp:transfer-to-campaign':
            {'descripcion': _('Transfiere una conversación WhatsApp a una campaña'),
             'version': '2.6.6'},
        'whatsapp:transfer-campaigns':
            {'descripcion': _('Campañas a las que transferir una conversación WhatsApp'),
             'version': '2.6.6'},
        'conversacion-assign-contact':
            {'descripcion': _('conversacion-assign-contact'),
             'version': '1.26.0'},
        'contacto-search':
            {'descripcion': _('contacto-search'),
             'version': '1.26.0'},
        'contacto-list':
            {'descripcion': _('contacto-list'),
             'version': '1.26.0'},
        'contacto-detail':
            {'descripcion': _('contacto-detail'),
             'version': '1.26.0'},
        'contacto-create-contact-from-conversation':
            {'descripcion': _('contacto-create-contact-from-conversation'),
             'version': '1.26.0'},
        'contacto-db-fields':
            {'descripcion': _('contacto-db-fields'),
             'version': '1.26.0'},
        'calificacion-list':
            {'descripcion': _('calificacion-list'),
             'version': '1.26.0'},
        'calificacion-options':
            {'descripcion': _('calificacion-options'),
             'version': '1.26.0'},
        'calificacion-detail':
            {'descripcion': _('calificacion-detail'),
             'version': '1.26.0'},
        'calificacion-history':
            {'descripcion': _('calificacion-history'),
             'version': '1.26.0'},
        'template-list':
            {'descripcion': _('template-list'),
             'version': '1.26.0'},
        'whatsapp_reports':
            {'descripcion': _('whatsapp_reports'),
             'version': '1.26.0'},
    }
