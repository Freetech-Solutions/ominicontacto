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

import threading
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _
from django.utils.timezone import now

from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from constance import config as config_constance

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.services.dialer.wombat_api import WombatReloader
from ominicontacto_app.services.dialer import wombat_habilitado, get_dialer_service
from ominicontacto_app.services.redis.connection import create_redis_connection
from ominicontacto_app.models import Campana
from supervision_app.services.data_management import DialerDataManager


class ReiniciarWombat(APIView):
    """Reinicia el servicio de Wombat"""
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    renderer_classes = (JSONRenderer, )
    http_method_names = ['post']

    def post(self, request):
        if not config_constance.WOMBAT_DIALER_ALLOW_REFRESH:
            raise PermissionDenied
        state = config_constance.WOMBAT_DIALER_STATE
        msg = _('Refrescando. Espere al menos 15 segundos mientras finaliza el proceso.')
        if state in [WombatReloader.STATE_DOWN, WombatReloader.STATE_STARTING]:
            return Response(data={
                'status': 'ERROR',
                'OML-state': state,
                'message': msg
            })

        # Hilo para efectuar el restart
        reloader = WombatReloader()
        thread_restart = threading.Thread(
            target=reloader.reload,
            # args=[key_task, ]
        )
        thread_restart.setDaemon(True)
        thread_restart.start()
        return Response(data={
            'status': 'OK',
            'OML-state': WombatReloader.STATE_STARTING,
            'message': msg,
        })


class WombatState(APIView):
    """ Informa el estado del servicio de Wombat """
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    renderer_classes = (JSONRenderer, )
    http_method_names = ['get']

    def get(self, request):
        if not config_constance.WOMBAT_DIALER_ALLOW_REFRESH:
            raise PermissionDenied
        service = WombatReloader()
        wd_state, real_state, uptime = service.synchronize_local_state()
        response_data = {
            'status': 'OK',
            'OML-state': config_constance.WOMBAT_DIALER_STATE,
            'state': real_state if real_state else 'ERROR',
        }
        if wd_state is not None:
            response_data['uptime'] = wombat_uptime_str()
        else:
            msg = _('Refrescando. Espere al menos 15 segundos mientras finaliza el proceso.')
            response_data['message'] = msg

        return Response(data=response_data)


class WombatStart(APIView):
    """ Envía orden de Start a Wombat """
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    renderer_classes = (JSONRenderer, )
    http_method_names = ['post']

    def post(self, request):
        if not config_constance.WOMBAT_DIALER_ALLOW_REFRESH:
            raise PermissionDenied
        service = WombatReloader()
        response = service.force_start_dialer()
        response['OML-state'] = config_constance.WOMBAT_DIALER_STATE
        if response and 'state' in response:
            response['uptime'] = wombat_uptime_str()
            return Response(data=response)

        return Response({'state': 'ERROR'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WombatStop(APIView):
    """ Informa el estado del servicio de Wombat """
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    renderer_classes = (JSONRenderer, )
    http_method_names = ['post']

    def post(self, request):
        if not config_constance.WOMBAT_DIALER_ALLOW_REFRESH:
            raise PermissionDenied
        service = WombatReloader()
        state = service.stop_dialer()
        if state is None:
            return Response({'state': 'ERROR'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response_data = {
            'status': 'OK',
            'state': state,
            'OML-state': state,
            'uptime': wombat_uptime_str()
        }

        return Response(data=response_data)


def wombat_uptime_str():
    uptime = now() - config_constance.WOMBAT_DIALER_UPDATE_DATETIME
    return str(uptime).split('.')[0]


class SupervisionWombatDialerStats(APIView):
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    renderer_classes = (JSONRenderer, )
    http_method_names = ['get']

    def _current_campaigns(self, user):
        if user.get_is_administrador():
            campaigns = Campana.objects.obtener_actuales()
        else:
            supervisor = user.get_supervisor_profile()
            campaigns = supervisor.campanas_asignadas_actuales()
        return campaigns.filter(type=Campana.TYPE_DIALER).filter(
            estado__in=[Campana.ESTADO_ACTIVA, Campana.ESTADO_PAUSADA, Campana.ESTADO_INACTIVA])

    def get(self, request):
        if not wombat_habilitado():
            return Response(data={'status': 'ERROR', 'message': 'Only with Wombat Enabled'},
                            status=status.HTTP_405_METHOD_NOT_ALLOWED)

        campaigns = self._current_campaigns(request.user)
        data = {
            'status': 'OK',
            'statuses': {},
            'channels': {},
        }
        data_manager = DialerDataManager(None, create_redis_connection(db=2))
        calldata_by_id = data_manager.get_campaigns_calldata(campaigns)
        campaigns_by_id = {}
        for campaign in campaigns:
            campaigns_by_id[campaign.id] = campaign
            data['statuses'][campaign.id] = campaign.estado
            channels = data_manager.compute_channels_from_calldata(calldata_by_id[campaign.id])
            data['channels'][campaign.id] = channels
        dialer_service = get_dialer_service()
        pendings_by_id = dialer_service.obtener_llamadas_pendientes_por_id(campaigns_by_id)
        data['pendings'] = pendings_by_id
        return Response(data)
