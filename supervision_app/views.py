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

import datetime
import json
import logging

from django.db.models import Count, Q
from django.http import JsonResponse, Http404
from django.views.generic import TemplateView

from ominicontacto_app.services.kamailio_service import KamailioService

from utiles_globales import AddSettingsContextMixin
from ominicontacto_app.forms.base import GrupoAgenteForm

from ominicontacto_app.models import Campana, Grupo, AgenteProfile
from supervision_app.services.redisgears_service import RedisGearsService
from supervision_app.services.voicebot_calls import get_voicebot_active_call_rows
from ominicontacto_app.services.dialer import get_dialer_service, wombat_habilitado
from ominicontacto_app.services.redis.connection import create_redis_connection
from reportes_app.models import LlamadaLog
from reportes_app.views_campanas_dialer_reportes import _obtener_pacing_contexto

logger = logging.getLogger(__name__)


def _supervisor_voicebot_agents(supervisor, request_user):
    """Agentes voicebot visibles para el supervisor según campañas asignadas."""
    if request_user.get_is_administrador():
        campanas = Campana.objects.obtener_all_dialplan_asterisk()
    else:
        campanas = supervisor.campanas_asignadas_actuales_no_finalizadas()

    agent_ids = set()
    agentes = []
    for campana in campanas:
        for agente in campana.obtener_agentes().filter(voicebot=True).select_related('user'):
            if agente.id not in agent_ids:
                agent_ids.add(agente.id)
                agentes.append(agente)
    return agentes


class SupervisionAgentesView(AddSettingsContextMixin, TemplateView):
    template_name = 'supervision_agentes.html'
    form_class = GrupoAgenteForm

    def get_context_data(self, **kwargs):
        context = super(SupervisionAgentesView,
                        self).get_context_data(**kwargs)
        supervisor = self.request.user.get_supervisor_profile()
        kamailio_service = KamailioService()
        sip_usuario = kamailio_service.generar_sip_user(
            supervisor.sip_extension)
        sip_password = kamailio_service.generar_sip_password(sip_usuario)
        if self.request.user.get_is_administrador():
            campanas = Campana.objects.obtener_all_dialplan_asterisk()
            grupo = Grupo.objects.all()
        else:
            campanas = supervisor.campanas_asignadas_actuales_no_finalizadas()
            ids_agentes = list(campanas.values_list(
                'queue_campana__members__pk', flat=True).distinct())
            id_grupo = AgenteProfile.objects.filter(id__in=ids_agentes).values_list(
                'grupo_id', flat=True).distinct()
            grupo = Grupo.objects.filter(id__in=id_grupo).values_list(
                'nombre', flat=True)
        context['campanas'] = campanas
        context['grupo'] = grupo
        context['sip_usuario'] = sip_usuario
        context['sip_password'] = sip_password
        context['supervisor_id'] = supervisor.id

        RedisGearsService().registra_stream_supervisor(supervisor.id)
        RedisGearsService().registra_stream_supervisor_voicebots(supervisor.id)
        return context


def supervision_voicebot_llamadas(request):
    """
    Snapshot REST de llamadas voicebot activas (1 fila por call_id en Redis).

    GET /supervision/agentes/data/voicebot-llamadas/?campaign_id=
    """
    try:
        supervisor = request.user.get_supervisor_profile()
        if supervisor is None:
            return JsonResponse({'error': 'Supervisor no encontrado'}, status=403)

        campaign_id = request.GET.get('campaign_id')
        if campaign_id is not None and str(campaign_id).strip() == '':
            campaign_id = None

        agentes_voicebot = _supervisor_voicebot_agents(supervisor, request.user)
        redis_connection = None
        try:
            redis_connection = create_redis_connection(db=0)
            redis_connection.ping()
        except Exception as e:
            logger.warning('Error conectando a Redis db=0 para voicebot llamadas: %s', e)

        llamadas = get_voicebot_active_call_rows(
            redis_connection,
            agentes_voicebot,
            campaign_id=campaign_id,
        )
        return JsonResponse({'llamadas': llamadas})
    except Exception as e:
        logger.error('Error en supervision_voicebot_llamadas: %s', e, exc_info=True)
        return JsonResponse({
            'error': 'Error obteniendo llamadas voicebot',
            'detail': str(e),
        }, status=500)


class SupervisionCampanasEntrantesView(TemplateView):
    template_name = 'supervision_campanas_entrantes.html'

    def get_context_data(self, **kwargs):
        context = super(SupervisionCampanasEntrantesView,
                        self).get_context_data(**kwargs)
        supervisor = self.request.user.get_supervisor_profile()
        context['supervisor_id'] = supervisor.id
        if self.request.user.get_is_administrador():
            campanas = Campana.objects.obtener_actuales()
        else:
            campanas = supervisor.campanas_asignadas_actuales()
        campanas = campanas.filter(type=Campana.TYPE_ENTRANTE).order_by('id')
        context['nombres_campanas'] = ",".join([x.nombre for x in campanas])
        context['campanas_ids'] = ",".join([str(x.id) for x in campanas])
        context['campanas'] = {x.id: {'name': x.nombre, 'target': x.objetivo} for x in campanas}
        RedisGearsService().registra_stream_supervisor_entrantes(
            supervisor.id, context['campanas_ids'], context['campanas'])
        return context


class SupervisionCampanasSalientesView(TemplateView):
    template_name = 'supervision_campanas_salientes.html'

    def get_context_data(self, **kwargs):
        context = super(SupervisionCampanasSalientesView,
                        self).get_context_data(**kwargs)
        supervisor = self.request.user.get_supervisor_profile()
        context['supervisor_id'] = supervisor.id
        if self.request.user.get_is_administrador():
            campanas = Campana.objects.obtener_actuales()
        else:
            campanas = supervisor.campanas_asignadas_actuales()
        campanas = campanas.filter(type__in=[Campana.TYPE_DIALER,
                                             Campana.TYPE_PREVIEW,
                                             Campana.TYPE_MANUAL]).order_by('id')
        context['campanas'] = {x.id: {'name': x.nombre, 'target': x.objetivo} for x in campanas}
        return context


class SupervisionCampanasDialerView(TemplateView):
    template_name = 'supervision_campanas_dialers.html'

    def get_context_data(self, **kwargs):
        context = super(SupervisionCampanasDialerView,
                        self).get_context_data(**kwargs)
        supervisor = self.request.user.get_supervisor_profile()
        context['supervisor_id'] = supervisor.id
        if self.request.user.get_is_administrador():
            campanas = Campana.objects.obtener_actuales()
        else:
            campanas = supervisor.campanas_asignadas_actuales()
        campanas = campanas \
            .filter(type=Campana.TYPE_DIALER) \
            .filter(estado__in=[Campana.ESTADO_ACTIVA,
                                Campana.ESTADO_PAUSADA,
                                Campana.ESTADO_INACTIVA]).order_by('id')
        context['nombres_campanas'] = ",".join([x.nombre for x in campanas])
        context['campanas_ids'] = ",".join([str(x.id) for x in campanas])
        context['campanas'] = {x.id: {'name': x.nombre, 'target': x.objetivo} for x in campanas}
        context['wombat_enabled'] = wombat_habilitado()

        # TODO: Datos de Agente por ahora sigue igual
        RedisGearsService().registra_stream_supervisor_dialers(supervisor.id)
        return context


# ============================================
# VISTAS Y FUNCIONES DE DASHBOARD (desde dashboard_camp_app)
# ============================================

def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _apply_filters(queryset, params):
    estado = params.get('estado')
    tipo = params.get('tipo')
    fecha_desde = _parse_date(params.get('fecha_desde'))
    fecha_hasta = _parse_date(params.get('fecha_hasta'))

    if estado:
        try:
            queryset = queryset.filter(estado=int(estado))
        except (TypeError, ValueError):
            pass

    if tipo:
        try:
            queryset = queryset.filter(type=int(tipo))
        except (TypeError, ValueError):
            pass

    date_filter = Q()
    if fecha_desde:
        date_filter &= Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_desde)
    if fecha_hasta:
        date_filter &= Q(fecha_inicio__isnull=True) | Q(fecha_inicio__lte=fecha_hasta)
    if date_filter:
        queryset = queryset.filter(date_filter)

    return queryset


def _build_counts(queryset, field, choices):
    counts = dict(
        queryset.values(field).annotate(total=Count('id')).values_list(field, 'total')
    )
    return [{
        'value': value,
        'label': str(label),
        'count': counts.get(value, 0),
    } for value, label in choices]


def _build_metrics(queryset):
    total = queryset.count()
    por_estado = _build_counts(queryset, 'estado', Campana.ESTADOS)
    por_tipo = _build_counts(queryset, 'type', Campana.TYPES_CAMPANA)
    return {
        'total': total,
        'por_estado': por_estado,
        'por_tipo': por_tipo,
    }


class DashboardCampView(AddSettingsContextMixin, TemplateView):
    template_name = 'supervision_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super(DashboardCampView, self).get_context_data(**kwargs)
        queryset = Campana.objects.filter(oculto=False)
        queryset = _apply_filters(queryset, self.request.GET)
        context['initial_metrics'] = json.dumps(_build_metrics(queryset))
        context['estado_choices'] = Campana.ESTADOS
        context['tipo_choices'] = Campana.TYPES_CAMPANA
        return context


def _campanas_panel_general_queryset(request_user):
    """
    Campañas disponibles en el selector del panel-general.

    Admin: todas las no finalizadas / no templates.
    Supervisor: solo las asignadas actuales no finalizadas.
    Sin perfil supervisor: vacío (fallback polling en el cliente).
    """
    estados_excluidos = [
        Campana.ESTADO_FINALIZADA,
        Campana.ESTADO_TEMPLATE_ACTIVO,
        Campana.ESTADO_TEMPLATE_BORRADO,
    ]
    try:
        if request_user.get_is_administrador():
            return Campana.objects.filter(oculto=False).exclude(
                estado__in=estados_excluidos
            ).order_by('nombre')
        supervisor = request_user.get_supervisor_profile()
        if supervisor is None:
            return Campana.objects.none()
        return supervisor.campanas_asignadas_actuales_no_finalizadas().filter(
            oculto=False
        ).order_by('nombre')
    except Exception:
        return Campana.objects.none()


def _enrich_contact_center_supervisor_context(context, request_user):
    """Inyecta supervisor_id / SIP y registra el stream Redis de agentes."""
    try:
        supervisor = request_user.get_supervisor_profile()
        if supervisor is None:
            raise AttributeError('supervisor profile missing')
        context['supervisor_id'] = supervisor.id
        kamailio_service = KamailioService()
        sip_usuario = kamailio_service.generar_sip_user(supervisor.sip_extension)
        sip_password = kamailio_service.generar_sip_password(sip_usuario)
        context['sip_usuario'] = sip_usuario
        context['sip_password'] = sip_password
        RedisGearsService().registra_stream_supervisor(supervisor.id)
    except Exception:
        context['supervisor_id'] = None
        context['sip_usuario'] = ''
        context['sip_password'] = ''
    return context


