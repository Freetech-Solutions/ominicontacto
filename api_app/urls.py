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

from api_app.views.usuarios import ListadoAgentes, ListadoGrupos

from django.urls import include, re_path, path
from rest_framework import routers
from django.contrib.auth.decorators import login_required

from api_app.views.base import login
from api_app.views.base_de_contactos import (
    CampaingsOnDB, ContactoDeCampanaCreateView, ContactoCampanaDetalleView,
    CampaignDatabaseMetadataView, CamposDireccionView,
    BaseDatosContactoCreateView, ContactoCreateView, )
from api_app.views.administrador import (
    AgentesActivosGrupoViewSet, CrearRolView, EliminarRolView, ActualizarPermisosDeRolView,
    SubirBaseContactosView, EnviarKeyRegistro)
from api_app.views.agenda_contacto import AgendaContactoCreateAPIView
from api_app.views.supervisor import (
    SupervisorCampanasActivasViewSet, AgentesStatusAPIView, UsuariosAgentesAPIView,
    InteraccionDeSupervisorSobreAgenteView,
    LlamadasDeCampanaView, CalificacionesDeCampanaView,
    ReasignarAgendaContactoView, DataAgendaContactoView,
    ExportarCSVContactados, ExportarCSVCalificados, ExportarCSVNoAtendidos,
    ExportarCSVCalificacionesPorAgente, ExportarCSVInteraccionesPorAgente,
    ExportarCSVPerformanceAgentes,
    StatusCampanasEntrantesView, ContactosAsignadosCampanaPreviewView,
    ExportarCSVCalificacionesCampana, ExportarCSVFormularioGestionCampana,
    ExportarCSVResultadosBaseContactados, DashboardSupervision, AuditSupervisor,
    EnviarMensajeAgentesView)
from api_app.views.campaigns.add_agents_to_campaign import (
    AgentesCampana, ActualizaAgentesCampana, ActualizarCampanasDeAgente, AgentesActivos)
from api_app.views.pause_set import (
    ConjuntoDePausaCreate, ConjuntoDePausaDelete, ConjuntoDePausaDetalle,
    ConjuntoDePausaList, ConjuntoDePausaUpdate, ConfiguracionDePausaCreate,
    ConfiguracionDePausaDelete, ConfiguracionDePausaUpdate, Pausas)
from api_app.views.external_site import (
    SitioExternoCreate, SitioExternoDelete, SitioExternoDesocultar,
    SitioExternoDetalle, SitioExternoList, SitioExternoOcultar,
    SitioExternoUpdate)
from api_app.views.external_site_authentication import (
    ExternalSiteAuthenticationCreate,
    ExternalSiteAuthenticationTest,
    ExternalSiteAuthenticationDelete,
    ExternalSiteAuthenticationDetail,
    ExternalSiteAuthenticationList,
    ExternalSiteAuthenticationUpdate)
from api_app.views.call_disposition import (
    CalificacionCreate, CalificacionDelete, CalificacionDetail,
    CalificacionList, CalificacionUpdate)
from api_app.views.external_system import (
    AgentesSistemaExternoList, SistemaExternoCreate, SistemaExternoDetail,
    SistemaExternoList, SistemaExternoUpdate)
from api_app.views.form import (
    FormCreate, FormDelete, FormDetail,
    FormHide, FormList, FormShow, FormUpdate)
from api_app.views.pause import (
    PauseCreate, PauseDelete, PauseDetail, PauseList, PauseReactivate,
    PauseUpdate)
from api_app.views.inbound_route import (
    InboundRouteCreate, InboundRouteDelete, InboundRouteDestinations,
    InboundRouteDetail, InboundRouteList, InboundRouteUpdate)
from api_app.views.outbound_route import (
    OutboundRouteCreate, OutboundRouteDelete, OutboundRouteList,
    OutboundRouteDetail, OutboundRouteOrphanTrunks, OutboundRouteReorder,
    OutboundRouteSIPTrunksList, OutboundRouteUpdate)
from api_app.views.group_of_hour import (
    GroupOfHourCreate, GroupOfHourDelete, GroupOfHourList,
    GroupOfHourDetail, GroupOfHourUpdate)
from api_app.views.ivr import (
    IVRAudioOptions, IVRCreate, IVRDelete, IVRDestinationTypes, IVRList,
    IVRDetail, IVRUpdate)
from api_app.views.register_server import (
    RegisterServerCreate,
    RegisterServerList)
from api_app.views.agente import (
    ObtenerCredencialesSIPAgenteView,
    OpcionesCalificacionViewSet, ApiCalificacionClienteView, ApiCalificacionClienteCreateView,
    API_ObtenerContactosCampanaView, Click2CallView, AgentLogoutView, HangUpCallView,
    AgentLoginAsterisk, AgentLogoutAsterisk, AgentPauseAsterisk, AgentUnpauseAsterisk,
    AgentReadyAsterisk, SetEstadoRevisionAuditoria, ApiStatusCalificacionLlamada,
    ApiEventoHold, AgentRingingAsterisk, AgentRejectCallAsterisk, Click2CallOutsideCampaign,
    ApiAgentesParaTransferencia, AgentDisabledAsterisk, NotifyEndTransferredCall,
    ApiConsultativeConferHold, AgentPresenceHeartbeatView,
)
from api_app.views.grabaciones import (
    ObtenerArchivoGrabacionView, ObtenerArchivosGrabacionView, ObtenerUrlGrabacionView,
    ProcessSpeechAnalisisTaskView
)
from api_app.views.auditoria import ObtenerArchivoAuditoriaView
from api_app.views.audios import ListadoAudiosView
from api_app.views.wombat_dialer import (ReiniciarWombat, WombatState, WombatStart, WombatStop,
                                         SupervisionWombatDialerStats)
