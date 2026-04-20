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

from django.urls import path, re_path
from django.contrib.auth.decorators import login_required
from django.conf import settings

from reportes_app import views_reportes_agentes
from reportes_app.views import (
    ReporteLlamadasFormView, ExportarReporteLlamadasFormView,
    ExportarZipReportesLlamadasFormView,
    ReporteDeResultadosView,
    AgentsActivityV2ReportView,
    AgenteReporteGraficoView)
from reportes_app import (
    views_campanas_preview_reportes,
    views_campanas_dialer_reportes,
    views_reportes,
)
from api_app.views.reports_centro_contacto import ReporteCentroContactoFormView
from reportes_app.views_reportes import (
    DescargarCSVCanalidadesCentroContactoView,
    DescargarCSVCanalidadesEgresosCentroContactoView,
    DescargarCSVCanalidadesPorHoraCentroContactoView,
    DescargarCSVCanalidadesPorHoraEgresosCentroContactoView,
    DescargarCSVCanalidadesPorDiaCentroContactoView,
    DescargarCSVCanalidadesPorDiaEgresosCentroContactoView,
    DescargarCSVCanalidadesPorMesCentroContactoView,
    DescargarCSVCanalidadesPorMesEgresosCentroContactoView,
    DescargarCSVLlamadasAtendidasCentroContactoView,
    DescargarCSVLlamadasAtendidasEgresosCentroContactoView,
    DescargarCSVLlamadasNoAtendidasCentroContactoView,
    DescargarCSVLlamadasNoAtendidasEgresosCentroContactoView,
    DescargarCSVLlamadasVozCentroContactoView,
    DescargarCSVLlamadasVozEgresosCentroContactoView,
    DescargarCSVLlamadasPorHoraCentroContactoView,
    DescargarCSVLlamadasPorHoraEgresosCentroContactoView,
    DescargarCSVLlamadasPorDiaCentroContactoView,
    DescargarCSVLlamadasPorDiaEgresosCentroContactoView,
    DescargarCSVLlamadasPorMesCentroContactoView,
    DescargarCSVLlamadasPorMesEgresosCentroContactoView,
    DescargarCSVConversacionesRespondidasCentroContactoView,
    DescargarCSVConversacionesRespondidasEgresosCentroContactoView,
    DescargarCSVConversacionesNoRespondidasCentroContactoView,
    DescargarCSVConversacionesNoRespondidasEgresosCentroContactoView,
    DescargarCSVWhatsappMensajesPorHoraCentroContactoView,
    DescargarCSVWhatsappMensajesPorHoraEgresosCentroContactoView,
    DescargarCSVWhatsappMensajesPorCampanaCentroContactoView,
    DescargarCSVWhatsappMensajesPorCampanaEgresosCentroContactoView,
    DescargarCSVWhatsappMensajesPorDiaCentroContactoView,
    DescargarCSVWhatsappMensajesPorDiaEgresosCentroContactoView,
    DescargarCSVWhatsappMensajesPorMesCentroContactoView,
    DescargarCSVWhatsappMensajesPorMesEgresosCentroContactoView,
    DescargarCSVAgentsActivityV2ListadoView,
)
from facebook_meta_app import views as facebook_views
from whatsapp_app import views as whatsapp_views

urlpatterns = [
    # ==========================================================================
    # Reportes generales agentes
    # ==========================================================================
]
# Ocultar reportes_agentes_tiempos cuando OML_DIALER_ENGINE=omnidialer
if not (hasattr(settings, 'OML_DIALER_ENGINE') and settings.OML_DIALER_ENGINE == 'omnidialer'):
    urlpatterns.append(
        path('reportes/agentes_tiempos/',
             login_required(
                 views_reportes_agentes.ReportesTiemposAgente.as_view()),
             name='reportes_agentes_tiempos')
    )
urlpatterns.extend([
    re_path(r'^reportes/agentes_export/(?P<tipo_reporte>[\w\-]+)/$',
            login_required(
                views_reportes_agentes.exporta_reporte_agente_llamada_view),
            name='reportes_agentes_exporta'),
    path('reportes/agente_por_fecha/',
         login_required(
             views_reportes_agentes.reporte_por_fecha_modal_agente_view),
         name='reportes_agente_por_fecha'),
    path('reportes/pausa_por_fecha/',
         login_required(
             views_reportes_agentes.reporte_por_fecha_pausa_modal_agente_view),
         name='reportes_pausa_por_fecha'),
    path('reportes/historico_llamadas_del_dia/',
         login_required(views_reportes_agentes.HistoricoDeLlamadasView.as_view()),
         name='historico_de_llamadas_de_agente',
         ),
    # ==========================================================================
    # Reportes generales llamadas
    # ==========================================================================
])
# Ocultar reporte_llamadas cuando OML_DIALER_ENGINE=omnidialer
if not (hasattr(settings, 'OML_DIALER_ENGINE') and settings.OML_DIALER_ENGINE == 'omnidialer'):
    urlpatterns.extend([
        path('reporte/llamadas/',
             login_required(ReporteLlamadasFormView.as_view()),
             name='reporte_llamadas',
             ),
        path('reporte/llamadas/exportar/',
             login_required(ExportarReporteLlamadasFormView.as_view()),
             name='csv_reporte_llamadas',
             ),
        path('reporte/llamadas/zip/',
             login_required(ExportarZipReportesLlamadasFormView.as_view()),
             name='zip_reportes_llamadas',
             ),
    ])