class DashboardContactCenterView(AddSettingsContextMixin, TemplateView):
    template_name = 'supervision_contact_center.html'

    def get_context_data(self, **kwargs):
        context = super(DashboardContactCenterView, self).get_context_data(**kwargs)
        context['campanas'] = _campanas_panel_general_queryset(self.request.user)
        return _enrich_contact_center_supervisor_context(context, self.request.user)


class DashboardContactCenterCampaignView(AddSettingsContextMixin, TemplateView):
    """Panel general con campaña fija por URL (supervision/<id_camp>/panel-general/)."""
    template_name = 'supervision_contact_center.html'

    def get_context_data(self, **kwargs):
        id_camp = kwargs.get('id_camp')
        if id_camp is None:
            raise Http404

        queryset = _campanas_panel_general_queryset(self.request.user)
        campana = queryset.filter(id=id_camp).first()
        if not campana:
            raise Http404

        context = super(DashboardContactCenterCampaignView, self).get_context_data(**kwargs)
        context['campanas'] = queryset
        context['initial_campaign_id'] = id_camp
        return _enrich_contact_center_supervisor_context(context, self.request.user)


def _campanas_panel_dialer_queryset(request_user):
    """Campañas dialer del selector de Panel Dialer (mismo alcance que panel-general + TYPE_DIALER)."""
    return _campanas_panel_general_queryset(request_user).filter(type=Campana.TYPE_DIALER)


def _empty_panel_dialer_estado():
    return {
        'estado_discador': {
            'pending_initial': 0,
            'pending_retries': 0,
            'finalized_no_contact': 0,
            'contacted_successfully': 0,
            'attempted_calls': 0,
            'answered_pstn': 0,
            'answered_agent': 0,
            'conectadas_no_atendidas': 0,
            'estimadas': 0,
            'contactos_llamados': 0,
            'campana_nombre': '',
            'campana_estado': '',
            'status': [],
        },
        'llamadas_discando': 0,
        'pacing': None,
        'show_pacing_section': False,
    }


def _panel_dialer_estado_payload(campana):
    """
    Payload Estado Discador del Panel Dialer (paridad con modal campana_dialer/detalle_servicio).
    Reutiliza obtener_estado_campana + pacing del motor dialer.
    """
    empty = _empty_panel_dialer_estado()
    if not campana:
        return empty

    dialer_service = get_dialer_service()
    try:
        datos = dialer_service.obtener_estado_campana(campana) or {}
    except Exception as e:
        logger.error(
            'Error obtener_estado_campana para panel dialer campana %s: %s',
            campana.id, e, exc_info=True,
        )
        datos = {}

    redis_dialer = None
    try:
        redis_dialer = create_redis_connection(db=3)
        redis_dialer.ping()
    except Exception:
        redis_dialer = None

    legacy = _get_dialer_status_metrics(redis_dialer, campana.id) if redis_dialer else empty['estado_discador']

    if 'contactos_llamados' in datos:
        contactos_llamados = datos.get('contactos_llamados', 0)
    else:
        try:
            contactos_llamados = LlamadaLog.objects.cantidad_contactos_llamados(campana)
        except Exception:
            contactos_llamados = 0

    status = []
    for item in datos.get('status') or []:
        status.append({
            'gbState': item.get('gbState'),
            'gbStateLabel': str(item.get('gbStateLabel') or item.get('gbState') or ''),
            'gbStateExt': item.get('gbStateExt') or '',
            'nCalls': _safe_int(item.get('nCalls', 0), 0),
        })

    estado = {
        'pending_initial': _safe_int(
            datos.get('estimadas_iniciales', legacy.get('pending_initial', 0)), 0),
        'pending_retries': _safe_int(
            datos.get('reintentos_abiertos', legacy.get('pending_retries', 0)), 0),
        'finalized_no_contact': _safe_int(
            datos.get('terminadas_no', legacy.get('finalized_no_contact', 0)), 0),
        'contacted_successfully': _safe_int(
            datos.get('terminadas_ok', legacy.get('contacted_successfully', 0)), 0),
        'attempted_calls': _safe_int(
            datos.get('efectuadas', legacy.get('attempted_calls', 0)), 0),
        'answered_pstn': _safe_int(
            datos.get('llamadas_conectadas', legacy.get('answered_pstn', 0)), 0),
        'answered_agent': _safe_int(legacy.get('answered_agent', 0), 0),
        'conectadas_no_atendidas': _safe_int(datos.get('conectadas_no_atendidas', 0), 0),
        'estimadas': _safe_int(datos.get('estimadas', 0), 0),
        'contactos_llamados': _safe_int(contactos_llamados, 0),
        'campana_nombre': campana.nombre or '',
        'campana_estado': str(campana.get_estado_display()),
        'status': status,
    }

    try:
        pacing_ctx = _obtener_pacing_contexto(campana, dialer_service)
    except Exception as e:
        logger.error(
            'Error pacing para panel dialer campana %s: %s', campana.id, e, exc_info=True,
        )
        pacing_ctx = {'pacing': None, 'show_pacing_section': False}

    return {
        'estado_discador': estado,
        'llamadas_discando': _safe_int(datos.get('canales_abiertos_pstn', 0), 0),
        'pacing': pacing_ctx.get('pacing'),
        'show_pacing_section': bool(pacing_ctx.get('show_pacing_section')),
    }


class DashboardPanelDialerView(AddSettingsContextMixin, TemplateView):
    template_name = 'supervision_panel_dialer.html'

    def get_context_data(self, **kwargs):
        context = super(DashboardPanelDialerView, self).get_context_data(**kwargs)
        context['campanas'] = _campanas_panel_dialer_queryset(self.request.user)
        return _enrich_contact_center_supervisor_context(context, self.request.user)


class DashboardPanelDialerCampaignView(AddSettingsContextMixin, TemplateView):
    """Panel Dialer con campaña fija por URL (supervision/<id_camp>/panel-dialer/)."""
    template_name = 'supervision_panel_dialer.html'

    def get_context_data(self, **kwargs):
        id_camp = kwargs.get('id_camp')
        if id_camp is None:
            raise Http404

        queryset = _campanas_panel_dialer_queryset(self.request.user)
        campana = queryset.filter(id=id_camp).first()
        if not campana:
            raise Http404

        context = super(DashboardPanelDialerCampaignView, self).get_context_data(**kwargs)
        context['campanas'] = queryset
        context['initial_campaign_id'] = id_camp
        return _enrich_contact_center_supervisor_context(context, self.request.user)


class DashboardDialerCampView(AddSettingsContextMixin, TemplateView):
    template_name = 'supervision_dialer_camp_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super(DashboardDialerCampView, self).get_context_data(**kwargs)
        return context


class DashboardCampEntrantesView(AddSettingsContextMixin, TemplateView):
    template_name = 'supervision_camp_entrantes_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super(DashboardCampEntrantesView, self).get_context_data(**kwargs)
        return context


def dashboard_camp_metrics(request):
    queryset = Campana.objects.filter(oculto=False)
    queryset = _apply_filters(queryset, request.GET)
    return JsonResponse(_build_metrics(queryset))


def dashboard_camp_list(request):
    queryset = Campana.objects.filter(oculto=False)
    queryset = _apply_filters(queryset, request.GET)
    queryset = queryset.order_by('nombre')
    rows = [{
        'id': campana.id,
        'nombre': campana.nombre,
        'estado': campana.get_estado_display(),
        'tipo': campana.get_type_display(),
        'fecha_inicio': campana.fecha_inicio.isoformat() if campana.fecha_inicio else None,
        'fecha_fin': campana.fecha_fin.isoformat() if campana.fecha_fin else None,
    } for campana in queryset[:200]]
    return JsonResponse({'total': queryset.count(), 'items': rows})


def _safe_int(value, default=0):
    """Convierte un valor a int de forma segura."""
    try:
        if value is None:
            return default
        # Manejar bytes de Redis
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=0.0):
    """Convierte un valor a float de forma segura."""
    try:
        if value is None:
            return default
        # Manejar bytes de Redis
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        return float(value) if value else default
    except (ValueError, TypeError):
        return default


def _normalize_redis_dict(redis_dict):
    """
    Normaliza un diccionario de Redis convirtiendo bytes a strings.
    
    Maneja valores None y otros tipos inesperados de forma segura.
    """
    if not redis_dict:
        return {}
    normalized = {}
    for key, value in redis_dict.items():
        try:
            # Convertir clave de bytes a string si es necesario
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            elif key is None:
                # Si la clave es None, usar string vacío como fallback
                key = ''
            
            # Convertir valor de bytes a string si es necesario
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            elif value is None:
                # Convertir None a string vacío para consistencia
                value = ''
            elif not isinstance(value, (str, int, float)):
                # Si el valor es de un tipo inesperado, convertirlo a string
                # Esto maneja casos donde Redis podría retornar otros tipos
                try:
                    value = str(value)
                except Exception:
                    # Si la conversión falla, usar string vacío
                    value = ''
                    logger.warning(f"Error normalizando valor de tipo {type(value)} en Redis dict, usando string vacío")
            
            normalized[key] = value
        except Exception as e:
            # Si hay un error procesando esta clave/valor, loguear y continuar
            logger.warning(f"Error normalizando clave/valor de Redis: {e}", exc_info=False)
            continue
    
    return normalized


def _get_all_agent_ids_scan(redis_agent_connection):
    """
    Obtiene todos los IDs de agentes usando SCAN (no bloqueante) en lugar de KEYS.
    
    Usa SCAN iterativo con count=100 para balance entre rendimiento y memoria.
    Extrae los IDs de las keys que coinciden con el patrón 'OML:AGENT:*'.
    
    Args:
        redis_agent_connection: Conexión a Redis
        
    Returns:
        set: Set de strings con los IDs de agentes
    """
    agent_ids = set()
    cursor = 0
    
    while True:
        # SCAN retorna (next_cursor, [keys])
        cursor, keys = redis_agent_connection.scan(
            cursor=cursor,
            match='OML:AGENT:*',
            count=100
        )
        
        # Procesar las keys encontradas en esta iteración
        for key in keys:
            try:
                # Convertir key de bytes a string si es necesario
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                # Extraer el ID del agente del formato 'OML:AGENT:{id}'
                agent_id = int(key.split('OML:AGENT:')[1])
                agent_ids.add(str(agent_id))
            except (ValueError, IndexError):
                # Ignorar keys que no tienen el formato esperado
                continue
        
        # Si el cursor es 0, hemos terminado de escanear
        if cursor == 0:
            break
    
    return agent_ids