from api_app.views.system import AsteriskQueuesData, NotifyAttendedMultinumCall, NotifyCallBlocked, HealthCheckView

from api_app.views.destino_entrante import DestinoEntranteView, DestinoEntranteTiposView
from api_app.views.logging import TransferenciaAEncuestaLogCreateView
from api_app.views.reports import (
    AgentStatusView, AgentStatusListView, CallStatusView, CampaignStatsReportView)
from api_app.views.reports_agent_activity_v2 import (
    AgentsActivityV2ReportView,
    ExportarCSVAgentsActivityV2Listado,
)
from api_app.views.reports_agent_kpis_v2 import AgentKpisV2ReportView
from api_app.views.reports_centro_contacto import (
    GetOmnichannelShareDataView,
    ReporteCentroContactoAPIView,
    ExportarCSVCanalidadesCentroContacto,
    ExportarCSVCanalidadesEgresosCentroContacto,
    ExportarCSVCanalidadesPorHoraCentroContacto,
    ExportarCSVCanalidadesPorHoraEgresosCentroContacto,
    ExportarCSVCanalidadesPorDiaCentroContacto,
    ExportarCSVCanalidadesPorDiaEgresosCentroContacto,
    ExportarCSVCanalidadesPorMesCentroContacto,
    ExportarCSVCanalidadesPorMesEgresosCentroContacto,
    ExportarCSVLlamadasAtendidasCentroContacto,
    ExportarCSVLlamadasAtendidasEgresosCentroContacto,
    InteractionTransfersPorLlamadaAPIView,
    ExportarCSVLlamadasNoAtendidasCentroContacto,
    ExportarCSVLlamadasNoAtendidasEgresosCentroContacto,
    ExportarCSVLlamadasVozCentroContacto,
    ExportarCSVLlamadasVozEgresosCentroContacto,
    ExportarCSVLlamadasPorHoraCentroContacto,
    ExportarCSVLlamadasPorHoraEgresosCentroContacto,
    ExportarCSVLlamadasPorDiaCentroContacto,
    ExportarCSVLlamadasPorDiaEgresosCentroContacto,
    ExportarCSVLlamadasPorMesCentroContacto,
    ExportarCSVLlamadasPorMesEgresosCentroContacto,
    ExportarCSVConversacionesRespondidasCentroContacto,
    ExportarCSVConversacionesRespondidasEgresosCentroContacto,
    ExportarCSVConversacionesNoRespondidasCentroContacto,
    ExportarCSVConversacionesNoRespondidasEgresosCentroContacto,
    ExportarCSVWhatsappMensajesPorHoraCentroContacto,
    ExportarCSVWhatsappMensajesPorHoraEgresosCentroContacto,
    ExportarCSVWhatsappMensajesPorCampanaCentroContacto,
    ExportarCSVWhatsappMensajesPorCampanaEgresosCentroContacto,
    ExportarCSVWhatsappMensajesPorDiaCentroContacto,
    ExportarCSVWhatsappMensajesPorDiaEgresosCentroContacto,
    ExportarCSVWhatsappMensajesPorMesCentroContacto,
    ExportarCSVWhatsappMensajesPorMesEgresosCentroContacto,
)
from api_app.views.audios_asterisk import AudiosAsteriskListView
from api_app.views.transfer import (
    TransferBlindAgentView, TransferBlindEndpointView,
    TransferBlindCampaignView, TransferBlindCampaignAgentView,
    Transfer3WayView, HangupLegView, SpyChannelView, VoicebotHangupView, HoldCallView, ThreeWayConfView,
    TransferConsultStartView, TransferConsultCompleteView, TransferConsultCancelView
)
from api_app.views.verloop import VerloopWebhookView
from api_app.views.voicebot import VoicebotWebhookView


router = routers.DefaultRouter()

#####################################################
# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.

# ###########  ADMINISTRADOR  ############ #
router.register(
    r'api/v1/grupo/(?P<pk_grupo>\d+)/agentes_activos', AgentesActivosGrupoViewSet,
    basename='api_agentes_activos_de_grupo')


# ###########     AGENTE      ############ #
router.register(
    r'api/v1/campaign/(?P<campaign>\w+)/dispositionOptions/(?P<externalSystem>\w+)',
    OpcionesCalificacionViewSet, basename='api_campana_opciones_calificacion')
router.register(
    r'api/v1/campaign/(?P<campaign>\w+)/dispositionOptions',
    OpcionesCalificacionViewSet, basename='api_campana_opciones_calificacion_intern')
router.register(r'api/v1/disposition', ApiCalificacionClienteView, basename='api_disposition')
router.register(
    r'api/v1/new_contact/disposition', ApiCalificacionClienteCreateView,
    basename='api_disposition_new_contact')


