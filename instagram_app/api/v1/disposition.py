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
from django.utils import timezone
from django.utils.translation import ugettext as _
from rest_framework import decorators, response, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework import serializers

from facebook_meta_app.api.v1.campaign import ListSerializer as CampaignSerializer
from facebook_meta_app.api.v1.disposition import (
    AgentSerializer,
    CreateSerializer,
    OpcionCalificacionSerializer,
    RespuestaFormularioGestionCreateSerilializer,
    RespuestaFormularioGestionSerilializer,
    RespuestaFormularioGestionUpdateSerilializer,
    UpdateSerializer,
)
from instagram_app.api.permissions import TienePermisoCanalInstagramAgente
from instagram_app.api.utils import HttpResponseStatus, get_response_data
from instagram_app.api.v1.contact import ListSerializer as ContactSerializer
from instagram_app.models import ConversationInstagramApp
from ominicontacto_app.models import (
    CalificacionCliente,
    HistoricalRespuestaFormularioGestion,
    OpcionCalificacion,
    RespuestaFormularioGestion,
)
from orquestador_app.core.instagram.send_message import autoresponse_goodbye


class ListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    contact = serializers.SerializerMethodField()
    agent = serializers.SerializerMethodField()
    comments = serializers.CharField(source='observaciones')
    respuesta_formulario_gestion = serializers.SerializerMethodField()
    disposition_data = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source='created')
    updated_at = serializers.DateTimeField(source='modified')
    campaign = serializers.SerializerMethodField()

    def get_campaign(self, obj):
        if obj.opcion_calificacion:
            return CampaignSerializer(obj.opcion_calificacion.campana).data
        return None

    def get_disposition_data(self, obj):
        if obj.opcion_calificacion:
            return OpcionCalificacionSerializer(obj.opcion_calificacion).data
        return None

    def get_agent(self, obj):
        if obj.agente:
            return AgentSerializer(obj.agente).data
        return None

    def get_respuesta_formulario_gestion(self, obj):
        if obj.opcion_calificacion.tipo == OpcionCalificacion.GESTION:
            respuesta_history = HistoricalRespuestaFormularioGestion.objects.filter(
                history_change_reason=obj.history_id)
            return RespuestaFormularioGestionSerilializer(respuesta_history, many=True).data
        return {}

    def get_contact(self, obj):
        if obj.contacto:
            return ContactSerializer(obj.contacto).data
        return None


class RetrieveSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    agent = serializers.SerializerMethodField()
    contact = serializers.SerializerMethodField()
    comments = serializers.CharField(source='observaciones')
    form_response = serializers.SerializerMethodField()
    disposition_data = serializers.SerializerMethodField()
    campaign = serializers.SerializerMethodField()

    def get_campaign(self, obj):
        if obj.opcion_calificacion:
            return CampaignSerializer(obj.opcion_calificacion.campana).data
        return None

    def get_agent(self, obj):
        if obj.agente:
            return AgentSerializer(obj.agente).data
        return None

    def get_contact(self, obj):
        if obj.contacto:
            return ContactSerializer(obj.contacto).data
        return None

    def get_disposition_data(self, obj):
        if obj.opcion_calificacion:
            return OpcionCalificacionSerializer(obj.opcion_calificacion).data
        return None

    def get_form_response(self, obj):
        if obj.opcion_calificacion.tipo == OpcionCalificacion.GESTION:
            respuesta = RespuestaFormularioGestion.objects.filter(calificacion=obj).last()
            return RespuestaFormularioGestionSerilializer(respuesta).data if respuesta else {}
        return {}