def _get_agent_metrics(redis_agent_connection, campaign_id=None, redis_calldata_connection=None):
    """
    Obtiene métricas de agentes desde Redis.
    
    Si campaign_id se especifica, obtiene solo los agentes asignados a esa campaña
    usando OML:CAMPAIGN-AGENTS:{campaign_id} y luego OML:AGENT:{id_agente}.
    
    También obtiene datos estadísticos desde OML:AGENTDATA:AGENT:{id_agente} si se
    proporciona redis_calldata_connection (Redis db=2).
    
    Retorna un diccionario con:
    - Métricas agregadas (logueados, ready, oncall, etc.)
    - Lista de agentes individuales con sus datos
    """
    try:
        agents = []
        agent_ids = set()
        
        if campaign_id:
            # Obtener agentes asignados a la campaña desde OML:CAMPAIGN-AGENTS:{campaign_id}
            campaign_agents_key = f'OML:CAMPAIGN-AGENTS:{campaign_id}'
            agent_ids_raw = redis_agent_connection.smembers(campaign_agents_key)
            # Normalizar agent_ids: convertir bytes a strings si es necesario
            agent_ids = set()
            for agent_id in agent_ids_raw:
                if isinstance(agent_id, bytes):
                    agent_id = agent_id.decode('utf-8')
                agent_ids.add(str(agent_id))
            if not agent_ids:
                # Si no hay agentes en la campaña, obtener solo voicebot desde Redis DB 2
                voicebot_value = 0
                if redis_calldata_connection:
                    try:
                        voicebot_key = f'OML:CALLDATA:VOICEBOT-CALLS:{campaign_id}'
                        voicebot_raw = redis_calldata_connection.get(voicebot_key)
                        if voicebot_raw:
                            voicebot_value = _safe_int(voicebot_raw, 0)
                    except Exception as e:
                        logger.warning(f"Error obteniendo valor de VOICEBOT-CALLS para campaña {campaign_id}: {e}")
                        voicebot_value = 0
                
                return {
                    'logueados': 0,
                    'ready': 0,
                    'oncall': 0,
                    'paused': 0,
                    'onconfer': 0,
                    'voicebot': voicebot_value,
                    'lista_agentes': [],
                }
        else:
            # Si no se especifica campaña, obtener todos los agentes usando SCAN (no bloqueante)
            agent_ids = _get_all_agent_ids_scan(redis_agent_connection)
        
        # Obtener datos de cada agente usando pipelines de Redis para optimizar rendimiento
        # Convertir agent_ids a lista para mantener orden y poder indexar resultados
        agent_ids_list = list(agent_ids)
        
        if not agent_ids_list:
            # Si no hay agentes, retornar métricas vacías
            return {
                'logueados': 0,
                'ready': 0,
                'oncall': 0,
                'paused': 0,
                'onconfer': 0,
                'voicebot': 0,
                'lista_agentes': [],
            }
        
        # Crear pipeline para obtener datos de agentes desde OML:AGENT:{id}
        agent_pipeline = redis_agent_connection.pipeline()
        for agent_id in agent_ids_list:
            agent_key = f'OML:AGENT:{agent_id}'
            agent_pipeline.hgetall(agent_key)
        
        # Crear pipeline para obtener datos estadísticos desde OML:AGENTDATA:AGENT:{id} si está disponible
        agentdata_pipeline = None
        if redis_calldata_connection:
            agentdata_pipeline = redis_calldata_connection.pipeline()
            for agent_id in agent_ids_list:
                agentdata_key = f'OML:AGENTDATA:AGENT:{agent_id}'
                agentdata_pipeline.hgetall(agentdata_key)
        
        # Ejecutar pipelines en paralelo (2 round-trips en lugar de 2N)
        try:
            agent_results = agent_pipeline.execute()
        except Exception as e:
            logger.error(f"Error ejecutando pipeline de agentes: {e}", exc_info=True)
            agent_results = []
        
        # Validar que el número de resultados coincida con el número de requests
        if len(agent_results) != len(agent_ids_list):
            logger.error(
                f"Pipeline de agentes incompleto: esperado {len(agent_ids_list)} resultados, "
                f"obtenido {len(agent_results)}"
            )
            # Ajustar resultados para evitar IndexError
            if len(agent_results) < len(agent_ids_list):
                agent_results.extend([None] * (len(agent_ids_list) - len(agent_results)))
            else:
                agent_results = agent_results[:len(agent_ids_list)]
        
        try:
            agentdata_results = agentdata_pipeline.execute() if agentdata_pipeline else [None] * len(agent_ids_list)
        except Exception as e:
            logger.error(f"Error ejecutando pipeline de agentdata: {e}", exc_info=True)
            agentdata_results = [None] * len(agent_ids_list)
        
        # Validar que el número de resultados de agentdata coincida con el número de requests
        if agentdata_pipeline and len(agentdata_results) != len(agent_ids_list):
            logger.error(
                f"Pipeline de agentdata incompleto: esperado {len(agent_ids_list)} resultados, "
                f"obtenido {len(agentdata_results)}"
            )
            # Ajustar resultados para evitar IndexError
            if len(agentdata_results) < len(agent_ids_list):
                agentdata_results.extend([None] * (len(agent_ids_list) - len(agentdata_results)))
            else:
                agentdata_results = agentdata_results[:len(agent_ids_list)]
        
        # Procesar resultados de los pipelines
        for idx, agent_id in enumerate(agent_ids_list):
            try:
                agent_data = agent_results[idx]
                if agent_data:
                    # Normalizar datos de Redis (convertir bytes a strings si es necesario)
                    agent_data = _normalize_redis_dict(agent_data)
                    
                    # Agregar el ID del agente a los datos
                    agent_data['id'] = int(agent_id)
                    
                    # Excluir agentes voicebot: la tabla solo muestra estado de agentes humanos
                    if agent_data.get('VOICEBOT') == '1':
                        continue
                    
                    # Procesar datos estadísticos desde OML:AGENTDATA:AGENT:{id_agente} si está disponible
                    if redis_calldata_connection:
                        try:
                            agentdata = agentdata_results[idx]
                            if agentdata:
                                # Normalizar datos de Redis
                                agentdata = _normalize_redis_dict(agentdata)
                                
                                # Agregar ANSWERED_TOTAL_CALLS:IN a los datos del agente
                                answered_total_calls_in = agentdata.get('ANSWERED_TOTAL_CALLS:IN', '0')
                                agent_data['ANSWERED_TOTAL_CALLS_IN'] = _safe_int(answered_total_calls_in, 0)
                                # Agregar ANSWERED_TOTAL_CALLS:DIALER a los datos del agente
                                answered_total_calls_dialer = agentdata.get('ANSWERED_TOTAL_CALLS:DIALER', '0')
                                agent_data['ANSWERED_TOTAL_CALLS_DIALER'] = _safe_int(answered_total_calls_dialer, 0)
                                # Agregar ANSWERED_TOTAL_CALLS:MANUAL a los datos del agente
                                answered_total_calls_manual = agentdata.get('ANSWERED_TOTAL_CALLS:MANUAL', '0')
                                agent_data['ANSWERED_TOTAL_CALLS_MANUAL'] = _safe_int(answered_total_calls_manual, 0)
                                # Obtener ANSWERED_TOTAL_TIME y calcular ATT
                                answered_total_time = _safe_float(agentdata.get('ANSWERED_TOTAL_TIME', '0'))
                                total_calls = agent_data['ANSWERED_TOTAL_CALLS_IN'] + agent_data['ANSWERED_TOTAL_CALLS_DIALER'] + agent_data['ANSWERED_TOTAL_CALLS_MANUAL']
                                if total_calls > 0:
                                    agent_data['ATT'] = answered_total_time / total_calls
                                else:
                                    agent_data['ATT'] = 0.0
                            else:
                                # Si no hay datos de agentdata, inicializar con valores por defecto
                                agent_data['ANSWERED_TOTAL_CALLS_IN'] = 0
                                agent_data['ANSWERED_TOTAL_CALLS_DIALER'] = 0
                                agent_data['ANSWERED_TOTAL_CALLS_MANUAL'] = 0
                                agent_data['ATT'] = 0.0
                        except Exception as e:
                            logger.warning(f"Error procesando datos de AGENTDATA para agente {agent_id}: {e}")
                            agent_data['ANSWERED_TOTAL_CALLS_IN'] = 0
                            agent_data['ANSWERED_TOTAL_CALLS_DIALER'] = 0
                            agent_data['ANSWERED_TOTAL_CALLS_MANUAL'] = 0
                            agent_data['ATT'] = 0.0
                    else:
                        # Si no hay conexión a calldata, inicializar con valores por defecto
                        agent_data['ANSWERED_TOTAL_CALLS_IN'] = 0
                        agent_data['ANSWERED_TOTAL_CALLS_DIALER'] = 0
                        agent_data['ANSWERED_TOTAL_CALLS_MANUAL'] = 0
                        agent_data['ATT'] = 0.0
                    
                    agents.append(agent_data)
            except (ValueError, TypeError) as e:
                logger.warning(f"Error procesando agente {agent_id}: {e}")
                continue

        # Obtener valor de voicebot desde Redis DB 2
        voicebot_value = 0
        if redis_calldata_connection and campaign_id:
            try:
                voicebot_key = f'OML:CALLDATA:VOICEBOT-CALLS:{campaign_id}'
                voicebot_raw = redis_calldata_connection.get(voicebot_key)
                if voicebot_raw:
                    voicebot_value = _safe_int(voicebot_raw, 0)
            except Exception as e:
                logger.warning(f"Error obteniendo valor de VOICEBOT-CALLS para campaña {campaign_id}: {e}")
                voicebot_value = 0
        
        # Contar por estado
        status_counts = {
            'logueados': len([a for a in agents if a.get('STATUS')]),
            'ready': len([a for a in agents if a.get('STATUS') == 'READY']),
            'oncall': len([a for a in agents if a.get('STATUS') == 'ONCALL']),
            'paused': len([a for a in agents if a.get('STATUS') and a.get('STATUS').startswith('PAUSE')]),
            'onconfer': len([a for a in agents if 'CONFER' in a.get('STATUS', '')]),
            'voicebot': voicebot_value,  # Valor desde Redis DB 2
            'lista_agentes': agents,
        }
        return status_counts
    except Exception as e:
        logger.error(f"Error obteniendo métricas de agentes: {e}", exc_info=True)
        return {
            'logueados': 0,
            'ready': 0,
            'oncall': 0,
            'paused': 0,
            'onconfer': 0,
            'voicebot': 0,
            'lista_agentes': [],
        }


