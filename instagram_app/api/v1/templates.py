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
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext as _
from rest_framework import response, status, viewsets
from rest_framework.authentication import SessionAuthentication

from api_app.authentication import ExpiringTokenAuthentication
from facebook_meta_app.api.v1.templates_messenger import ListSerializer as PlantillaSerializer
from instagram_app.api.permissions import TienePermisoCanalInstagramAgente
from instagram_app.api.utils import HttpResponseStatus, get_response_data
from ominicontacto_app.models import Campana


class ViewSet(viewsets.ViewSet):
    permission_classes = [TienePermisoCanalInstagramAgente]
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)

    def _get_template_group(self, campana):
        try:
            instagram_config = campana.configuracion_instagram
            if instagram_config and instagram_config.grupo_plantilla_facebook:
                return instagram_config.grupo_plantilla_facebook
        except ObjectDoesNotExist:
            pass

        try:
            facebook_config = campana.configuracion_meta_facebook
            if facebook_config and facebook_config.grupo_plantilla_facebook:
                return facebook_config.grupo_plantilla_facebook
        except ObjectDoesNotExist:
            pass

        return None

    def list(self, request, campana_pk):
        try:
            campana = Campana.objects.get(pk=campana_pk)
            template_group = self._get_template_group(campana)
            templates = template_group.plantillas.all() if template_group else []
            serializer = PlantillaSerializer(templates, many=True)
            data = {
                'instagram_templates': serializer.data,
            }
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se obtuvieron los templates de forma exitosa'),
                    data=data),
                status=status.HTTP_200_OK)
        except Exception as e:
            return response.Response(
                data=get_response_data(message=_(str(e))),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
