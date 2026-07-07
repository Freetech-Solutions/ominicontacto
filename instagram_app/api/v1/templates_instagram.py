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
from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import response, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication

from api_app.authentication import ExpiringTokenAuthentication
from api_app.views.permissions import TienePermisoOML
from instagram_app.api.utils import HttpResponseStatus, get_response_data
from instagram_app.models import PlantillaInstagram


class ListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(source='nombre')
    type = serializers.IntegerField(source='tipo')
    configuration = serializers.JSONField(source='configuracion')


class CreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='nombre')
    type = serializers.IntegerField(source='tipo')
    configuration = serializers.JSONField(source='configuracion')

    class Meta:
        model = PlantillaInstagram
        fields = ['id', 'name', 'type', 'configuration']

    def validate_configuracion(self, configuration):
        tipo = self.initial_data.get('type')
        if tipo not in [PlantillaInstagram.TIPO_TEXT]:
            raise serializers.ValidationError({'tipo': _('No soportado por el momento')})
        if 'type' not in configuration or configuration['type'] != 'text' \
                or 'text' not in configuration:
            raise serializers.ValidationError({
                'error': _('Configuración incorrecta para el tipo de mensaje')})
        return configuration


class RetrieveSerializer(ListSerializer):
    pass


class UpdateSerializer(CreateSerializer):
    def validate_configuracion(self, configuracion):
        tipo = self.initial_data.get('type', self.instance.tipo)
        if tipo not in [PlantillaInstagram.TIPO_TEXT]:
            raise serializers.ValidationError({'tipo': _('No soportado por el momento')})
        if 'type' not in configuracion or configuracion['type'] != 'text' \
                or 'text' not in configuracion:
            raise serializers.ValidationError({
                'error': _('Configuración incorrecta para el tipo de mensaje')})
        return configuracion


class ViewSet(viewsets.ViewSet):
    permission_classes = [TienePermisoOML]
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)

    def list(self, request):
        queryset = PlantillaInstagram.objects.filter(is_active=True)
        serializer = ListSerializer(queryset, many=True)
        return response.Response(
            data=get_response_data(
                status=HttpResponseStatus.SUCCESS,
                message=_('Se obtuvieron las plantillas de forma exitosa'),
                data=serializer.data),
            status=status.HTTP_200_OK)

    def create(self, request):
        serializer = CreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(is_active=True)
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se creó la plantilla de forma exitosa'),
                    data=serializer.data),
                status=status.HTTP_201_CREATED)
        return response.Response(
            data=get_response_data(message=_('Error en los datos'), errors=serializer.errors),
            status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk):
        try:
            instance = PlantillaInstagram.objects.filter(is_active=True).get(pk=pk)
        except PlantillaInstagram.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Plantilla no encontrada')),
                status=status.HTTP_404_NOT_FOUND)
        serializer = RetrieveSerializer(instance)
        return response.Response(
            data=get_response_data(
                status=HttpResponseStatus.SUCCESS,
                data=serializer.data,
                message=_('Se obtuvo la plantilla de forma exitosa')),
            status=status.HTTP_200_OK)

    def update(self, request, pk):
        try:
            instance = PlantillaInstagram.objects.filter(is_active=True).get(pk=pk)
        except PlantillaInstagram.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Plantilla no encontrada')),
                status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateSerializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    data=serializer.data,
                    message=_('Se actualizó la plantilla de forma exitosa')),
                status=status.HTTP_200_OK)
        return response.Response(
            data=get_response_data(message=_('Error en los datos'), errors=serializer.errors),
            status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk):
        try:
            instance = PlantillaInstagram.objects.filter(is_active=True).get(pk=pk)
            instance.delete()
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se eliminó la plantilla de forma exitosa')),
                status=status.HTTP_200_OK)
        except PlantillaInstagram.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Plantilla no encontrada')),
                status=status.HTTP_404_NOT_FOUND)
        except models.ProtectedError as exc:
            return response.Response(
                data=get_response_data(
                    message=_(
                        "No está permitido eliminar la plantilla porque está siendo usada "
                        "por {related}.".format(
                            related=", ".join(str(o) for o in exc.protected_objects)))),
                status=status.HTTP_400_BAD_REQUEST)