def _get_campaign_call_metrics(redis_calldata_connection, campaign_id, redis_dialer_connection=None, redis_oml_connection=None):
    """Obtiene métricas de llamadas desde Redis para una campaña."""
    if not campaign_id:
        return {}

    try:
        calldata_key = f'OML:CALLDATA:CAMP:{campaign_id}'
        calldata_raw = redis_calldata_connection.hgetall(calldata_key)
        # Normalizar datos de Redis (convertir bytes a strings si es necesario)
        calldata = _normalize_redis_dict(calldata_raw)
        
        # Log de depuración para verificar datos leídos
        logger.debug(f"[DEBUG] Datos de Redis para campaña {campaign_id}: {calldata}")

        # Obtener valor de llamadas discando desde Redis DB3
        llamadas_discando = 0
        if redis_dialer_connection:
            try:
                dialer_key = f'OML:CALLS:{campaign_id}:DIALER'
                dialer_value = redis_dialer_connection.get(dialer_key)
                llamadas_discando = _safe_int(dialer_value, 0)
            except Exception as e:
                logger.warning(f"Error obteniendo valor de DIALER para campaña {campaign_id}: {e}")
                llamadas_discando = 0

        # Métricas de outbound - leer desde CALL_TYPE:2 (llamadas salientes manuales) y CALL_TYPE:1
        # según los datos guardados en Redis DB2: OML:CALLDATA:CAMP:{campaign_id}
        dial_type2 = _safe_int(calldata.get('CALL_TYPE:2:DIAL', 0))
        exit_answered_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_ANSWERED', 0))
        # Leer las claves específicas para diferenciar Human, Bot y Mixta
        exit_answered_human_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_ANSWERED_HUMAN', 0))
        exit_answered_bot_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_ANSWERED_BOT', 0))
        exit_answered_mix_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_ANSWERED_MIX', 0))
        busy_type2 = _safe_int(calldata.get('CALL_TYPE:2:BUSY', 0))
        exit_busy_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_BUSY', 0))
        noanswer_type2 = _safe_int(calldata.get('CALL_TYPE:2:NOANSWER', 0))
        exit_timeout_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_TIMEOUT', 0))
        exit_handoff_timeout_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_HANDOFF_TIMEOUT', 0))
        exit_amd_type5 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_AMD', 0))
        
        # También leer datos de CALL_TYPE:1 para sumar métricas
        dial_type1 = _safe_int(calldata.get('CALL_TYPE:1:DIAL', 0))
        exit_answered_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_ANSWERED', 0))
        # Leer las claves específicas para CALL_TYPE:1 también
        exit_answered_human_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_ANSWERED_HUMAN', 0))
        exit_answered_bot_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_ANSWERED_BOT', 0))
        exit_answered_mix_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_ANSWERED_MIX', 0))
        busy_type1 = _safe_int(calldata.get('CALL_TYPE:1:BUSY', 0))
        exit_busy_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_BUSY', 0))
        noanswer_type1 = _safe_int(calldata.get('CALL_TYPE:1:NOANSWER', 0))
        exit_timeout_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_TIMEOUT', 0))
        exit_handoff_timeout_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_HANDOFF_TIMEOUT', 0))
        exit_congestion_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_CONGESTION', 0))
        exit_congestion_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_CONGESTION', 0))
        chanunavail_type2 = _safe_int(calldata.get('CALL_TYPE:2:CHANUNAVAIL', 0))
        chanunavail_type1 = _safe_int(calldata.get('CALL_TYPE:1:CHANUNAVAIL', 0))
        chanunavail_total = chanunavail_type2 + chanunavail_type1
        cancel_type2 = _safe_int(calldata.get('CALL_TYPE:2:CANCEL', 0))
        cancel_type1 = _safe_int(calldata.get('CALL_TYPE:1:CANCEL', 0))
        canceladas_total = cancel_type2 + cancel_type1
        nondialplan_type2 = _safe_int(calldata.get('CALL_TYPE:2:NONDIALPLAN', 0))
        exit_shortcall_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_SHORTCALL', 0))
        exit_shortcall_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_SHORTCALL', 0))
        shortcall_total = exit_shortcall_type1 + exit_shortcall_type2
        errores_total = (
            _safe_int(calldata.get('CALL_TYPE:2:FAIL', 0))
            + _safe_int(calldata.get('CALL_TYPE:1:FAIL', 0))
            + _safe_int(calldata.get('CALL_TYPE:2:OTHER', 0))
            + _safe_int(calldata.get('CALL_TYPE:1:OTHER', 0))
            + _safe_int(calldata.get('CALL_TYPE:2:BLACKLIST', 0))
            + _safe_int(calldata.get('CALL_TYPE:1:BLACKLIST', 0))
        )
        
        # Calcular ocupado como suma de BUSY y EXIT_BUSY de ambos tipos
        ocupado_total = busy_type2 + exit_busy_type2 + busy_type1 + exit_busy_type1
        
        # Calcular congestion como suma de ambos tipos
        congestion_total = exit_congestion_type2 + exit_congestion_type1
        
        # Calcular timeout como suma de NOANSWER y EXIT_TIMEOUT (+ post-handoff voicebot) de ambos tipos
        timeout_total = (
            noanswer_type2
            + noanswer_type1
            + exit_timeout_type2
            + exit_timeout_type1
            + exit_handoff_timeout_type2
            + exit_handoff_timeout_type1
        )
        
        # Calcular atendidas separadas por tipo (Human, Bot, Mixta)
        atendidas_human = exit_answered_human_type2 + exit_answered_human_type1
        atendidas_bot = exit_answered_bot_type2 + exit_answered_bot_type1
        atendidas_mix = exit_answered_mix_type2 + exit_answered_mix_type1
        # Calcular total de atendidas como suma de Human, Bot y Mixta
        # Si no hay valores específicos, usar el valor genérico EXIT_ANSWERED como fallback
        if atendidas_human == 0 and atendidas_bot == 0 and atendidas_mix == 0:
            atendidas_total = exit_answered_type2 + exit_answered_type1
        else:
            atendidas_total = atendidas_human + atendidas_bot + atendidas_mix
        
        # Calcular discadas como suma de ambos tipos, con fallback a DIAL_OUT
        discadas_total = dial_type2 + dial_type1
        if discadas_total == 0:
            discadas_total = _safe_int(calldata.get('DIAL_OUT', 0))
        
        outbound = {
            'discadas': discadas_total,  # CALL_TYPE:2:DIAL + CALL_TYPE:1:DIAL o DIAL_OUT
            'atendidas': atendidas_total,  # Total de atendidas (Human + Bot + Mixta)
            'atendidas_human': atendidas_human,  # CALL_TYPE:2:EXIT_ANSWERED_HUMAN + CALL_TYPE:1:EXIT_ANSWERED_HUMAN
            'atendidas_bot': atendidas_bot,  # CALL_TYPE:2:EXIT_ANSWERED_BOT + CALL_TYPE:1:EXIT_ANSWERED_BOT
            'atendidas_mix': atendidas_mix,  # CALL_TYPE:2:EXIT_ANSWERED_MIX + CALL_TYPE:1:EXIT_ANSWERED_MIX
            'positivas': atendidas_total,  # CALL_TYPE:2:EXIT_ANSWERED + CALL_TYPE:1:EXIT_ANSWERED
            'llamadas_discando': llamadas_discando,  # Valor desde Redis DB3 OML:CALLS:{id_camp}:DIALER
            'contestadores': exit_amd_type5,  # CALL_TYPE:2:EXIT_AMD
            'ocupado': ocupado_total,  # CALL_TYPE:2:BUSY + CALL_TYPE:2:EXIT_BUSY + CALL_TYPE:1:BUSY + CALL_TYPE:1:EXIT_BUSY
            'timeout': timeout_total,  # CALL_TYPE:2:NOANSWER + CALL_TYPE:1:NOANSWER + CALL_TYPE:2:EXIT_TIMEOUT + CALL_TYPE:1:EXIT_TIMEOUT
            'canceladas': canceladas_total,  # CALL_TYPE:2:CANCEL + CALL_TYPE:1:CANCEL
            'congestion': congestion_total,  # CALL_TYPE:2:EXIT_CONGESTION + CALL_TYPE:1:EXIT_CONGESTION
            'chanunavail': chanunavail_total,  # CALL_TYPE:2:CHANUNAVAIL + CALL_TYPE:1:CHANUNAVAIL (Redis)
            'num_sin_ruta': nondialplan_type2,  # CALL_TYPE:2:NONDIALPLAN
            'errores': errores_total,  # FAIL + OTHER + BLACKLIST (CALL_TYPE 1 y 2)
            'shortcall': shortcall_total,  # CALL_TYPE:1:EXIT_SHORTCALL + CALL_TYPE:2:EXIT_SHORTCALL
        }

        
        # Log de depuración para verificar métricas calculadas
        logger.debug(f"[DEBUG] Métricas outbound calculadas para campaña {campaign_id}: {outbound}")

        # Métricas de inbound - leer desde CALL_TYPE:3 del hash OML:CALLDATA:CAMP:{campaign_id}
        # El logger escribe EXIT_ANSWERED_HUMAN/BOT/MIX, no EXIT_ANSWERED genérico
        abandonadas = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ABANDON', 0)) + _safe_int(
            calldata.get('CALL_TYPE:3:EXIT_HANDOFF_ABANDON', 0)
        )
        timeout = _safe_int(calldata.get('CALL_TYPE:3:EXIT_TIMEOUT', 0)) + _safe_int(
            calldata.get('CALL_TYPE:3:EXIT_HANDOFF_TIMEOUT', 0)
        )
        exit_answered_human = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ANSWERED_HUMAN', 0))
        exit_answered_bot = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ANSWERED_BOT', 0))
        exit_answered_mix = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ANSWERED_MIX', 0))
        exit_answered = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ANSWERED', 0))

        if exit_answered_human + exit_answered_bot + exit_answered_mix > 0:
            atendidas = exit_answered_human + exit_answered_bot + exit_answered_mix
        else:
            atendidas = exit_answered  # Fallback para datos del sync

        # Calcular total de entrantes como suma de abandonadas + timeout + atendidas
        entrantes = abandonadas + timeout + atendidas
        
        inbound = {
            'entrantes': entrantes,
            'atendidas': atendidas,
            'positivas': atendidas,  # EXIT_ANSWERED representa gestiones positivas
            'en_cola': 0,  # Se obtiene de QUEUE-SIZE
            'abandonadas': abandonadas,
            'timeout': timeout,
            'errores': 0,  # No disponible directamente, placeholder
        }

        # Obtener tamaño de cola (ari-app escribe en DB 0; usar redis_oml_connection si está disponible)
        queue_size_key = f'OML:CALLDATA:QUEUE-SIZE:{campaign_id}'
        queue_conn = redis_oml_connection if redis_oml_connection else redis_calldata_connection
        queue_size = queue_conn.get(queue_size_key) if queue_conn else None
        inbound['en_cola'] = _safe_int(queue_size, 0)

        # Calcular tiempos (AHT, más extensa)
        # T. Promedio (AHT) = OML:CALLDATA:CAMP:{id_camp} (Key: TOTAL_CALL_TIME) / OML:CALLDATA:CAMP:{id_camp} (Key: EXIT_ANSWERED)
        total_call_time = _safe_float(calldata.get('TOTAL_CALL_TIME', 0))
        exit_answered = _safe_int(calldata.get('EXIT_ANSWERED', 0))
        
        if exit_answered > 0:
            aht = total_call_time / exit_answered
        else:
            aht = 0
        
        # Obtener Gestión positiva desde Redis: OML:DISPOSITIONDATA:CAMP:{campaign_id} -> ENGAGED
        gestion_positiva = 0
        try:
            dispositiondata_key = f'OML:DISPOSITIONDATA:CAMP:{campaign_id}'
            engaged_value = redis_calldata_connection.hget(dispositiondata_key, 'ENGAGED')
            if engaged_value:
                gestion_positiva = _safe_int(engaged_value, 0)
        except Exception as e:
            logger.warning(f"Error obteniendo ENGAGED desde Redis para campaña {campaign_id}: {e}")
            gestion_positiva = 0
        
        call_times = {
            'aht': aht,  # Average Handle Time calculado desde Redis
            'mas_extensa': 0,  # Requiere cálculo desde timestamps
            'gestion_positiva': gestion_positiva,  # ENGAGED desde OML:DISPOSITIONDATA:CAMP:{campaign_id}
        }

        # Gestiones (human, bot, mixed) - placeholders hasta confirmar fuente
        gestiones = {
            'human': 0,
            'bot': 0,
            'mixed': 0,
        }

        # Sentimiento (muy bien, bien, regular, mal) - placeholders hasta confirmar fuente
        sentimiento = {
            'muy_bien': 0,
            'bien': 0,
            'regular': 0,
            'mal': 0,
        }

        return {
            'outbound': outbound,
            'inbound': inbound,
            'call_times': call_times,
            'gestiones': gestiones,
            'sentimiento': sentimiento,
        }
    except Exception as e:
        logger.error(f"Error obteniendo métricas de campaña {campaign_id}: {e}")
        return {
            'outbound': {
                'discadas': 0, 'atendidas': 0, 'positivas': 0, 'llamadas_discando': 0, 'contestadores': 0,
                'ocupado': 0, 'timeout': 0, 'canceladas': 0, 'congestion': 0, 'chanunavail': 0, 'num_sin_ruta': 0,
                'errores': 0,
                'shortcall': 0,
            },
            'inbound': {
                'entrantes': 0, 'atendidas': 0, 'positivas': 0, 'en_cola': 0,
                'abandonadas': 0, 'timeout': 0, 'errores': 0,
            },
            'call_times': {'aht': 0, 'mas_extensa': 0, 'gestion_positiva': 0},
            'gestiones': {'human': 0, 'bot': 0, 'mixed': 0},
            'sentimiento': {'muy_bien': 0, 'bien': 0, 'regular': 0, 'mal': 0},
        }


