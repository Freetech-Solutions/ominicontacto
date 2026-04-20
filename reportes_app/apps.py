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

from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.apps import AppConfig
from django.conf import settings


class ReportesAppConfig(AppConfig):
    name = 'reportes_app'

    def supervision_menu_items(self, request, permissions):
        items = []
        # Ocultar reporte_llamadas cuando OML_DIALER_ENGINE=omnidialer
        if ('reporte_llamadas' in permissions and
                not (hasattr(settings, 'OML_DIALER_ENGINE') and settings.OML_DIALER_ENGINE == 'omnidialer')):
            items.append({
                'label': _('Llamadas'),
                'url': reverse('reporte_llamadas'),
            })
        # Ocultar reportes_agentes_tiempos cuando OML_DIALER_ENGINE=omnidialer
        if ('reportes_agentes_tiempos' in permissions and
                not (hasattr(settings, 'OML_DIALER_ENGINE') and settings.OML_DIALER_ENGINE == 'omnidialer')):
            items.append({
                'label': _('Agentes'),
                'url': reverse('reportes_agentes_tiempos'),
            })
        if 'reporte_centro_de_contacto' in permissions:
            items.append({
                'label': _('Interacciones'),
                'url': reverse('reporte_centro_de_contacto'),
            })
        if 'reportes_agents_activity_v2' in permissions:
            items.append({
                'label': _('Agentes'),
                'url': reverse('reportes_agents_activity_v2'),
            })

        if items:
            return [{
                'order': 700,
                'label': _('Reportes'),
                'icon': 'fas fa-chart-line',
                'id': 'menuReports',
                'children': items
            }]
        return None

    def configuraciones_de_permisos(self):
        return [
            {'nombre': 'reportes_agentes_tiempos',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reportes_agentes_exporta',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reportes_agente_por_fecha',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reportes_pausa_por_fecha',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'historico_de_llamadas_de_agente',
             'roles': ['Agente', ]},
            {'nombre': 'reporte_llamadas',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'csv_reporte_llamadas',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'zip_reportes_llamadas',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campana_reporte_calificacion',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'exporta_campana_reporte_calificacion',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campana_reporte_grafico',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campana_reporte_grafico_pdf',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campana_reporte_grafico_agente',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'exporta_reporte_calificaciones_gestion',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'exporta_reporte_llamados_contactados',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'exporta_reporte_calificados',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'exporta_reporte_no_atendidos',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'exporta_reporte_calificaciones_por_agente',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campana_preview_detalle',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campana_preview_detalle_express',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campana_dialer_detalle_servicio',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campana_dialer_detalle',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_de_resultados',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'exporta_reporte_resultados_de_base_contactaciones',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campaign_whatsapp_report_conversations',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'campaign_whatsapp_report_general',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_canalidades_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_canalidades_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_canalidades_por_hora_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_canalidades_por_hora_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_canalidades_por_dia_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_canalidades_por_dia_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_canalidades_por_mes_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_canalidades_por_mes_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_atendidas_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_atendidas_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_no_atendidas_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_no_atendidas_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_voz_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_voz_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_por_hora_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_por_hora_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_por_dia_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_por_dia_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_por_mes_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_llamadas_por_mes_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_conversaciones_respondidas_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_conversaciones_respondidas_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_conversaciones_no_respondidas_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_conversaciones_no_respondidas_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_hora_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_hora_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_campana_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_campana_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_dia_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_dia_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_mes_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_mes_egresos_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reportes_agents_activity_v2',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'reportes_agents_activity_v2_descargar_listado_csv',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
            {'nombre': 'agente_reporte_grafico',
             'roles': ['Administrador', 'Gerente', 'Supervisor', 'Referente', ]},
        ]

    informacion_de_permisos = {
        'reportes_agentes_tiempos':
            {'descripcion': _('Reportes de tiempos de agentes (sesión, pausa, llamada, etc...)'),
             'version': '1.7.0'},
        'reportes_agentes_exporta':
            {'descripcion': _('Exporta reportes de agentes.'), 'version': '1.7.0'},
        'reportes_agente_por_fecha':
            {'descripcion': _('Reporte de tiempos de agente para ventana modal.'),
             'version': '1.7.0'},
        'reportes_pausa_por_fecha':
            {'descripcion': _('Reportes de pausas de agente para ventana modal.'),
             'version': '1.7.0'},
        'historico_de_llamadas_de_agente':
            {'descripcion': _('Historico de llamadas para mostrar en la consola de Agente'),
             'version': '1.7.0'},
        'reporte_llamadas':
            {'descripcion': _('Reporte de Llamadas'), 'version': '1.7.0'},
        'csv_reporte_llamadas':
            {'descripcion': _('Descarga csv de reporte de llamadas'), 'version': '1.7.0'},
        'zip_reportes_llamadas':
            {'descripcion': _('Descarga .zip de reporte de llamadas'), 'version': '1.7.0'},
        'campana_reporte_calificacion':
            {'descripcion': _('Reporte de calificaciones de campaña'), 'version': '1.7.0'},
        'exporta_campana_reporte_calificacion':
            {'descripcion': _('Descargar Reporte de calificaciones de campaña'),
             'version': '1.7.0'},
        'campana_reporte_grafico':
            {'descripcion': _('Reporte Grafico de campaña'), 'version': '1.7.0'},
        'campana_reporte_grafico_pdf':
            {'descripcion': _('Descargar Reporte Grafico de campaña'), 'version': '1.7.0'},
        'campana_reporte_grafico_agente':
            {'descripcion': _('Reporte Grafico de Agente en Campana'), 'version': '1.7.0'},
        'exporta_reporte_calificaciones_gestion':
            {'descripcion': _('Reporte de gestiones de un Agente'), 'version': '1.7.0'},
        'exporta_reporte_llamados_contactados':
            {'descripcion': _('Descargar Reporte de llamados contactados de una campaña'),
             'version': '1.7.0'},
        'exporta_reporte_calificados':
            {'descripcion': _('Descargar Reporte de llamados calificados de una campaña'),
             'version': '1.7.0'},
        'exporta_reporte_no_atendidos':
            {'descripcion': _('Descargar Reporte de llamados no atendidos de una campaña'),
             'version': '1.7.0'},
        'exporta_reporte_calificaciones_por_agente':
            {'descripcion': _('Descargar Reporte de calificaciones por agente de una campaña'),
             'version': '1.19.0'},
        'campana_preview_detalle':
            {'descripcion': _('Detalle del estado de una campaña Preview'), 'version': '1.7.0'},
        'campana_preview_detalle_express':
            {'descripcion': _('Detalle del estado de una campaña Preview (para ventana modal)'),
             'version': '1.7.0'},
        'campana_dialer_detalle_servicio':
            {'descripcion': _('Detalle del estado de una campaña Dialer'), 'version': '1.7.0'},
        'campana_dialer_detalle':
            {'descripcion': _('Detalle del estado de una campaña Dialer (para ventana modal)'),
             'version': '1.7.0'},
        'reporte_de_resultados':
            {'descripcion': _('Reporte de resultado de contactaciones en una Campaña'),
             'version': '1.19.0'},
        'exporta_reporte_resultados_de_base_contactaciones':
            {'descripcion': _('Descargar reporte de resultados en una Campaña'),
             'version': '1.19.0'},
        'campaign_whatsapp_report_conversations':
            {'descripcion': _('Vista de reporte de conversaciones de Whatsapp para Campaña'),
             'version': '1.19.0'},
        'campaign_whatsapp_report_general':
            {'descripcion': _('Vista de reporte general de Whatsapp para una Campaña'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto':
            {'descripcion': _('Reporte de Nivel de Servicio (Service Level) del Centro de Contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_canalidades_csv':
            {'descripcion': _('Descargar CSV de Canalidades por campaña del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_canalidades_egresos_csv':
            {'descripcion': _('Descargar CSV de Canalidades por campaña (Egresos) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_canalidades_por_hora_csv':
            {'descripcion': _('Descargar CSV de Canalidades por hora del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_canalidades_por_hora_egresos_csv':
            {'descripcion': _('Descargar CSV de Canalidades por hora (Egresos) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_canalidades_por_dia_csv':
            {'descripcion': _('Descargar CSV de Canalidades por día del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_canalidades_por_dia_egresos_csv':
            {'descripcion': _('Descargar CSV de Canalidades por día (Egresos) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_canalidades_por_mes_csv':
            {'descripcion': _('Descargar CSV de Canalidades por mes del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_canalidades_por_mes_egresos_csv':
            {'descripcion': _('Descargar CSV de Canalidades por mes (Egresos) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_atendidas_csv':
            {'descripcion': _('Descargar CSV de Listado de llamadas atendidas del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_atendidas_egresos_csv':
            {'descripcion': _('Descargar CSV de Listado de llamadas atendidas (Egresos) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_no_atendidas_csv':
            {'descripcion': _('Descargar CSV de Listado de llamadas no atendidas del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_no_atendidas_egresos_csv':
            {'descripcion': _('Descargar CSV de Listado de llamadas no atendidas (Egresos) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_voz_csv':
            {'descripcion': _('Descargar CSV de Llamadas de voz por campaña del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_voz_egresos_csv':
            {'descripcion': _('Descargar CSV de Llamadas de voz por campaña (Egresos) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_por_hora_csv':
            {'descripcion': _('Descargar CSV de Llamadas por hora de día (Voz) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_por_hora_egresos_csv':
            {'descripcion': _('Descargar CSV de Llamadas por hora de día (Egresos) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_por_dia_csv':
            {'descripcion': _('Descargar CSV de Llamadas por día (Voz) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_por_dia_egresos_csv':
            {'descripcion': _('Descargar CSV de Llamadas por día (Egresos/Voz) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_por_mes_csv':
            {'descripcion': _('Descargar CSV de Llamadas por mes (Voz) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_llamadas_por_mes_egresos_csv':
            {'descripcion': _('Descargar CSV de Llamadas por mes (Egresos/Voz) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_conversaciones_respondidas_csv':
            {'descripcion': _('Descargar CSV de Conversaciones Respondidas (WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_conversaciones_respondidas_egresos_csv':
            {'descripcion': _('Descargar CSV de Conversaciones Respondidas (Egresos/WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_conversaciones_no_respondidas_csv':
            {'descripcion': _('Descargar CSV de Conversaciones no respondidas (WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_conversaciones_no_respondidas_egresos_csv':
            {'descripcion': _('Descargar CSV de Conversaciones no respondidas (Egresos/WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_hora_csv':
            {'descripcion': _('Descargar CSV de Mensajes por hora de día (WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_hora_egresos_csv':
            {'descripcion': _('Descargar CSV de Mensajes por hora (Egresos/WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_campana_csv':
            {'descripcion': _('Descargar CSV de Mensajes por campaña del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_campana_egresos_csv':
            {'descripcion': _('Descargar CSV de Mensajes por campaña (Egresos/WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_dia_csv':
            {'descripcion': _('Descargar CSV de Mensajes por día (WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_dia_egresos_csv':
            {'descripcion': _('Descargar CSV de Mensajes por día (Egresos/WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_mes_csv':
            {'descripcion': _('Descargar CSV de Mensajes por mes (WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_mes_egresos_csv':
            {'descripcion': _('Descargar CSV de Mensajes por mes (Egresos/WhatsApp) del reporte centro de contacto'),
             'version': '1.19.0'},
        'reportes_agents_activity_v2':
            {'descripcion': _('KPIs de actividad de agentes (sesión, ready, pausa, ACW)'),
             'version': '1.19.0'},
        'reportes_agents_activity_v2_descargar_listado_csv':
            {'descripcion': _('Descargar CSV de la tabla Listado del reporte de actividad de agentes (v2)'),
             'version': '1.19.0'},
        'agente_reporte_grafico':
            {'descripcion': _('Vista gráfica de KPIs por agente en rango de tiempo'),
             'version': '1.19.0'},
    }