class ViewSet(viewsets.ViewSet):
    permission_classes = [TienePermisoCanalInstagramAgente]
    authentication_classes = (SessionAuthentication, )

    def _finalize_conversation(self, conversation_id, calificacion, timestamp, send_goodbye=True):
        conversation = ConversationInstagramApp.objects.get(id=conversation_id)
        if not conversation.is_disposition:
            conversation.is_disposition = True
            if send_goodbye:
                autoresponse_goodbye(conversation, timestamp)
        conversation.conversation_disposition = calificacion.history.first()
        conversation.save(update_fields=['is_disposition', 'conversation_disposition'])
        return conversation

    def _save_form_response(self, calificacion, respuesta_formulario_gestion):
        formulario = calificacion.opcion_calificacion.formulario
        instance = RespuestaFormularioGestion.objects.filter(
            calificacion=calificacion).last()
        if instance:
            serializer_respuesta = RespuestaFormularioGestionUpdateSerilializer(
                instance, {'metadata': respuesta_formulario_gestion}, partial=True)
        else:
            serializer_respuesta = RespuestaFormularioGestionCreateSerilializer(data={
                'metadata': respuesta_formulario_gestion,
                'formulario': formulario,
            })
        if serializer_respuesta.is_valid():
            serializer_respuesta.save(calificacion=calificacion)
        return serializer_respuesta

    def retrieve(self, request, pk):
        try:
            calificacion = CalificacionCliente.objects.get(pk=pk)
            serializer = RetrieveSerializer(calificacion)
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se obtuvo la calificacion de forma exitosa'),
                    data=serializer.data),
                status=status.HTTP_200_OK)
        except CalificacionCliente.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Calificacion no encontrada')),
                status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            return response.Response(
                data=get_response_data(message=_('Error al obtener las calificaciones')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request):
        try:
            request_data = request.data.copy()
            conversation_id = request_data.pop('idConversation')
            timestamp = timezone.now().astimezone(timezone.get_current_timezone())
            serializer_calificacion = CreateSerializer(data=request_data)
            if not serializer_calificacion.is_valid():
                return response.Response(
                    data=get_response_data(
                        message=_('Error en los datos'),
                        errors=serializer_calificacion.errors),
                    status=status.HTTP_400_BAD_REQUEST)

            opcion_calificacion = serializer_calificacion.validated_data.get(
                'opcion_calificacion')
            contacto = serializer_calificacion.validated_data.get('contacto')
            existing_calificacion = CalificacionCliente.objects.filter(
                contacto=contacto,
                opcion_calificacion__campana=opcion_calificacion.campana).first()

            if existing_calificacion:
                update_data = {
                    'idAgente': serializer_calificacion.validated_data.get('agente').pk,
                    'idDispositionOption': opcion_calificacion.pk,
                    'subdispositionOption': serializer_calificacion.validated_data.get(
                        'subcalificacion'),
                    'comments': serializer_calificacion.validated_data.get('observaciones'),
                }
                serializer_existing = UpdateSerializer(
                    existing_calificacion, data=update_data, partial=True)
                if not serializer_existing.is_valid():
                    return response.Response(
                        data=get_response_data(
                            message=_('Error en los datos'),
                            errors=serializer_existing.errors),
                        status=status.HTTP_400_BAD_REQUEST)
                calificacion = serializer_existing.save(
                    canalidad=CalificacionCliente.CANALIDAD_INSTAGRAM)
                serializer_respuesta = None
                if calificacion.opcion_calificacion.tipo != OpcionCalificacion.GESTION \
                        and calificacion.get_venta():
                    calificacion.get_venta().delete()
                else:
                    serializer_respuesta = self._save_form_response(
                        calificacion, request_data.pop('respuestaFormularioGestion', {}))
                    if not serializer_respuesta.is_valid():
                        return response.Response(
                            data=get_response_data(
                                message=_('Error en los datos del formulario'),
                                errors=serializer_respuesta.errors),
                            status=status.HTTP_400_BAD_REQUEST)
                self._finalize_conversation(conversation_id, calificacion, timestamp)
                response_data = serializer_existing.data
                if serializer_respuesta:
                    response_data = {
                        **response_data,
                        **{'respuestaFormularioGestion': serializer_respuesta.data},
                    }
                return response.Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS,
                        message=_('Se actualizo la calificacion de forma exitosa'),
                        data=response_data),
                    status=status.HTTP_200_OK)

            if opcion_calificacion.tipo == OpcionCalificacion.GESTION:
                respuesta_formulario_gestion = request_data.pop(
                    'respuestaFormularioGestion', {})
                serializer_respuesta = RespuestaFormularioGestionCreateSerilializer(data={
                    'metadata': respuesta_formulario_gestion,
                    'formulario': opcion_calificacion.formulario,
                })
                if not serializer_respuesta.is_valid():
                    return response.Response(
                        data=get_response_data(
                            message=_('Error en los datos del formulario'),
                            errors=serializer_respuesta.errors),
                        status=status.HTTP_400_BAD_REQUEST)
                calificacion = serializer_calificacion.save(
                    canalidad=CalificacionCliente.CANALIDAD_INSTAGRAM)
                serializer_respuesta.save(calificacion=calificacion)
                conversation = self._finalize_conversation(
                    conversation_id, calificacion, timestamp, send_goodbye=False)
                autoresponse_goodbye(conversation, timestamp)
                return response.Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS,
                        message=_('Se creo la calificacion de forma exitosa'),
                        data={
                            **serializer_calificacion.data,
                            **{'respuestaFormularioGestion': serializer_respuesta.data},
                        }),
                    status=status.HTTP_201_CREATED)

            calificacion = serializer_calificacion.save(
                canalidad=CalificacionCliente.CANALIDAD_INSTAGRAM)
            self._finalize_conversation(conversation_id, calificacion, timestamp)
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se creo la calificacion de forma exitosa'),
                    data=serializer_calificacion.data),
                status=status.HTTP_201_CREATED)
        except Exception as e:
            print(e)
            return response.Response(
                data=get_response_data(message=str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, pk):
        try:
            request_data = request.data.copy()
            conversation_id = request_data.pop('idConversation')
            timestamp = timezone.now().astimezone(timezone.get_current_timezone())
            instance = CalificacionCliente.objects.get(pk=pk)
            serializer_calificacion = UpdateSerializer(instance, data=request_data, partial=True)
            if not serializer_calificacion.is_valid():
                return response.Response(
                    data=get_response_data(
                        message=_('Error en los datos'),
                        errors=serializer_calificacion.errors),
                    status=status.HTTP_400_BAD_REQUEST)

            calificacion = serializer_calificacion.save(
                canalidad=CalificacionCliente.CANALIDAD_INSTAGRAM)
            if calificacion.opcion_calificacion.tipo != OpcionCalificacion.GESTION \
                    and calificacion.get_venta():
                calificacion.get_venta().delete()
            elif 'respuestaFormularioGestion' in request_data:
                serializer_respuesta = self._save_form_response(
                    calificacion, request_data.pop('respuestaFormularioGestion'))
                if not serializer_respuesta.is_valid():
                    return response.Response(
                        data=get_response_data(
                            message=_('Error en los datos del formulario'),
                            errors=serializer_respuesta.errors),
                        status=status.HTTP_400_BAD_REQUEST)
            self._finalize_conversation(conversation_id, calificacion, timestamp)
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se actualizo la calificacion de forma exitosa'),
                    data=serializer_calificacion.data),
                status=status.HTTP_200_OK)
        except CalificacionCliente.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('CalificacionCliente no encontrada')),
                status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            return response.Response(
                data=get_response_data(message=_('Error al actualizar la CalificacionCliente')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True)
    def history(self, request, pk):
        try:
            calificacioncliente = CalificacionCliente.objects.get(pk=pk)
            history = calificacioncliente.history.all().order_by('-history_date')
            serializer = ListSerializer(history, many=True)
            return response.Response(
                data=get_response_data(status=HttpResponseStatus.SUCCESS, data=serializer.data),
                status=status.HTTP_200_OK)
        except CalificacionCliente.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Calificacion no encontrada')),
                status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print("Error al obtener el historial de calificacion:", e)
            return response.Response(
                data=get_response_data(message=_('Error al obtener el historial de calificacion')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=False, url_path='options/(?P<campaing_id>[^/.]+)')
    def options(self, request, campaing_id):
        try:
            opciones = OpcionCalificacion.objects.filter(campana__id=campaing_id)
            serializer = OpcionCalificacionSerializer(opciones, many=True)
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se obtuvieron las opciones de calificacion de forma exitosa'),
                    data=serializer.data),
                status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return response.Response(
                data=get_response_data(message=_('Error al obtener opciones de calificacion')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