def _get_dialer_status_metrics(redis_dialer_connection, campaign_id):
    """
    Obtiene métricas del estado del discador desde Redis DB3.
    
    Args:
        redis_dialer_connection: Conexión a Redis DB3
        campaign_id: ID de la campaña
    
    Returns:
        dict: Diccionario con las métricas del estado del discador:
            - pending_initial: Contactos pendientes
            - pending_retries: Contactos con reintentos pendientes
            - finalized_no_contact: Finalizados sin contacto
            - contacted_successfully: Contactados exitosamente
            - attempted_calls: Llamadas Discadas
            - answered_pstn: Atendidas en destino
            - answered_agent: Conectadas al agente
    """
    if not campaign_id or not redis_dialer_connection:
        return {
            'pending_initial': 0,
            'pending_retries': 0,
            'finalized_no_contact': 0,
            'contacted_successfully': 0,
            'attempted_calls': 0,
            'answered_pstn': 0,
            'answered_agent': 0,
        }
    
    try:
        # Obtener datos desde Redis DB3 usando HGETALL
        counter_key = f'CAMP:{campaign_id}:COUNTER'
        stats_raw = redis_dialer_connection.hgetall(counter_key)
        
        # Normalizar datos de Redis (convertir bytes a strings si es necesario)
        stats = _normalize_redis_dict(stats_raw)
        
        # Extraer las métricas requeridas
        estado_discador = {
            'pending_initial': _safe_int(stats.get('PENDING_INITIAL_CONTACT_ATTEMPTS', 0), 0),
            'pending_retries': _safe_int(stats.get('NO CONTACTS WITH PENDING ATTEMPTS', 0), 0),
            'finalized_no_contact': _safe_int(stats.get('FINALIZED WITH NO CONTACT', 0), 0),
            'contacted_successfully': _safe_int(stats.get('CONTACTED SUCCESSFULLY', 0), 0),
            'attempted_calls': _safe_int(stats.get('ATTEMPTED_CALLS', 0), 0),
            'answered_pstn': _safe_int(stats.get('ANSWERED_PSTN', 0), 0),
            'answered_agent': _safe_int(stats.get('ANSWERED_AGENT', 0), 0),
        }
        
        return estado_discador
    except Exception as e:
        logger.error(f"Error obteniendo métricas del estado del discador para campaña {campaign_id}: {e}", exc_info=True)
        return {
            'pending_initial': 0,
            'pending_retries': 0,
            'finalized_no_contact': 0,
            'contacted_successfully': 0,
            'attempted_calls': 0,
            'answered_pstn': 0,
            'answered_agent': 0,
        }


def _enrich_agent_list(lista_agentes):
    """Enriquece la lista de agentes con información de la base de datos."""
    if not lista_agentes:
        return []
    
    agent_ids = [agente.get('id') for agente in lista_agentes if agente.get('id')]
    if not agent_ids:
        return lista_agentes
    
    try:
        agentes_db = AgenteProfile.objects.filter(
            id__in=agent_ids
        ).select_related('user', 'grupo').values(
            'id', 'user__first_name', 'user__last_name', 
            'user__username', 'grupo__nombre'
        )
        # Crear diccionario de agentes por ID para acceso rápido
        agentes_dict = {ag['id']: ag for ag in agentes_db}
        
        # Enriquecer cada agente con información de la BD
        for agente in lista_agentes:
            agente_id = agente.get('id')
            if agente_id in agentes_dict:
                agente_db = agentes_dict[agente_id]
                agente['nombre'] = f"{agente_db.get('user__first_name', '')} {agente_db.get('user__last_name', '')}".strip()
                agente['username'] = agente_db.get('user__username', '')
                agente['grupo'] = agente_db.get('grupo__nombre', '')
            else:
                agente['nombre'] = f"Agente {agente_id}"
                agente['username'] = ''
                agente['grupo'] = ''
    except Exception as e:
        logger.warning(f"Error obteniendo nombres de agentes desde BD: {e}")
        # Si falla, usar IDs como nombres
        for agente in lista_agentes:
            if not agente.get('nombre'):
                agente['nombre'] = f"Agente {agente.get('id', 'N/A')}"
    
    return lista_agentes


def validate_campaign_id(request, required=False):
    """
    Valida y retorna el campaign_id del request.
    
    Args:
        request: Django request object
        required: Si True, retorna error si campaign_id no está presente
    
    Returns:
        tuple: (campaign_id, error_response)
        - campaign_id: int o None si no se proporciona
        - error_response: JsonResponse con error o None si es válido
    """
    campaign_id = request.GET.get('campaign_id')
    
    if not campaign_id:
        if required:
            return None, JsonResponse({
                'error': 'campaign_id es requerido',
            }, status=400)
        return None, None
    
    try:
        campaign_id = int(campaign_id)
    except (ValueError, TypeError):
        return None, JsonResponse({
            'error': 'campaign_id debe ser un número válido',
        }, status=400)
    
    # Validar que campaign_id sea positivo
    if campaign_id <= 0:
        return None, JsonResponse({
            'error': 'campaign_id debe ser un número positivo',
        }, status=400)
    
    return campaign_id, None


def dashboard_contact_center_agentes(request):
    """
    Endpoint API que retorna solo métricas agregadas de agentes (sin lista detallada).
    
    Parámetros GET:
    - campaign_id: ID de la campaña (opcional, si no se especifica se obtienen todos los agentes)
    
    Retorna JSON con:
    - logueados, ready, oncall, ringing, onconfer, voicebot
    - timestamp
    """
    try:
        campaign_id, error_response = validate_campaign_id(request, required=False)
        if error_response:
            return error_response

        redis_agent_connection = None
        redis_calldata_connection = None
        try:
            redis_agent_connection = create_redis_connection(db=0)
            redis_agent_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=0 (agentes): {e}")
            redis_agent_connection = None

        try:
            redis_calldata_connection = create_redis_connection(db=2)
            redis_calldata_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=2 (calldata): {e}")
            redis_calldata_connection = None

        agent_metrics = {}
        if redis_agent_connection:
            full_metrics = _get_agent_metrics(redis_agent_connection, campaign_id, redis_calldata_connection)
            # Retornar solo métricas agregadas, sin lista_agentes
            agent_metrics = {
                'logueados': full_metrics.get('logueados', 0),
                'ready': full_metrics.get('ready', 0),
                'oncall': full_metrics.get('oncall', 0),
                'ringing': full_metrics.get('ringing', 0),
                'onconfer': full_metrics.get('onconfer', 0),
                'voicebot': full_metrics.get('voicebot', 0),
            }
        else:
            agent_metrics = {
                'logueados': 0, 'ready': 0, 'oncall': 0,
                'ringing': 0, 'onconfer': 0, 'voicebot': 0,
            }

        return JsonResponse({
            **agent_metrics,
            'timestamp': datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Error en dashboard_contact_center_agentes: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Error obteniendo métricas de agentes',
            'detail': str(e),
        }, status=500)


def dashboard_contact_center_agentes_lista(request):
    """
    Endpoint API que retorna solo la lista detallada de agentes.
    
    Parámetros GET:
    - campaign_id: ID de la campaña (opcional, si no se especifica se obtienen todos los agentes)
    
    Retorna JSON con:
    - lista_agentes: array de agentes con información enriquecida
    - timestamp
    """
    try:
        campaign_id, error_response = validate_campaign_id(request, required=False)
        if error_response:
            return error_response

        redis_agent_connection = None
        redis_calldata_connection = None
        try:
            redis_agent_connection = create_redis_connection(db=0)
            redis_agent_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=0 (agentes): {e}")
            redis_agent_connection = None

        try:
            redis_calldata_connection = create_redis_connection(db=2)
            redis_calldata_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=2 (calldata): {e}")
            redis_calldata_connection = None

        lista_agentes = []
        if redis_agent_connection:
            full_metrics = _get_agent_metrics(redis_agent_connection, campaign_id, redis_calldata_connection)
            lista_agentes = full_metrics.get('lista_agentes', [])
            # Enriquecer con información de la base de datos
            lista_agentes = _enrich_agent_list(lista_agentes)

        return JsonResponse({
            'lista_agentes': lista_agentes,
            'timestamp': datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Error en dashboard_contact_center_agentes_lista: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Error obteniendo lista de agentes',
            'detail': str(e),
        }, status=500)