urlpatterns = [

    # ###########   TODOS/BASE    ############ #
    re_path(r'^', include(router.urls)),
    path('api/v1/login', login, name='api_login'),
    # ###########   ADMINISTRADOR    ############ #
    re_path(r'api/v1/permissions/new_role/$',
            CrearRolView.as_view(),
            name='api_new_role'),
    re_path(r'api/v1/permissions/delete_role/$',
            EliminarRolView.as_view(),
            name='api_delete_role'),
    re_path(r'api/v1/permissions/update_role_permissions/$',
            ActualizarPermisosDeRolView.as_view(),
            name='api_update_role_permissions'),
    re_path(r'api/v1/crear_base_contactos/$',
            SubirBaseContactosView.as_view(),
            name='api_upload_base_contactos'),
    re_path(r'api/v1/reenviar_key_registro/$',
            EnviarKeyRegistro.as_view(),
            name='reenviar_key_registro'),
    # ###########   SUPERVISOR    ############ #
    path('api/v1/supervision/campaigns/',
         SupervisorCampanasActivasViewSet.as_view(),
         name='api_campanas_de_supervisor'),
    # Verificar uso api_agentes_activos (parece haber sidousado en supervision):
    path('api/v1/supervision/agents/',
         AgentesStatusAPIView.as_view(),
         name='api_agentes_activos'),
    path('api/v1/supervision/agents_users/',
         UsuariosAgentesAPIView.as_view(),
         name='api_agents_users'),
    re_path(r'api/v1/supervision/status_campanas/entrantes/$',
            login_required(StatusCampanasEntrantesView.as_view()),
            name='api_supervision_campanas_entrantes'),
    path('api/v1/supervision/action_on_agent/<int:pk>/',
         InteraccionDeSupervisorSobreAgenteView.as_view(),
         name='api_accion_sobre_agente'),
    re_path(r'api/v1/supervision/enviar_mensaje_agentes/$',
            login_required(EnviarMensajeAgentesView.as_view()),
            name='api_enviar_mensaje_agentes'),
    re_path(r'^api_supervision/llamadas_campana/(?P<pk_campana>\d+)/$',
            LlamadasDeCampanaView.as_view(),
            name='api_supervision_llamadas_campana',
            ),
    re_path(r'^api_supervision/calificaciones_campana/(?P<pk_campana>\d+)/$',
            CalificacionesDeCampanaView.as_view(),
            name='api_supervision_calificaciones_campana',
            ),
    re_path(r'api/v1/supervision/reasignar_agenda_contacto/$',
            ReasignarAgendaContactoView.as_view(),
            name='api_reasignar_agenda_contacto'),
    re_path(r'api/v1/supervision/data_agenda_contacto/(?P<agenda_id>\d+)/$',
            DataAgendaContactoView.as_view(),
            name='api_data_agenda_contacto'),
    re_path(r'api/v1/exportar_csv_contactados/$',
            ExportarCSVContactados.as_view(),
            name='api_exportar_csv_contactados'),
    re_path(r'api/v1/exportar_csv_calificados/$',
            ExportarCSVCalificados.as_view(),
            name='api_exportar_csv_calificados'),
    re_path(r'api/v1/exportar_csv_no_atendidos/$',
            ExportarCSVNoAtendidos.as_view(),
            name='api_exportar_csv_no_atendidos'),
    re_path(r'api/v1/exportar_csv_calificaciones_por_agente/$',
            ExportarCSVCalificacionesPorAgente.as_view(),
            name='api_exportar_csv_calificaciones_por_agente'),
    re_path(r'api/v1/exportar_csv_interacciones_por_agente/$',
            ExportarCSVInteraccionesPorAgente.as_view(),
            name='api_exportar_csv_interacciones_por_agente'),
    re_path(r'api/v1/exportar_csv_performance_agentes/$',
            ExportarCSVPerformanceAgentes.as_view(),
            name='api_exportar_csv_performance_agentes'),
    re_path(r'api/v1/supervision/contactos_asignados_preview/(?P<pk_campana>\d+)/$',
            ContactosAsignadosCampanaPreviewView.as_view(),
            name='api_contactos_asignados_campana_preview'),
    re_path(r'api/v1/exportar_csv_calificaciones_campana/$',
            ExportarCSVCalificacionesCampana.as_view(),
            name='api_exportar_csv_calificaciones_campana'),
    re_path(r'api/v1/exportar_csv_formulario_gestion_campana/$',
            ExportarCSVFormularioGestionCampana.as_view(),
            name='api_exportar_csv_formulario_gestion_campana'),
    re_path(r'api/v1/exportar_csv_resultados_base_contactados/$',
            ExportarCSVResultadosBaseContactados.as_view(),
            name='api_exportar_csv_resultados_base_contactados'),
    re_path(r'api/v1/dashboard_supervision/$',
            DashboardSupervision.as_view(),
            name='api_dashboard_supervision'),
    re_path(r'api/v1/campaign/(?P<pk_campana>\d+)/agents/$',
            AgentesCampana.as_view(),
            name='api_agents_campaign'),
    path('api/v1/campaign/agents_update/',
         ActualizaAgentesCampana.as_view(),
         name='api_update_campaign_agents'),
    path('api/v1/agent/campaigns_update/',
         ActualizarCampanasDeAgente.as_view(),
         name='api_update_agent_campaigns'),
    re_path(r'api/v1/active_agents/$',
            AgentesActivos.as_view(),
            name='api_active_agents'),
    # =========================
    # Conjuntos de Pausas
    # =========================
    re_path(r'api/v1/pause_sets/pause_options/$',
            Pausas.as_view(),
            name='api_pause_set_pause_options'),
    re_path(r'api/v1/pause_sets/$',
            ConjuntoDePausaList.as_view(),
            name='api_pause_set_list'),
    re_path(r'api/v1/pause_sets/(?P<pk>\d+)/$',
            ConjuntoDePausaDetalle.as_view(),
            name='api_pause_set_detail'),
    re_path(r'api/v1/pause_sets/create/$',
            ConjuntoDePausaCreate.as_view(),
            name='api_pause_set_create'),
    re_path(r'api/v1/pause_sets/(?P<pk>\d+)/update/$',
            ConjuntoDePausaUpdate.as_view(),
            name='api_pause_set_update'),
    re_path(r'api/v1/pause_sets/(?P<pk>\d+)/delete/$',
            ConjuntoDePausaDelete.as_view(),
            name='api_pause_set_delete'),
    re_path(r'api/v1/pause_config/create/$',
            ConfiguracionDePausaCreate.as_view(),
            name='api_pause_config_create'),
    re_path(r'api/v1/pause_config/(?P<pk>\d+)/update/$',
            ConfiguracionDePausaUpdate.as_view(),
            name='api_pause_config_update'),
    re_path(r'api/v1/pause_config/(?P<pk>\d+)/delete/$',
            ConfiguracionDePausaDelete.as_view(),
            name='api_pause_config_delete'),
    # =========================
    # Sitios Externos
    # =========================
    re_path(r'api/v1/external_sites/$',
            SitioExternoList.as_view(),
            name='api_external_sites_list'),
    re_path(r'api/v1/external_sites/(?P<pk>\d+)/$',
            SitioExternoDetalle.as_view(),
            name='api_external_sites_detail'),
    re_path(r'api/v1/external_sites/create/$',
            SitioExternoCreate.as_view(),
            name='api_external_sites_create'),
    re_path(r'api/v1/external_sites/(?P<pk>\d+)/update/$',
            SitioExternoUpdate.as_view(),
            name='api_external_sites_update'),
    re_path(r'api/v1/external_sites/(?P<pk>\d+)/delete/$',
            SitioExternoDelete.as_view(),
            name='api_external_sites_delete'),
    re_path(r'api/v1/external_sites/(?P<pk>\d+)/hide/$',
            SitioExternoOcultar.as_view(),
            name='api_external_sites_hide'),
    re_path(r'api/v1/external_sites/(?P<pk>\d+)/show/$',
            SitioExternoDesocultar.as_view(),
            name='api_external_sites_show'),
    # ===================================
    # Autenticacion de Sitios Externos
    # ===================================
    re_path(r'api/v1/external_site_authentications/$',
            ExternalSiteAuthenticationList.as_view(),
            name='api_external_site_authentications_list'),
    re_path(r'api/v1/external_site_authentications/(?P<pk>\d+)/$',
            ExternalSiteAuthenticationDetail.as_view(),
            name='api_external_site_authentications_detail'),
    re_path(r'api/v1/external_site_authentications/create/$',
            ExternalSiteAuthenticationCreate.as_view(),
            name='api_external_site_authentications_create'),
    re_path(r'api/v1/external_site_authentications/test/$',
            ExternalSiteAuthenticationTest.as_view(),
            name='api_external_site_authentications_test'),
    re_path(r'api/v1/external_site_authentications/(?P<pk>\d+)/update/$',
            ExternalSiteAuthenticationUpdate.as_view(),
            name='api_external_site_authentications_update'),
    re_path(r'api/v1/external_site_authentications/(?P<pk>\d+)/delete/$',
            ExternalSiteAuthenticationDelete.as_view(),
            name='api_external_site_authentications_delete'),
    # =========================
    # Calificaciones
    # =========================
    re_path(r'api/v1/call_dispositions/$',
            CalificacionList.as_view(),
            name='api_call_dispositions_list'),
    re_path(r'api/v1/call_dispositions/create/$',
            CalificacionCreate.as_view(),
            name='api_call_dispositions_create'),
    re_path(r'api/v1/call_dispositions/(?P<pk>\d+)/update/$',
            CalificacionUpdate.as_view(),
            name='api_call_dispositions_update'),
    re_path(r'api/v1/call_dispositions/(?P<pk>\d+)/$',
            CalificacionDetail.as_view(),
            name='api_call_dispositions_detail'),
    re_path(r'api/v1/call_dispositions/(?P<pk>\d+)/delete/$',
            CalificacionDelete.as_view(),
            name='api_call_dispositions_delete'),
    # =========================
    # Sistemas Externos
    # =========================
    re_path(r'api/v1/external_systems/$',
            SistemaExternoList.as_view(),
            name='api_external_systems_list'),
    re_path(r'api/v1/external_systems/create/$',
            SistemaExternoCreate.as_view(),
            name='api_external_systems_create'),
    re_path(r'api/v1/external_systems/(?P<pk>\d+)/update/$',
            SistemaExternoUpdate.as_view(),
            name='api_external_systems_update'),
    re_path(r'api/v1/external_systems/(?P<pk>\d+)/$',
            SistemaExternoDetail.as_view(),
            name='api_external_systems_detail'),
    re_path(r'api/v1/agents_external_system/$',
            AgentesSistemaExternoList.as_view(),
            name='api_agents_external_system_list'),
    # =========================
    # Formularios
    # =========================
    re_path(r'api/v1/forms/$',
            FormList.as_view(),
            name='api_forms_list'),
    re_path(r'api/v1/forms/create/$',
            FormCreate.as_view(),
            name='api_forms_create'),
    re_path(r'api/v1/forms/(?P<pk>\d+)/update/$',
            FormUpdate.as_view(),
            name='api_forms_update'),
    re_path(r'api/v1/forms/(?P<pk>\d+)/hide/$',
            FormHide.as_view(),
            name='api_forms_hide'),
    re_path(r'api/v1/forms/(?P<pk>\d+)/show/$',
            FormShow.as_view(),
            name='api_forms_show'),
    re_path(r'api/v1/forms/(?P<pk>\d+)/$',
            FormDetail.as_view(),
            name='api_forms_detail'),
    re_path(r'api/v1/forms/(?P<pk>\d+)/delete/$',
            FormDelete.as_view(),
            name='api_forms_delete'),
    # =========================
    # Pausas
    # =========================
    re_path(r'api/v1/pauses/$',
            PauseList.as_view(),
            name='api_pauses_list'),
    re_path(r'api/v1/pauses/create/$',
            PauseCreate.as_view(),
            name='api_pauses_create'),
    re_path(r'api/v1/pauses/(?P<pk>\d+)/update/$',
            PauseUpdate.as_view(),
            name='api_pauses_update'),
    re_path(r'api/v1/pauses/(?P<pk>\d+)/$',
            PauseDetail.as_view(),
            name='api_pauses_detail'),
    re_path(r'api/v1/pauses/(?P<pk>\d+)/reactivate/$',
            PauseReactivate.as_view(),
            name='api_pauses_reactivate'),
    re_path(r'api/v1/pauses/(?P<pk>\d+)/delete/$',
            PauseDelete.as_view(),
            name='api_pauses_delete'),
    # =========================
    # Rutas Entrantes
    # =========================
    re_path(r'api/v1/inbound_routes/$',
            InboundRouteList.as_view(),
            name='api_inbound_routes_list'),
    re_path(r'api/v1/inbound_routes/create/$',
            InboundRouteCreate.as_view(),
            name='api_inbound_routes_create'),
    re_path(r'api/v1/inbound_routes/(?P<pk>\d+)/update/$',
            InboundRouteUpdate.as_view(),
            name='api_inbound_routes_update'),
    re_path(r'api/v1/inbound_routes/(?P<pk>\d+)/$',
            InboundRouteDetail.as_view(),
            name='api_inbound_routes_detail'),
    re_path(r'api/v1/inbound_routes/(?P<pk>\d+)/delete/$',
            InboundRouteDelete.as_view(),
            name='api_inbound_routes_delete'),
    re_path(r'api/v1/inbound_routes/destinations_by_type/$',
            InboundRouteDestinations.as_view(),
            name='api_inbound_routes_destinations_by_type'),
    # =========================
    # Rutas Salientes
    # =========================
    re_path(r'api/v1/outbound_routes/$',
            OutboundRouteList.as_view(),
            name='api_outbound_routes_list'),
    re_path(r'api/v1/outbound_routes/create/$',
            OutboundRouteCreate.as_view(),
            name='api_outbound_routes_create'),
    re_path(r'api/v1/outbound_routes/(?P<pk>\d+)/update/$',
            OutboundRouteUpdate.as_view(),
            name='api_outbound_routes_update'),
    re_path(r'api/v1/outbound_routes/(?P<pk>\d+)/$',
            OutboundRouteDetail.as_view(),
            name='api_outbound_routes_detail'),
    re_path(r'api/v1/outbound_routes/(?P<pk>\d+)/delete/$',
            OutboundRouteDelete.as_view(),
            name='api_outbound_routes_delete'),
    re_path(r'api/v1/outbound_routes/sip_trunks/$',
            OutboundRouteSIPTrunksList.as_view(),
            name='api_outbound_routes_sip_trunks'),
    re_path(r'api/v1/outbound_routes/(?P<pk>\d+)/orphan_trunks$',
            OutboundRouteOrphanTrunks.as_view(),
            name='api_outbound_routes_orphan_trunks'),
    re_path(r'api/v1/outbound_routes/reorder/$',
            OutboundRouteReorder.as_view(),
            name='api_outbound_routes_reorder'),
    # =========================
    # Grupos Horarios
    # =========================
    re_path(r'api/v1/group_of_hours/$',
            GroupOfHourList.as_view(),
            name='api_group_of_hours_list'),
    re_path(r'api/v1/group_of_hours/create/$',
            GroupOfHourCreate.as_view(),
            name='api_group_of_hours_create'),
    re_path(r'api/v1/group_of_hours/(?P<pk>\d+)/update/$',
            GroupOfHourUpdate.as_view(),
            name='api_group_of_hours_update'),
    re_path(r'api/v1/group_of_hours/(?P<pk>\d+)/$',
            GroupOfHourDetail.as_view(),
            name='api_group_of_hours_detail'),
    re_path(r'api/v1/group_of_hours/(?P<pk>\d+)/delete/$',
            GroupOfHourDelete.as_view(),
            name='api_group_of_hours_delete'),
    # =========================
    # IVRs
    # =========================
    path('api/v1/ivrs/',
         IVRList.as_view(),
         name='api_ivrs_list'),
    path('api/v1/ivrs/create/',
         IVRCreate.as_view(),
         name='api_ivrs_create'),
    path('api/v1/ivrs/<int:pk>/update/',
         IVRUpdate.as_view(),
         name='api_ivrs_update'),
    path('api/v1/ivrs/<int:pk>/',
         IVRDetail.as_view(),
         name='api_ivrs_detail'),
    path('api/v1/ivrs/<int:pk>/delete/',
         IVRDelete.as_view(),
         name='api_ivrs_delete'),
    path('api/v1/ivrs/audio_options/',
         IVRAudioOptions.as_view(),
         name='api_ivrs_audio_options_list'),
    path('api/v1/ivrs/destination_types/',
         IVRDestinationTypes.as_view(),
         name='api_ivrs_destination_types_list'),
    # =========================
    # Register Server
    # =========================
    path('api/v1/register_server/',
         RegisterServerList.as_view(),
         name='api_register_server_detail'),
    path('api/v1/register_server/create/',
         RegisterServerCreate.as_view(),
         name='api_register_server_create'),
    # =========================
    # Base de contactos
    # =========================
    path('api/v1/contact_database/create/',
         BaseDatosContactoCreateView.as_view(), name='api_database_create_view'),
    path('api/v1/contact_database/<int:db_pk>/contact/',
         ContactoCreateView.as_view(), name='api_database_create_contact_view'),
    path('api/v1/contact_database/<int:pk>/campaings/',
         CampaingsOnDB.as_view(),
         name='api_contact_database_campaings'),
    path('api/v1/new_contact/', ContactoDeCampanaCreateView.as_view(),
         name='api_new_contact'),
    path('api/v1/campaign/database_metadata/', CampaignDatabaseMetadataView.as_view(),
         name='api_campaign_database_metadata'),
    path('api/v1/campaign/database_metadata_columns_fields/<int:pk>/',
         CamposDireccionView.as_view(), name='api_database_metadata_columns_fields'),
    # ###########     AGENTE      ############ #
    re_path(r'^api/v1/campaign/(?P<campaign>[^/]+)/contacts/(?P<pk_contacto>\d+)/$',
            ContactoCampanaDetalleView.as_view(),
            name='api_campaign_contact_detail'),
    path('api/v1/campaign/<int:pk_campana>/contacts/',
         API_ObtenerContactosCampanaView.as_view(), name='api_contactos_campana'),
    path('api/v1/agenda_contacto/',
         AgendaContactoCreateAPIView.as_view(),
         name='api_agenda_contacto_create'),
    path('api/v1/makeCall/',
         Click2CallView.as_view(),
         name='api_click2call'),
    path('api/v1/make_call_outside_campaign/',
         Click2CallOutsideCampaign.as_view(),
         name='api_click2call_outside_campaign'),
    path('api/v1/hangupCall/',
         HangUpCallView.as_view(),
         name='api_hangup_call'),
    path('api/v1/asterisk_login/',
         AgentLoginAsterisk.as_view(), name='api_agent_asterisk_login'),
    path('api/v1/asterisk_ready/',
         AgentReadyAsterisk.as_view(), name='api_agent_asterisk_ready'),
    path('api/v1/asterisk_logout/',
         AgentLogoutAsterisk.as_view(), name='api_agent_asterisk_logout'),
    path('agente/logout/', login_required(AgentLogoutView.as_view()),
         name='api_agente_logout'),
    path('api/v1/asterisk_pause/',
         AgentPauseAsterisk.as_view(), name='api_make_pause'),
    path('api/v1/asterisk_unpause/',
         AgentUnpauseAsterisk.as_view(), name='api_make_unpause'),
    path('api/v1/asterisk_ringing/',
         AgentRingingAsterisk.as_view(), name='api_make_ringing'),
    path('api/v1/asterisk_reject_call/',
         AgentRejectCallAsterisk.as_view(), name='api_make_reject_call'),
    path('api/v1/asterisk_disabled/',
         AgentDisabledAsterisk.as_view(), name='api_make_disabled'),
    path('api/v1/notify_end_transferred_call/',
         NotifyEndTransferredCall.as_view(), name='api_notify_end_transferred_call'),
    path('api/v1/sip/credentials/agent/', ObtenerCredencialesSIPAgenteView.as_view(),
         name='api_credenciales_sip_agente'),
    path('api/v1/audit/set_revision_status/', SetEstadoRevisionAuditoria.as_view(),
         name='api_set_estado_revision'),
    path('api/v1/calificar_llamada/', ApiStatusCalificacionLlamada.as_view(),
         name='api_status_calificacion_llamada'),
    path('api/v1/evento_hold/', ApiEventoHold.as_view(),
         name='api_evento_hold'),
    path('api/v1/agent/consultative_confer_hold', ApiConsultativeConferHold.as_view(),
         name='api_consultative_confer_hold'),
    path('api/v1/agent/presence/heartbeat/', AgentPresenceHeartbeatView.as_view(),
         name='api_agent_presence_heartbeat'),
    path('api/v1/agent/transfer_options', ApiAgentesParaTransferencia.as_view({'get': 'list'}),
         name='api_agent_call_transfer_options'),
    # ###########     AUDITORIAS       ############ #
    path('api/v1/auditoria/archivo',
         ObtenerArchivoAuditoriaView.as_view(), name='api_auditoria_archivo'),
    # ###########     GRABACIONES      ############ #
    re_path(r'^api/v1/grabacion/archivo/$',
            ObtenerArchivoGrabacionView.as_view(), name='api_grabacion_archivo'),
    re_path(r'^api/v1/grabacion/descarga_masiva',
            ObtenerArchivosGrabacionView.as_view(), name='api_grabacion_descarga_masiva'),
    path('api/v1/call_record/<str:callid>/',
         ObtenerUrlGrabacionView.as_view(), name='api_call_record_url'),
    path('api/v1/call_record/analysis/<str:task>/<str:callid>/',
         ProcessSpeechAnalisisTaskView.as_view(), name='api_call_record_analysis'),
    # ###########  AUDIOS ASTERISK    ############ #
    path('api/v1/audio/list/',
         ListadoAudiosView.as_view({'get': 'list'}), name='api_audios_listado'),
    # ###########  USUARIOS    ############ #
    path('api/v1/group/list/',
         ListadoGrupos.as_view({'get': 'list'}), name='api_grupos'),
    path('api/v1/agent/list/',
         ListadoAgentes.as_view({'get': 'list'}), name='api_agentes'),
    path('api/v1/audit_supervisor/',
         AuditSupervisor.as_view(), name='api_audit_supervisor'),
    # ###########  WOMBAT DIALER    ############ #
    path('api/v1/wombat_dialer/restart/',
         ReiniciarWombat.as_view(), name='api_restart_wombat'),
    path('api/v1/wombat_dialer/status/',
         WombatState.as_view(), name='api_wombat_state'),
    path('api/v1/wombat_dialer/start/',
         WombatStart.as_view(), name='api_wombat_start'),
    path('api/v1/wombat_dialer/stop/',
         WombatStop.as_view(), name='api_wombat_stop'),
    path('api/v1/supervision/wombat_dialer/stats/',
         SupervisionWombatDialerStats.as_view(), name='supervision_wombat_dialer_stats'),

    # ###########  ASTERISK    ############ #
    path('api/v1/asterisk/queues_data/',
         AsteriskQueuesData.as_view(), name='api_asterisk_queues_data'),
    path('api/v1/asterisk/notify_attended_multinum_call/',
         NotifyAttendedMultinumCall.as_view(), name='api_notify_attended_multinum_call'),
    path('api/v1/asterisk/notify_call_blocked/',
         NotifyCallBlocked.as_view(), name='api_notify_call_blocked'),

    # ###########  Inbound Destinations    ############ #
    re_path(r'^api/v1/inbound_destinations/(?P<type>\d+)/list/',
            DestinoEntranteView.as_view(), name='api_inbound_destinations'),
    path('api/v1/inbound_destinations_types/list/',
         DestinoEntranteTiposView.as_view(), name='api_inbound_destinations_types'),

    # ###########  Inbound Destinations    ############ #
    path('api/v1/reportes/survey_transfer/',
         TransferenciaAEncuestaLogCreateView.as_view(), name='api_log_survey_transfer'),

    # ######  For Bots Internos    ############ #
    path('api/v1/agent_status/campaign/<int:campaign_id>',
         AgentStatusView.as_view(), name='api_agent_status'),
    path('api/v1/agent_status_list/campaign/<int:campaign_id>',
         AgentStatusListView.as_view(), name='api_agent_status_list'),
    path('api/v1/call_status/campaign/<int:campaign_id>',
         CallStatusView.as_view(), name='api_call_status'),
    path('api/reports/campaign-stats/',
         CampaignStatsReportView.as_view(), name='api_reports_campaign_stats'),
    path('api/v1/reportes/agents_activity_v2/',
         AgentsActivityV2ReportView.as_view(), name='api_reportes_agents_activity_v2'),
    path('api/v1/exportar_csv_agents_activity_v2_listado/',
         ExportarCSVAgentsActivityV2Listado.as_view(),
         name='api_exportar_csv_agents_activity_v2_listado'),
    path('api/v1/reportes/agents_kpis_v2/',
         AgentKpisV2ReportView.as_view(), name='agents_kpis_v2'),
    path('api/reporte/centro_de_contacto/',
         login_required(ReporteCentroContactoAPIView.as_view()),
         name='api_reporte_centro_de_contacto'),
    path('api/reporte/omnichannel_share/',
         login_required(GetOmnichannelShareDataView.as_view()),
         name='api_reporte_omnichannel_share'),
    path('api/v1/exportar_csv_canalidades_centro_contacto/',
         ExportarCSVCanalidadesCentroContacto.as_view(),
         name='api_exportar_csv_canalidades_centro_contacto'),
    path('api/v1/exportar_csv_canalidades_egresos_centro_contacto/',
         ExportarCSVCanalidadesEgresosCentroContacto.as_view(),
         name='api_exportar_csv_canalidades_egresos_centro_contacto'),
    path('api/v1/exportar_csv_canalidades_por_hora_centro_contacto/',
         ExportarCSVCanalidadesPorHoraCentroContacto.as_view(),
         name='api_exportar_csv_canalidades_por_hora_centro_contacto'),
    path('api/v1/exportar_csv_canalidades_por_hora_egresos_centro_contacto/',
         ExportarCSVCanalidadesPorHoraEgresosCentroContacto.as_view(),
         name='api_exportar_csv_canalidades_por_hora_egresos_centro_contacto'),
    path('api/v1/exportar_csv_canalidades_por_dia_centro_contacto/',
         ExportarCSVCanalidadesPorDiaCentroContacto.as_view(),
         name='api_exportar_csv_canalidades_por_dia_centro_contacto'),
    path('api/v1/exportar_csv_canalidades_por_dia_egresos_centro_contacto/',
         ExportarCSVCanalidadesPorDiaEgresosCentroContacto.as_view(),
         name='api_exportar_csv_canalidades_por_dia_egresos_centro_contacto'),
    path('api/v1/exportar_csv_canalidades_por_mes_centro_contacto/',
         ExportarCSVCanalidadesPorMesCentroContacto.as_view(),
         name='api_exportar_csv_canalidades_por_mes_centro_contacto'),
    path('api/v1/exportar_csv_canalidades_por_mes_egresos_centro_contacto/',
         ExportarCSVCanalidadesPorMesEgresosCentroContacto.as_view(),
         name='api_exportar_csv_canalidades_por_mes_egresos_centro_contacto'),
    path('api/v1/reporte/centro_contacto/interaction_transfers/',
         InteractionTransfersPorLlamadaAPIView.as_view(),
         name='api_interaction_transfers_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_atendidas_centro_contacto/',
         ExportarCSVLlamadasAtendidasCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_atendidas_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_atendidas_egresos_centro_contacto/',
         ExportarCSVLlamadasAtendidasEgresosCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_atendidas_egresos_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_no_atendidas_centro_contacto/',
         ExportarCSVLlamadasNoAtendidasCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_no_atendidas_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_no_atendidas_egresos_centro_contacto/',
         ExportarCSVLlamadasNoAtendidasEgresosCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_no_atendidas_egresos_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_voz_centro_contacto/',
         ExportarCSVLlamadasVozCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_voz_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_voz_egresos_centro_contacto/',
         ExportarCSVLlamadasVozEgresosCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_voz_egresos_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_por_hora_centro_contacto/',
         ExportarCSVLlamadasPorHoraCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_por_hora_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_por_hora_egresos_centro_contacto/',
         ExportarCSVLlamadasPorHoraEgresosCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_por_hora_egresos_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_por_dia_centro_contacto/',
         ExportarCSVLlamadasPorDiaCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_por_dia_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_por_dia_egresos_centro_contacto/',
         ExportarCSVLlamadasPorDiaEgresosCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_por_dia_egresos_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_por_mes_centro_contacto/',
         ExportarCSVLlamadasPorMesCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_por_mes_centro_contacto'),
    path('api/v1/exportar_csv_llamadas_por_mes_egresos_centro_contacto/',
         ExportarCSVLlamadasPorMesEgresosCentroContacto.as_view(),
         name='api_exportar_csv_llamadas_por_mes_egresos_centro_contacto'),
    path('api/v1/exportar_csv_conversaciones_respondidas_centro_contacto/',
         ExportarCSVConversacionesRespondidasCentroContacto.as_view(),
         name='api_exportar_csv_conversaciones_respondidas_centro_contacto'),
    path('api/v1/exportar_csv_conversaciones_respondidas_egresos_centro_contacto/',
         ExportarCSVConversacionesRespondidasEgresosCentroContacto.as_view(),
         name='api_exportar_csv_conversaciones_respondidas_egresos_centro_contacto'),
    path('api/v1/exportar_csv_conversaciones_no_respondidas_centro_contacto/',
         ExportarCSVConversacionesNoRespondidasCentroContacto.as_view(),
         name='api_exportar_csv_conversaciones_no_respondidas_centro_contacto'),
    path('api/v1/exportar_csv_conversaciones_no_respondidas_egresos_centro_contacto/',
         ExportarCSVConversacionesNoRespondidasEgresosCentroContacto.as_view(),
         name='api_exportar_csv_conversaciones_no_respondidas_egresos_centro_contacto'),
    path('api/v1/exportar_csv_whatsapp_mensajes_por_hora_centro_contacto/',
         ExportarCSVWhatsappMensajesPorHoraCentroContacto.as_view(),
         name='api_exportar_csv_whatsapp_mensajes_por_hora_centro_contacto'),
    path('api/v1/exportar_csv_whatsapp_mensajes_por_hora_egresos_centro_contacto/',
         ExportarCSVWhatsappMensajesPorHoraEgresosCentroContacto.as_view(),
         name='api_exportar_csv_whatsapp_mensajes_por_hora_egresos_centro_contacto'),
    path('api/v1/exportar_csv_whatsapp_mensajes_por_campana_centro_contacto/',
         ExportarCSVWhatsappMensajesPorCampanaCentroContacto.as_view(),
         name='api_exportar_csv_whatsapp_mensajes_por_campana_centro_contacto'),
    path('api/v1/exportar_csv_whatsapp_mensajes_por_campana_egresos_centro_contacto/',
         ExportarCSVWhatsappMensajesPorCampanaEgresosCentroContacto.as_view(),
         name='api_exportar_csv_whatsapp_mensajes_por_campana_egresos_centro_contacto'),
    path('api/v1/exportar_csv_whatsapp_mensajes_por_dia_centro_contacto/',
         ExportarCSVWhatsappMensajesPorDiaCentroContacto.as_view(),
         name='api_exportar_csv_whatsapp_mensajes_por_dia_centro_contacto'),
    path('api/v1/exportar_csv_whatsapp_mensajes_por_dia_egresos_centro_contacto/',
         ExportarCSVWhatsappMensajesPorDiaEgresosCentroContacto.as_view(),
         name='api_exportar_csv_whatsapp_mensajes_por_dia_egresos_centro_contacto'),
    path('api/v1/exportar_csv_whatsapp_mensajes_por_mes_centro_contacto/',
         ExportarCSVWhatsappMensajesPorMesCentroContacto.as_view(),
         name='api_exportar_csv_whatsapp_mensajes_por_mes_centro_contacto'),
    path('api/v1/exportar_csv_whatsapp_mensajes_por_mes_egresos_centro_contacto/',
         ExportarCSVWhatsappMensajesPorMesEgresosCentroContacto.as_view(),
         name='api_exportar_csv_whatsapp_mensajes_por_mes_egresos_centro_contacto'),

    # ######  AudiosAsterisk    ############ #
    path('api/v1/languages/list',
         AudiosAsteriskListView.as_view(), name='audios_asterisk_list'),

    # ###########  TRANSFERENCIAS    ############ #
    path('api/v1/transfer/blind-agent/',
         TransferBlindAgentView.as_view(), name='api_transfer_blind_agent'),
    path('api/v1/transfer/blind-endpoint/',
         TransferBlindEndpointView.as_view(), name='api_transfer_blind_endpoint'),
    path('api/v1/transfer/blind-campaign/',
         TransferBlindCampaignView.as_view(), name='api_transfer_blind_campaign'),
    path('api/v1/transfer/blind-campaign-agent/',
         TransferBlindCampaignAgentView.as_view(), name='api_transfer_blind_campaign_agent'),
    path('api/v1/transfer/3way/',
         Transfer3WayView.as_view(), name='api_transfer_3way'),
    path('api/v1/call/hangup-leg/',
         HangupLegView.as_view(), name='api_call_hangup_leg'),
    path('api/v1/call/spy/',
         SpyChannelView.as_view(), name='api_call_spy'),
    path('api/v1/call/voicebot-hangup/',
         VoicebotHangupView.as_view(), name='api_call_voicebot_hangup'),
    path('api/v1/call/hold/',
         HoldCallView.as_view(), name='api_call_hold'),
    path('api/v1/call/three-way-conf/',
         ThreeWayConfView.as_view(), name='api_three_way_conf'),
    path('api/v1/agent/transfer/consult/start/',
         TransferConsultStartView.as_view(), name='api_transfer_consult_start'),
    path('api/v1/agent/transfer/consult/complete/',
         TransferConsultCompleteView.as_view(), name='api_transfer_consult_complete'),
    path('api/v1/agent/transfer/consult/cancel/',
         TransferConsultCancelView.as_view(), name='api_transfer_consult_cancel'),
    path('api/v1/health/',
         HealthCheckView.as_view(), name='api_health_check'),

    # ###########  VERLOOP WEBHOOK    ############ #
    path('api/v1/webhook/verloop/',
         VerloopWebhookView.as_view(), name='api_verloop_webhook'),

    # ###########  VOICEBOT WEBHOOK (genérico SIP)    ############ #
    path('api/v1/webhook/voicebot/',
         VoicebotWebhookView.as_view(), name='api_voicebot_webhook'),
]