urlpatterns += [
    path('reporte/centro_de_contacto/',
         login_required(ReporteCentroContactoFormView.as_view()),
         name='reporte_centro_de_contacto',
         ),
    path('reporte/centro_de_contacto/exportar_canalidades_csv/<str:task_id>/',
         login_required(DescargarCSVCanalidadesCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_canalidades_csv',
         ),
    path('reporte/centro_de_contacto/exportar_canalidades_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVCanalidadesEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_canalidades_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_canalidades_por_hora_csv/<str:task_id>/',
         login_required(DescargarCSVCanalidadesPorHoraCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_canalidades_por_hora_csv',
         ),
    path('reporte/centro_de_contacto/exportar_canalidades_por_hora_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVCanalidadesPorHoraEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_canalidades_por_hora_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_canalidades_por_dia_csv/<str:task_id>/',
         login_required(DescargarCSVCanalidadesPorDiaCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_canalidades_por_dia_csv',
         ),
    path('reporte/centro_de_contacto/exportar_canalidades_por_dia_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVCanalidadesPorDiaEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_canalidades_por_dia_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_canalidades_por_mes_csv/<str:task_id>/',
         login_required(DescargarCSVCanalidadesPorMesCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_canalidades_por_mes_csv',
         ),
    path('reporte/centro_de_contacto/exportar_canalidades_por_mes_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVCanalidadesPorMesEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_canalidades_por_mes_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_atendidas_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasAtendidasCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_atendidas_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_atendidas_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasAtendidasEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_atendidas_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_no_atendidas_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasNoAtendidasCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_no_atendidas_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_no_atendidas_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasNoAtendidasEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_no_atendidas_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_voz_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasVozCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_voz_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_voz_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasVozEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_voz_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_por_hora_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasPorHoraCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_por_hora_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_por_hora_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasPorHoraEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_por_hora_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_por_dia_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasPorDiaCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_por_dia_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_por_dia_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasPorDiaEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_por_dia_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_por_mes_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasPorMesCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_por_mes_csv',
         ),
    path('reporte/centro_de_contacto/exportar_llamadas_por_mes_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVLlamadasPorMesEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_llamadas_por_mes_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_conversaciones_respondidas_csv/<str:task_id>/',
         login_required(DescargarCSVConversacionesRespondidasCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_conversaciones_respondidas_csv',
         ),
    path('reporte/centro_de_contacto/exportar_conversaciones_respondidas_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVConversacionesRespondidasEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_conversaciones_respondidas_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_conversaciones_no_respondidas_csv/<str:task_id>/',
         login_required(DescargarCSVConversacionesNoRespondidasCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_conversaciones_no_respondidas_csv',
         ),
    path('reporte/centro_de_contacto/exportar_conversaciones_no_respondidas_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVConversacionesNoRespondidasEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_conversaciones_no_respondidas_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_whatsapp_mensajes_por_hora_csv/<str:task_id>/',
         login_required(DescargarCSVWhatsappMensajesPorHoraCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_hora_csv',
         ),
    path('reporte/centro_de_contacto/exportar_whatsapp_mensajes_por_hora_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVWhatsappMensajesPorHoraEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_hora_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_whatsapp_mensajes_por_campana_csv/<str:task_id>/',
         login_required(DescargarCSVWhatsappMensajesPorCampanaCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_campana_csv',
         ),
    path('reporte/centro_de_contacto/exportar_whatsapp_mensajes_por_campana_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVWhatsappMensajesPorCampanaEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_campana_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_whatsapp_mensajes_por_dia_csv/<str:task_id>/',
         login_required(DescargarCSVWhatsappMensajesPorDiaCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_dia_csv',
         ),
    path('reporte/centro_de_contacto/exportar_whatsapp_mensajes_por_dia_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVWhatsappMensajesPorDiaEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_dia_egresos_csv',
         ),
    path('reporte/centro_de_contacto/exportar_whatsapp_mensajes_por_mes_csv/<str:task_id>/',
         login_required(DescargarCSVWhatsappMensajesPorMesCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_mes_csv',
         ),
    path('reporte/centro_de_contacto/exportar_whatsapp_mensajes_por_mes_egresos_csv/<str:task_id>/',
         login_required(DescargarCSVWhatsappMensajesPorMesEgresosCentroContactoView.as_view()),
         name='reporte_centro_de_contacto_descargar_whatsapp_mensajes_por_mes_egresos_csv',
         ),
    path('reportes/agents-activity-v2/',
         login_required(AgentsActivityV2ReportView.as_view()),
         name='reportes_agents_activity_v2',
         ),
    path('reportes/agents-activity-v2/exportar_listado_csv/<str:task_id>/',
         login_required(DescargarCSVAgentsActivityV2ListadoView.as_view()),
         name='reportes_agents_activity_v2_descargar_listado_csv',
         ),
    path('agente/<int:pk_agente>/reporte_grafico/',
         login_required(AgenteReporteGraficoView.as_view()),
         name='agente_reporte_grafico',
         ),
    # ==========================================================================
    # Reportes desde las campañas
    # ==========================================================================
    path('campana/<int:pk_campana>/reporte_calificacion/',
         login_required(
             views_reportes.CampanaReporteCalificacionListView.as_view()),
         name="campana_reporte_calificacion"),
    path('campana/<int:pk_campana>/exporta/',
         login_required(
             views_reportes.ExportaCampanaReporteCalificacionView.as_view()),
         name='exporta_campana_reporte_calificacion',
         ),
    path('campana/<int:pk_campana>/reporte_grafico/',
         login_required(
             views_reportes.CampanaReporteGraficoView.as_view()),
         name='campana_reporte_grafico',
         ),
    path('campana/<int:pk_campana>/reporte_pdf/',
         login_required(
             views_reportes.ExportaCampanaReporteGraficoPDFView.as_view()),
         name="campana_reporte_grafico_pdf"),
    path('campana/<int:pk_campana>/reporte_grafico/<int:pk_agente>/agente/',
         login_required(
             views_reportes.AgenteCampanaReporteGrafico.as_view()),
         name='campana_reporte_grafico_agente',
         ),
    path('formulario/<int:pk_campana>/exporta/',
         login_required(
             views_reportes.ExportaReporteFormularioVentaView.as_view()),
         name='exporta_reporte_calificaciones_gestion',
         ),
    path('campana/<int:pk_campana>/exporta_contactados/',
         login_required(
             views_reportes.ExportaReporteLlamadosContactadosView.as_view()),
         name='exporta_reporte_llamados_contactados',
         ),
    path('campana_dialer/<int:pk_campana>/exporta_calificados/',
         login_required(
             views_reportes.ExportaReporteCalificadosView.as_view()),
         name='exporta_reporte_calificados',
         ),
    path('campana/<int:pk_campana>/exporta/no_atendidos/',
         login_required(
             views_reportes.ExportaReporteNoAtendidosView.as_view()),
         name='exporta_reporte_no_atendidos',
         ),
    path('campana/<int:pk_campana>/exporta/calificaciones_por_agente/',
         login_required(
             views_reportes.ExportaReporteCalificacionesPorAgenteView.as_view()),
         name='exporta_reporte_calificaciones_por_agente',
         ),
    path('campana/<int:pk_campana>/exporta/interacciones_por_agente/',
         login_required(
             views_reportes.ExportaReporteInteraccionesPorAgenteView.as_view()),
         name='exporta_reporte_interacciones_por_agente',
         ),
    path('campana/<int:pk_campana>/exporta/performance_agentes/',
         login_required(
             views_reportes.ExportaReportePerformanceAgentesView.as_view()),
         name='exporta_reporte_performance_agentes',
         ),
    path('campana_preview/<int:pk>/detalle/',
         login_required(
             views_campanas_preview_reportes.CampanaPreviewDetailView.as_view()),
         name="campana_preview_detalle"),
    path('campana_preview/<int:pk>/detalle_express/',
         login_required(
             views_campanas_preview_reportes.CampanaPreviewExpressView.as_view()),
         name="campana_preview_detalle_express"),
    path('campana_dialer/detalle_servicio/',
         login_required(
             views_campanas_dialer_reportes.detalle_campana_dialer_view),
         name="campana_dialer_detalle_servicio"),
    path('campana_dialer/<int:pk_campana>/detalle/',
         login_required(
             views_campanas_dialer_reportes.CampanaDialerDetailView.as_view()),
         name='campana_dialer_detalle',
         ),
    path('reporte_de_resultados/<int:pk_campana>/',
         login_required(
             ReporteDeResultadosView.as_view()),
         name='reporte_de_resultados',
         ),
    path('campana/<int:pk_campana>/whatsapp_conversations_report/',
         login_required(
             whatsapp_views.CampaignReportConversationsListView.as_view()),
         name='campaign_whatsapp_report_conversations',
         ),
    path('campana/<int:pk_campana>/whatsapp_general_report/',
         login_required(
             whatsapp_views.GeneralReportListView.as_view()),
         name='campaign_whatsapp_report_general',
         ),
    path('campana/<int:pk_campana>/facebook_conversations_report/',
         login_required(
             facebook_views.CampaignReportConversationsListView.as_view()),
         name='campaign_facebook_report_conversations',
         ),
    path('campana/<int:pk_campana>/facebook_general_report/',
         login_required(
             facebook_views.GeneralReportListView.as_view()),
         name='campaign_facebook_report_general',
         ),
    re_path(r'^resultados_de_base_campana/(?P<pk_campana>\d+)/(?P<all_data>\d+)/$',
            login_required(
                views_reportes.ExportaReporteResultadosDeBaseView.as_view()),
            name='exporta_reporte_resultados_de_base_contactaciones',
            ),
]