def dashboard_contact_center_bots_campana(request):
    """
    Endpoint API que retorna la lista de agentes voicebot de la campaña
    con sus llamadas activas desde Redis (OML:CALLDATA:VOICEBOT-CALLS:{id_camp}:{id_agent}).

    Parámetros GET:
    - campaign_id: ID de la campaña (requerido)

    Retorna JSON con:
    - bots: [ { id, nombre, llamadas_activas }, ... ]
    - timestamp
    """
    try:
        campaign_id, error_response = validate_campaign_id(request, required=True)
        if error_response:
            return error_response

        try:
            campana = Campana.objects.get(id=campaign_id)
        except Campana.DoesNotExist:
            return JsonResponse({
                'bots': [],
                'timestamp': datetime.datetime.now().isoformat(),
            })

        agentes_voicebot = campana.obtener_agentes().filter(voicebot=True).select_related('user')
        redis_connection = None
        try:
            redis_connection = create_redis_connection(db=0)
            redis_connection.ping()
        except Exception as e:
            logger.warning(f"Error conectando a Redis db=0 para bots campaña: {e}")

        def _safe_int(val, default=0):
            try:
                return int(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        bots = []
        for agente in agentes_voicebot:
            llamadas_activas = 0
            if redis_connection:
                try:
                    key = f'OML:CALLDATA:VOICEBOT-CALLS:{campaign_id}:{agente.id}'
                    raw = redis_connection.get(key)
                    llamadas_activas = _safe_int(raw, 0)
                except Exception as e:
                    logger.warning(f"Error leyendo Redis VOICEBOT-CALLS para agente {agente.id}: {e}")
            user = getattr(agente, 'user', None)
            if user:
                nombre = (user.get_full_name() or '').strip() or getattr(user, 'username', '') or f'Bot {agente.id}'
            else:
                nombre = f'Bot {agente.id}'
            bots.append({
                'id': agente.id,
                'nombre': nombre,
                'llamadas_activas': llamadas_activas,
            })

        return JsonResponse({
            'bots': bots,
            'timestamp': datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Error en dashboard_contact_center_bots_campana: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Error obteniendo bots de la campaña',
            'detail': str(e),
        }, status=500)


def dashboard_contact_center_llamadas(request):
    """
    Endpoint API que retorna solo métricas de llamadas.
    
    Parámetros GET:
    - campaign_id: ID de la campaña (requerido para métricas de llamadas)
    
    Retorna JSON con:
    - outbound, inbound, call_times, gestiones, sentimiento
    - timestamp
    """
    try:
        campaign_id, error_response = validate_campaign_id(request, required=False)
        if error_response:
            return error_response

        redis_calldata_connection = None
        redis_dialer_connection = None
        redis_oml_connection = None
        try:
            redis_calldata_connection = create_redis_connection(db=2)
            redis_calldata_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=2 (calldata): {e}")
            redis_calldata_connection = None

        try:
            redis_oml_connection = create_redis_connection(db=0)
            redis_oml_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=0 (oml/queue-size): {e}")
            redis_oml_connection = None

        try:
            redis_dialer_connection = create_redis_connection(db=3)
            redis_dialer_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=3 (dialer): {e}")
            redis_dialer_connection = None

        campaign_metrics = {}
        if redis_calldata_connection and campaign_id:
            campaign_metrics = _get_campaign_call_metrics(
                redis_calldata_connection, campaign_id, redis_dialer_connection, redis_oml_connection
            )
        else:
            campaign_metrics = {
                'outbound': {
                    'discadas': 0, 'atendidas': 0, 'atendidas_human': 0, 'atendidas_bot': 0, 'atendidas_mix': 0,
                    'positivas': 0, 'llamadas_discando': 0, 'contestadores': 0,
                    'ocupado': 0, 'timeout': 0, 'canceladas': 0, 'congestion': 0, 'chanunavail': 0, 'num_sin_ruta': 0,
                    'errores': 0,
                    'shortcall': 0,
                },
                'inbound': {
                    'entrantes': 0, 'atendidas': 0, 'positivas': 0, 'en_cola': 0,
                    'abandonadas': 0, 'timeout': 0, 'errores': 0,
                },
                'call_times': {'aht': 0, 'mas_extensa': 0, 'gestion_positiva': 0},
                'gestiones': {'human': 0, 'bot': 0, 'mixed': 0},
                'sentimiento': {'muy_bien': 0, 'bien': 0, 'regular': 0, 'mal': 0},
            }

        # Obtener métricas del estado del discador desde Redis DB3
        estado_discador = {}
        if redis_dialer_connection and campaign_id:
            estado_discador = _get_dialer_status_metrics(redis_dialer_connection, campaign_id)
        else:
            estado_discador = {
                'pending_initial': 0,
                'pending_retries': 0,
                'finalized_no_contact': 0,
                'contacted_successfully': 0,
                'attempted_calls': 0,
                'answered_pstn': 0,
                'answered_agent': 0,
            }

        return JsonResponse({
            **campaign_metrics,
            'estado_discador': estado_discador,
            'timestamp': datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Error en dashboard_contact_center_llamadas: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Error obteniendo métricas de llamadas',
            'detail': str(e),
        }, status=500)


def dashboard_panel_dialer_estado(request):
    """
    Estado Discador completo del Panel Dialer (paridad modal campana_dialer/list).

    GET campaign_id (requerido): campaña TYPE_DIALER asignada al supervisor.
    """
    try:
        campaign_id, error_response = validate_campaign_id(request, required=True)
        if error_response:
            return error_response

        campana = _campanas_panel_dialer_queryset(request.user).filter(id=campaign_id).first()
        if not campana:
            raise Http404

        payload = _panel_dialer_estado_payload(campana)
        return JsonResponse({
            **payload,
            'timestamp': datetime.datetime.now().isoformat(),
        })
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Error en dashboard_panel_dialer_estado: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Error obteniendo estado del discador',
            'detail': str(e),
        }, status=500)


def dashboard_contact_center_data(request):
    """
    Endpoint API que retorna datos del contact center desde Redis.
    
    Parámetros GET:
    - campaign_id: ID de la campaña (opcional, si no se especifica se obtienen todos los agentes)
    
    Retorna JSON con:
    - agentes: métricas de agentes (logueados, ready, oncall, ringing, onconfer, voicebot)
    - llamadas: métricas de llamadas (outbound, inbound, tiempos, gestiones, sentimiento)
    """
    try:
        # Obtener y validar campaign_id del request
        campaign_id, error_response = validate_campaign_id(request, required=False)
        if error_response:
            return error_response

        # Conectar a Redis
        redis_agent_connection = None
        redis_calldata_connection = None

        try:
            redis_agent_connection = create_redis_connection(db=0)
            redis_agent_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=0 (agentes): {e}")
            redis_agent_connection = None

        try:
            redis_calldata_connection = create_redis_connection(db=2)
            redis_calldata_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=2 (calldata): {e}")
            redis_calldata_connection = None

        # Obtener métricas de agentes
        agent_metrics = {}
        if redis_agent_connection:
            agent_metrics = _get_agent_metrics(redis_agent_connection, campaign_id, redis_calldata_connection)
            # Enriquecer lista de agentes con nombres desde la base de datos
            lista_agentes = agent_metrics.get('lista_agentes', [])
            if lista_agentes:
                lista_agentes = _enrich_agent_list(lista_agentes)
                agent_metrics['lista_agentes'] = lista_agentes
        else:
            agent_metrics = {
                'logueados': 0, 'ready': 0, 'oncall': 0,
                'ringing': 0, 'onconfer': 0, 'voicebot': 0,
                'lista_agentes': [],
            }

        # Conectar a Redis DB3 para obtener datos del dialer
        redis_dialer_connection = None
        try:
            redis_dialer_connection = create_redis_connection(db=3)
            redis_dialer_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=3 (dialer): {e}")
            redis_dialer_connection = None

        # Obtener métricas de campaña
        campaign_metrics = {}
        if redis_calldata_connection and campaign_id:
            campaign_metrics = _get_campaign_call_metrics(
                redis_calldata_connection, campaign_id, redis_dialer_connection, redis_agent_connection
            )
        else:
            campaign_metrics = {
                'outbound': {
                    'discadas': 0, 'atendidas': 0, 'atendidas_human': 0, 'atendidas_bot': 0, 'atendidas_mix': 0,
                    'positivas': 0, 'llamadas_discando': 0, 'contestadores': 0,
                    'ocupado': 0, 'timeout': 0, 'canceladas': 0, 'congestion': 0, 'chanunavail': 0, 'num_sin_ruta': 0,
                    'errores': 0,
                    'shortcall': 0,
                },
                'inbound': {
                    'entrantes': 0, 'atendidas': 0, 'positivas': 0, 'en_cola': 0,
                    'abandonadas': 0, 'timeout': 0, 'errores': 0,
                },
                'call_times': {'aht': 0, 'mas_extensa': 0, 'gestion_positiva': 0},
                'gestiones': {'human': 0, 'bot': 0, 'mixed': 0},
                'sentimiento': {'muy_bien': 0, 'bien': 0, 'regular': 0, 'mal': 0},
            }

        # Obtener métricas del estado del discador desde Redis DB3
        estado_discador = {}
        if redis_dialer_connection and campaign_id:
            estado_discador = _get_dialer_status_metrics(redis_dialer_connection, campaign_id)
        else:
            estado_discador = {
                'pending_initial': 0,
                'pending_retries': 0,
                'finalized_no_contact': 0,
                'contacted_successfully': 0,
                'attempted_calls': 0,
                'answered_pstn': 0,
                'answered_agent': 0,
            }

        # Construir respuesta
        response_data = {
            'agentes': agent_metrics,
            'llamadas': campaign_metrics,
            'estado_discador': estado_discador,
            'timestamp': datetime.datetime.now().isoformat(),
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error en dashboard_contact_center_data: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Error obteniendo datos del contact center',
            'detail': str(e),
        }, status=500)


def _get_inbound_detalle_metrics(redis_agent_connection, redis_calldata_connection, campaign_id):
    """
    Obtiene métricas detalladas de inbound para una campaña.
    
    Retorna un diccionario con:
    - nombre_camp: Nombre de la campaña
    - ag_ready: Cantidad de agentes en estado READY
    - ag_oncall: Cantidad de agentes en estado ONCALL
    - ag_pause: Cantidad de agentes en pausa
    - llamadas_ofrecidas: Total de llamadas ofrecidas (entrantes)
    - llamadas_atendidas: Llamadas atendidas
    - llamadas_timeout: Llamadas que expiraron por timeout
    - llamadas_abandonadas: Llamadas abandonadas
    - tiempo_prom_abandono: Tiempo promedio de abandono en segundos
    - tiempo_prom_espera: Tiempo promedio de espera en segundos
    - gestiones_positivas: Gestiones positivas (atendidas)
    """
    if not campaign_id:
        return None
    
    try:
        # Obtener nombre de la campaña desde la base de datos
        try:
            campana = Campana.objects.get(id=campaign_id)
            nombre_camp = campana.nombre
        except Campana.DoesNotExist:
            nombre_camp = f"Campaña {campaign_id}"
        
        # Obtener agentes de la campaña y contar por estado
        ag_ready = 0
        ag_oncall = 0
        ag_pause = 0
        
        if redis_agent_connection:
            campaign_agents_key = f'OML:CAMPAIGN-AGENTS:{campaign_id}'
            agent_ids = redis_agent_connection.smembers(campaign_agents_key)
            
            # Optimización: usar pipeline para obtener STATUS de todos los agentes en una sola operación
            if agent_ids:
                pipeline = redis_agent_connection.pipeline()
                for agent_id in agent_ids:
                    agent_key = f'OML:AGENT:{agent_id}'
                    pipeline.hget(agent_key, 'STATUS')
                
                # Ejecutar pipeline y obtener todos los STATUS en una sola operación
                try:
                    statuses = pipeline.execute()
                    
                    # Procesar resultados
                    for status in statuses:
                        if not status:
                            continue
                        status = status.decode('utf-8') if isinstance(status, bytes) else status
                        
                        if status == 'READY':
                            ag_ready += 1
                        elif status == 'ONCALL':
                            ag_oncall += 1
                        elif status.startswith('PAUSE'):
                            ag_pause += 1
                except Exception:
                    # Fallback: si el pipeline falla, usar método individual con hget (más eficiente que hgetall)
                    for agent_id in agent_ids:
                        try:
                            agent_key = f'OML:AGENT:{agent_id}'
                            status = redis_agent_connection.hget(agent_key, 'STATUS')
                            
                            if not status:
                                continue
                            status = status.decode('utf-8') if isinstance(status, bytes) else status
                            
                            if status == 'READY':
                                ag_ready += 1
                            elif status == 'ONCALL':
                                ag_oncall += 1
                            elif status.startswith('PAUSE'):
                                ag_pause += 1
                        except Exception:
                            continue
        
        # Obtener métricas de llamadas desde Redis
        llamadas_ofrecidas = 0
        llamadas_atendidas = 0
        llamadas_timeout = 0
        llamadas_abandonadas = 0
        tiempo_prom_abandono = 0
        tiempo_prom_espera = 0
        gestiones_positivas = 0
        
        if redis_calldata_connection:
            # Obtener datos del hash CALLDATA:CAMP
            calldata_key = f'OML:CALLDATA:CAMP:{campaign_id}'
            calldata_raw = redis_calldata_connection.hgetall(calldata_key)
            # Normalizar datos de Redis (convertir bytes a strings si es necesario)
            calldata = _normalize_redis_dict(calldata_raw)
            
            # Para inbound, usar CALL_TYPE:3 (TYPE_ENTRANTE = 3)
            # El logger escribe EXIT_ANSWERED_HUMAN/BOT/MIX, no EXIT_ANSWERED genérico
            llamadas_abandonadas = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ABANDON', 0)) + _safe_int(
                calldata.get('CALL_TYPE:3:EXIT_HANDOFF_ABANDON', 0)
            )
            llamadas_timeout = _safe_int(calldata.get('CALL_TYPE:3:EXIT_TIMEOUT', 0)) + _safe_int(
                calldata.get('CALL_TYPE:3:EXIT_HANDOFF_TIMEOUT', 0)
            )
            exit_answered_human = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ANSWERED_HUMAN', 0))
            exit_answered_bot = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ANSWERED_BOT', 0))
            exit_answered_mix = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ANSWERED_MIX', 0))
            exit_answered = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ANSWERED', 0))
            if exit_answered_human + exit_answered_bot + exit_answered_mix > 0:
                llamadas_atendidas = exit_answered_human + exit_answered_bot + exit_answered_mix
            else:
                llamadas_atendidas = exit_answered
            
            # Llamadas ofrecidas = suma de todas las que entraron a la cola
            # Intentar obtener desde ENTERQUEUE, si no está disponible, usar suma
            llamadas_ofrecidas = llamadas_atendidas + llamadas_abandonadas + llamadas_timeout
            
            # Intentar obtener desde ENTERQUEUE si está disponible
            try:
                # Buscar todas las keys que coincidan con CALL_TYPE:*:ENTERQUEUE
                scan_result = redis_calldata_connection.hscan(calldata_key, 0, match='CALL_TYPE:*:ENTERQUEUE')
                if scan_result and scan_result[1]:
                    llamadas_ofrecidas = sum([int(v) for v in scan_result[1].values()])
            except Exception:
                # Si falla, usar la suma calculada anteriormente
                pass
            
            # Gestiones positivas = llamadas atendidas (EXIT_ANSWERED)
            gestiones_positivas = llamadas_atendidas
            
            # Calcular tiempo promedio de abandono
            # Fórmula: CALL_TYPE:3:ABANDON_WAIT_TOTAL_TIME / CALL_TYPE:3:EXIT_ABANDON
            abandon_wait_total_time = _safe_float(calldata.get('CALL_TYPE:3:ABANDON_WAIT_TOTAL_TIME', 0))
            exit_abandon = _safe_int(calldata.get('CALL_TYPE:3:EXIT_ABANDON', 0)) + _safe_int(
                calldata.get('CALL_TYPE:3:EXIT_HANDOFF_ABANDON', 0)
            )
            if exit_abandon > 0:
                tiempo_prom_abandono = abandon_wait_total_time / exit_abandon
            else:
                tiempo_prom_abandono = 0
            
            # Calcular tiempo promedio de espera
            # Fórmula: CALL_TYPE:3:BRIDGE_WAIT_TOTAL_TIME / llamadas_atendidas
            bridge_wait_total_time = _safe_float(calldata.get('CALL_TYPE:3:BRIDGE_WAIT_TOTAL_TIME', 0))
            if llamadas_atendidas > 0:
                tiempo_prom_espera = bridge_wait_total_time / llamadas_atendidas
            else:
                tiempo_prom_espera = 0
        
        return {
            'nombre_camp': nombre_camp,
            'ag_ready': ag_ready,
            'ag_oncall': ag_oncall,
            'ag_pause': ag_pause,
            'llamadas_ofrecidas': llamadas_ofrecidas,
            'llamadas_atendidas': llamadas_atendidas,
            'llamadas_timeout': llamadas_timeout,
            'llamadas_abandonadas': llamadas_abandonadas,
            'tiempo_prom_abandono': tiempo_prom_abandono,
            'tiempo_prom_espera': tiempo_prom_espera,
            'gestiones_positivas': gestiones_positivas,
        }
    except Exception as e:
        logger.error(f"Error obteniendo métricas detalladas de inbound para campaña {campaign_id}: {e}", exc_info=True)
        return None


def dashboard_contact_center_inbound_detalle(request):
    """
    Endpoint API que retorna métricas detalladas de inbound para la campaña seleccionada.
    
    Parámetros GET:
    - campaign_id: ID de la campaña (requerido)
    
    Retorna JSON con métricas detalladas de inbound.
    """
    try:
        campaign_id, error_response = validate_campaign_id(request, required=True)
        if error_response:
            return error_response

        redis_agent_connection = None
        redis_calldata_connection = None

        try:
            redis_agent_connection = create_redis_connection(db=0)
            redis_agent_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=0 (agentes): {e}")
            redis_agent_connection = None

        try:
            redis_calldata_connection = create_redis_connection(db=2)
            redis_calldata_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=2 (calldata): {e}")
            redis_calldata_connection = None

        inbound_detalle = None
        if redis_agent_connection or redis_calldata_connection:
            inbound_detalle = _get_inbound_detalle_metrics(
                redis_agent_connection, 
                redis_calldata_connection, 
                campaign_id
            )
        
        if inbound_detalle is None:
            inbound_detalle = {
                'nombre_camp': '',
                'ag_ready': 0,
                'ag_oncall': 0,
                'ag_pause': 0,
                'llamadas_ofrecidas': 0,
                'llamadas_atendidas': 0,
                'llamadas_timeout': 0,
                'llamadas_abandonadas': 0,
                'tiempo_prom_abandono': 0,
                'tiempo_prom_espera': 0,
                'gestiones_positivas': 0,
            }

        return JsonResponse({
            **inbound_detalle,
            'timestamp': datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Error en dashboard_contact_center_inbound_detalle: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Error obteniendo métricas detalladas de inbound',
            'detail': str(e),
        }, status=500)


def _get_outbound_detalle_metrics(redis_agent_connection, redis_calldata_connection, campaign_id):
    """
    Obtiene métricas detalladas de outbound para una campaña.
    
    Retorna un diccionario con:
    - nombre_camp: Nombre de la campaña
    - ag_ready: Cantidad de agentes en estado READY
    - ag_oncall: Cantidad de agentes en estado ONCALL
    - ag_pause: Cantidad de agentes en pausa
    - att: Average Talk Time (tiempo promedio de conversación)
    - discadas: Total de llamadas discadas
    - contactadas: Llamadas que fueron contactadas (contestadas)
    - contestadores: Llamadas que fueron a contestador
    - busy: Llamadas que encontraron ocupado
    - congestion: Llamadas con congestión
    - otro_error: Otros errores
    - tiempo_prom_abandono: Tiempo promedio de abandono en segundos
    - tiempo_prom_espera: Tiempo promedio de espera en segundos
    - gestiones_positivas: Gestiones positivas (atendidas)
    """
    if not campaign_id:
        return None
    
    try:
        # Obtener nombre de la campaña desde la base de datos
        try:
            campana = Campana.objects.get(id=campaign_id)
            nombre_camp = campana.nombre
        except Campana.DoesNotExist:
            nombre_camp = f"Campaña {campaign_id}"
        
        # Obtener agentes de la campaña y contar por estado
        ag_ready = 0
        ag_oncall = 0
        ag_pause = 0
        
        if redis_agent_connection:
            campaign_agents_key = f'OML:CAMPAIGN-AGENTS:{campaign_id}'
            agent_ids = redis_agent_connection.smembers(campaign_agents_key)
            
            # Optimización: usar pipeline para obtener STATUS de todos los agentes en una sola operación
            if agent_ids:
                pipeline = redis_agent_connection.pipeline()
                for agent_id in agent_ids:
                    agent_key = f'OML:AGENT:{agent_id}'
                    pipeline.hget(agent_key, 'STATUS')
                
                # Ejecutar pipeline y obtener todos los STATUS en una sola operación
                try:
                    statuses = pipeline.execute()
                    
                    # Procesar resultados
                    for status in statuses:
                        if not status:
                            continue
                        status = status.decode('utf-8') if isinstance(status, bytes) else status
                        
                        if status == 'READY':
                            ag_ready += 1
                        elif status == 'ONCALL':
                            ag_oncall += 1
                        elif status.startswith('PAUSE'):
                            ag_pause += 1
                except Exception:
                    # Fallback: si el pipeline falla, usar método individual con hget (más eficiente que hgetall)
                    for agent_id in agent_ids:
                        try:
                            agent_key = f'OML:AGENT:{agent_id}'
                            status = redis_agent_connection.hget(agent_key, 'STATUS')
                            
                            if not status:
                                continue
                            status = status.decode('utf-8') if isinstance(status, bytes) else status
                            
                            if status == 'READY':
                                ag_ready += 1
                            elif status == 'ONCALL':
                                ag_oncall += 1
                            elif status.startswith('PAUSE'):
                                ag_pause += 1
                        except Exception:
                            continue
        
        # Obtener métricas de llamadas desde Redis
        # Inicializar con valores por defecto
        att = 0
        discadas = 0
        contactadas = 0
        contestadores = 0
        busy = 0
        congestion = 0
        otro_error = 0
        tiempo_prom_abandono = 0
        tiempo_prom_espera = 0
        gestiones_positivas = 0
        
        if redis_calldata_connection:
            # Obtener datos del hash CALLDATA:CAMP desde Redis DB2
            calldata_key = f'OML:CALLDATA:CAMP:{campaign_id}'
            calldata_raw = redis_calldata_connection.hgetall(calldata_key)
            # Normalizar datos de Redis (convertir bytes a strings si es necesario)
            calldata = _normalize_redis_dict(calldata_raw)
            
            # Para outbound, leer CALL_TYPE:2 (llamadas salientes manuales) y CALL_TYPE:1
            # También considerar CALL_TYPE:5 para AMD (Answering Machine Detection)
            
            # Discadas = total de llamadas discadas
            # Sumar CALL_TYPE:2:DIAL (manual) y CALL_TYPE:1:DIAL
            dial_type2 = _safe_int(calldata.get('CALL_TYPE:2:DIAL', 0))
            dial_type1 = _safe_int(calldata.get('CALL_TYPE:1:DIAL', 0))
            dial_out = _safe_int(calldata.get('DIAL_OUT', 0))
            discadas = dial_type2 + dial_type1
            if discadas == 0:
                discadas = dial_out
            
            # Contactadas = llamadas atendidas (EXIT_ANSWERED)
            # Sumar CALL_TYPE:2:EXIT_ANSWERED y CALL_TYPE:1:EXIT_ANSWERED
            exit_answered_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_ANSWERED', 0))
            exit_answered_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_ANSWERED', 0))
            contactadas = exit_answered_type2 + exit_answered_type1
            
            # Contestadores = llamadas que fueron a contestador (AMD - Answering Machine Detection)
            # Usar CALL_TYPE:5:EXIT_AMD
            contestadores = _safe_int(calldata.get('CALL_TYPE:2:EXIT_AMD', 0))
            
            # Busy = llamadas que encontraron ocupado
            # Sumar CALL_TYPE:2:BUSY, CALL_TYPE:2:EXIT_BUSY, CALL_TYPE:1:EXIT_BUSY
            busy_type2 = _safe_int(calldata.get('CALL_TYPE:2:BUSY', 0))
            exit_busy_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_BUSY', 0))
            exit_busy_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_BUSY', 0))
            busy = busy_type2 + exit_busy_type2 + exit_busy_type1
            
            # Congestion = llamadas con congestión
            # Buscar EXIT_CONGESTION en ambos tipos
            exit_congestion_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_CONGESTION', 0))
            exit_congestion_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_CONGESTION', 0))
            congestion = exit_congestion_type2 + exit_congestion_type1
            
            # NOANSWER = llamadas sin respuesta
            noanswer_type2 = _safe_int(calldata.get('CALL_TYPE:2:NOANSWER', 0))
            noanswer_type1 = _safe_int(calldata.get('CALL_TYPE:1:NOANSWER', 0))
            noanswer = noanswer_type2 + noanswer_type1
            
            # Otro Error = calcular como diferencia entre discadas y todas las salidas conocidas
            exit_timeout_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_TIMEOUT', 0))
            exit_timeout_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_TIMEOUT', 0))
            exit_handoff_timeout_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_HANDOFF_TIMEOUT', 0))
            exit_handoff_timeout_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_HANDOFF_TIMEOUT', 0))
            exit_abandon_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_ABANDON', 0))
            exit_abandon_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_ABANDON', 0))
            exit_handoff_abandon_type2 = _safe_int(calldata.get('CALL_TYPE:2:EXIT_HANDOFF_ABANDON', 0))
            exit_handoff_abandon_type1 = _safe_int(calldata.get('CALL_TYPE:1:EXIT_HANDOFF_ABANDON', 0))
            
            total_exits = (exit_answered_type2 + exit_answered_type1 + 
                          exit_timeout_type2 + exit_timeout_type1 +
                          exit_handoff_timeout_type2 + exit_handoff_timeout_type1 +
                          exit_abandon_type2 + exit_abandon_type1 +
                          exit_handoff_abandon_type2 + exit_handoff_abandon_type1 +
                          exit_busy_type2 + exit_busy_type1 +
                          exit_congestion_type2 + exit_congestion_type1 +
                          noanswer + contestadores)
            
            otro_error = discadas - total_exits
            if otro_error < 0:
                otro_error = 0
            
            # Gestiones positivas = llamadas atendidas (EXIT_ANSWERED)
            gestiones_positivas = exit_answered_type2 + exit_answered_type1
            
            # Calcular ATT (Average Talk Time)
            # Sumar tiempos de ambos tipos y dividir por total de atendidas
            answered_total_time_type2 = _safe_float(calldata.get('CALL_TYPE:2:ANSWERED_TOTAL_TIME', 0))
            answered_total_time_type1 = _safe_float(calldata.get('CALL_TYPE:1:ANSWERED_TOTAL_TIME', 0))
            total_answered_time = answered_total_time_type2 + answered_total_time_type1
            total_exit_answered = exit_answered_type2 + exit_answered_type1
            
            if total_exit_answered > 0:
                att = total_answered_time / total_exit_answered
            else:
                att = 0
            
            # Calcular tiempo promedio de abandono
            # Sumar tiempos de abandono de ambos tipos
            abandon_wait_total_time_type2 = _safe_float(calldata.get('CALL_TYPE:2:ABANDON_WAIT_TOTAL_TIME', 0))
            abandon_wait_total_time_type1 = _safe_float(calldata.get('CALL_TYPE:1:ABANDON_WAIT_TOTAL_TIME', 0))
            total_abandon_wait_time = abandon_wait_total_time_type2 + abandon_wait_total_time_type1
            total_exit_abandon = (
                exit_abandon_type2
                + exit_abandon_type1
                + exit_handoff_abandon_type2
                + exit_handoff_abandon_type1
            )
            
            if total_exit_abandon > 0:
                tiempo_prom_abandono = total_abandon_wait_time / total_exit_abandon
            else:
                tiempo_prom_abandono = 0
            
            # Calcular tiempo promedio de espera
            # Sumar tiempos de espera de ambos tipos
            bridge_wait_total_time_type2 = _safe_float(calldata.get('CALL_TYPE:2:BRIDGE_WAIT_TOTAL_TIME', 0))
            bridge_wait_total_time_type1 = _safe_float(calldata.get('CALL_TYPE:1:BRIDGE_WAIT_TOTAL_TIME', 0))
            total_bridge_wait_time = bridge_wait_total_time_type2 + bridge_wait_total_time_type1
            
            if total_exit_answered > 0:
                tiempo_prom_espera = total_bridge_wait_time / total_exit_answered
            else:
                tiempo_prom_espera = 0
        
        return {
            'nombre_camp': nombre_camp,
            'ag_ready': ag_ready,
            'ag_oncall': ag_oncall,
            'ag_pause': ag_pause,
            'att': att,
            'discadas': discadas,
            'contactadas': contactadas,
            'contestadores': contestadores,
            'busy': busy,
            'congestion': congestion,
            'otro_error': otro_error,
            'tiempo_prom_abandono': tiempo_prom_abandono,
            'tiempo_prom_espera': tiempo_prom_espera,
            'gestiones_positivas': gestiones_positivas,
        }
    except Exception as e:
        logger.error(f"Error obteniendo métricas detalladas de outbound para campaña {campaign_id}: {e}", exc_info=True)
        # En caso de error, retornar un objeto con valores por defecto pero con el nombre de la campaña
        try:
            campana = Campana.objects.get(id=campaign_id)
            nombre_camp = campana.nombre
        except Campana.DoesNotExist:
            nombre_camp = f"Campaña {campaign_id}"
        
        return {
            'nombre_camp': nombre_camp,
            'ag_ready': 0,
            'ag_oncall': 0,
            'ag_pause': 0,
            'att': 0,
            'discadas': 0,
            'contactadas': 0,
            'contestadores': 0,
            'busy': 0,
            'congestion': 0,
            'otro_error': 0,
            'tiempo_prom_abandono': 0,
            'tiempo_prom_espera': 0,
            'gestiones_positivas': 0,
        }


def dashboard_contact_center_outbound_detalle(request):
    """
    Endpoint API que retorna métricas detalladas de outbound para la campaña seleccionada.
    
    Parámetros GET:
    - campaign_id: ID de la campaña (requerido)
    
    Retorna JSON con métricas detalladas de outbound.
    """
    try:
        campaign_id, error_response = validate_campaign_id(request, required=True)
        if error_response:
            return error_response

        redis_agent_connection = None
        redis_calldata_connection = None

        try:
            redis_agent_connection = create_redis_connection(db=0)
            redis_agent_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=0 (agentes): {e}")
            redis_agent_connection = None

        try:
            redis_calldata_connection = create_redis_connection(db=2)
            redis_calldata_connection.ping()
        except Exception as e:
            logger.error(f"Error conectando a Redis db=2 (calldata): {e}")
            redis_calldata_connection = None

        # Siempre intentar obtener métricas, incluso si no hay conexión a Redis
        # La función manejará internamente la falta de conexión
        outbound_detalle = _get_outbound_detalle_metrics(
            redis_agent_connection, 
            redis_calldata_connection, 
            campaign_id
        )
        
        # Si la función retorna None (por error), usar valores por defecto
        if outbound_detalle is None:
            # Intentar obtener al menos el nombre de la campaña
            try:
                campana = Campana.objects.get(id=campaign_id)
                nombre_camp = campana.nombre
            except Campana.DoesNotExist:
                nombre_camp = f"Campaña {campaign_id}"
            
            outbound_detalle = {
                'nombre_camp': nombre_camp,
                'ag_ready': 0,
                'ag_oncall': 0,
                'ag_pause': 0,
                'att': 0,
                'discadas': 0,
                'contactadas': 0,
                'contestadores': 0,
                'busy': 0,
                'congestion': 0,
                'otro_error': 0,
                'tiempo_prom_abandono': 0,
                'tiempo_prom_espera': 0,
                'gestiones_positivas': 0,
            }

        return JsonResponse({
            **outbound_detalle,
            'timestamp': datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Error en dashboard_contact_center_outbound_detalle: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Error obteniendo métricas detalladas de outbound',
            'detail': str(e),
        }, status=500)
