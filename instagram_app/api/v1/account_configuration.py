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
import json

from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response

from configuracion_telefonia_app.models import DestinoEntrante, GrupoHorario, OpcionDestino
from instagram_app.api.permissions import TienePermisoCanalInstagramAgente
from instagram_app.api.utils import HttpResponseStatus, get_response_data
from instagram_app.models import (
    ConfiguracionInstagramCampana,
    CuentaInstagram,
    MenuInteractivoInstagram,
    OpcionMenuInteractivoInstagram,
    PlantillaInstagram,
)
from instagram_app.services.redis.account import StreamDeCuentasInstagram
from ominicontacto_app.models import Campana


class InstagramAccountSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()
    access_token = serializers.CharField()
    verify_token = serializers.CharField()
    app_id = serializers.CharField()
    page_id = serializers.CharField()
    ig_user_id = serializers.CharField()
    username = serializers.CharField()
    destination = serializers.SerializerMethodField()
    schedule = serializers.SerializerMethodField()
    horario = serializers.SerializerMethodField()
    campaign = serializers.SerializerMethodField()
    welcome_message = serializers.SerializerMethodField()
    goodbye_message = serializers.SerializerMethodField()
    out_of_hours_message = serializers.SerializerMethodField()
    validated = serializers.BooleanField()
    is_active = serializers.BooleanField()

    def get_campaign(self, obj):
        if obj.destination and obj.destination.tipo == DestinoEntrante.CAMPANA:
            return obj.destination.content_object.id
        return None

    def get_schedule(self, obj):
        return obj.horario_id

    def get_horario(self, obj):
        return obj.horario_id

    def get_welcome_message(self, obj):
        return obj.welcome_message_id

    def get_goodbye_message(self, obj):
        return obj.goodbye_message_id

    def get_out_of_hours_message(self, obj):
        return obj.out_of_hours_message_id

    def get_destination(self, obj):
        return DestinoEntranteInstagramSerializer(read_only=True).to_representation(obj)


class JSONSerializerField(serializers.Field):
    def to_internal_value(self, data):
        try:
            if isinstance(data, int):
                json_data = data
            else:
                json_data = json.loads(json.dumps(data))
        except Exception:
            json_data = data
        return json_data

    def to_representation(self, value):
        return value


class OpcionMenuInstagramSerializer(serializers.BaseSerializer):

    def to_internal_value(self, data):
        value = data.get('value')
        destination = data.get('destination')
        description = data.get('description')
        type_option = data.get('type_option')
        if not destination:
            raise serializers.ValidationError({'destination': _('Este campo es requerido.')})
        if not value:
            raise serializers.ValidationError({'value': _('Este campo es requerido.')})
        return {
            'destination': destination,
            'value': value,
            'description': description,
            'type_option': type_option,
        }


class MenuInteractivoInstagramSerializer(serializers.Serializer):
    id_tmp = serializers.IntegerField(required=False)
    is_main = serializers.BooleanField(required=False, default=True)
    menu_header = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    wrong_answer = serializers.CharField(required=False, allow_blank=True)
    success = serializers.CharField(required=False, allow_blank=True)
    timeout = serializers.IntegerField(min_value=0, required=False)
    options = OpcionMenuInstagramSerializer(many=True)

    def validate_options(self, options):
        if len(options) > len(set([option['value'] for option in options])):
            raise serializers.ValidationError({
                'options': _('El valor de las opciones no puede repetirse')})
        if len(options) > 10:
            raise serializers.ValidationError({
                'options': _('No pueden definirse más de 10 opciones')})
        return options


class DestinoDeCuentaInstagramCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=(
            (DestinoEntrante.CAMPANA, _('Campana')),
            (DestinoEntrante.MENU_INTERACTIVO_INSTAGRAM, _('Menu Interactivo')),
        ))
    data = JSONSerializerField()
    id_tmp = serializers.IntegerField(required=False)

    def validate_data(self, destination):
        destination_type = int(self.initial_data.get('type'))
        if destination_type == DestinoEntrante.CAMPANA:
            return self._validate_campana_as_destination(destination)
        return self._validate_menu_interactivo_as_destination(destination)

    def _validate_campana_as_destination(self, campana_id):
        if not isinstance(campana_id, int):
            raise serializers.ValidationError({'data': _('Valor incorrecto. Debe ser un id')})
        try:
            campana = Campana.objects.get(pk=campana_id)
        except Campana.DoesNotExist:
            raise serializers.ValidationError({'data': _('No existe campaña con ese id')})
        self.destino = self._get_or_create_campaign_destination(campana)
        return campana_id

    def _validate_menu_interactivo_as_destination(self, menu_data):
        self.menu_serializer = MenuInteractivoInstagramSerializer(data=menu_data, many=True)
        self.menu_serializer.is_valid(raise_exception=True)
        return menu_data

    def _get_or_create_campaign_destination(self, campaign):
        try:
            return DestinoEntrante.get_nodo_ruta_entrante(campaign)
        except DestinoEntrante.DoesNotExist:
            return DestinoEntrante.crear_nodo_ruta_entrante(campaign)

    def create(self, validated_data):
        if int(validated_data['type']) == DestinoEntrante.MENU_INTERACTIVO_INSTAGRAM:
            self.create_menu_interactivo(validated_data)
        return validated_data

    def create_menu_interactivo(self, validated_data):
        account = self.context.get('account')
        list_menu_data = validated_data.get('data', [])
        destinos_con_opciones = []
        first_destino = None
        for menu_data in list_menu_data:
            menu = MenuInteractivoInstagram.objects.create(
                menu_header=menu_data.get('menu_header', ''),
                texto_opcion_incorrecta=menu_data.get('wrong_answer', ''),
                texto_derivacion=menu_data.get('success', ''),
                timeout=menu_data.get('timeout', 0) or 0,
                account=account,
                is_main=menu_data.get('is_main', False),
            )
            destino = DestinoEntrante.crear_nodo_ruta_entrante(menu)
            if first_destino is None:
                first_destino = destino
            destinos_con_opciones.append({
                'id_tmp': menu_data.get('id_tmp'),
                'destino_anterior': destino,
                'opciones': menu_data.get('options', []),
            })
            if menu_data.get('is_main', False) or (
                'id_tmp' in menu_data and 'id_tmp' in validated_data and
                menu_data['id_tmp'] == validated_data['id_tmp']
            ):
                self.destino = destino
            menu_data['id'] = menu.id
        if not hasattr(self, 'destino') and first_destino:
            self.destino = first_destino
        self.crear_opciones(destinos_con_opciones)

    def crear_opciones(self, destinos_con_opciones):
        for object_dict in destinos_con_opciones:
            for option_data in object_dict['opciones']:
                destino_siguiente = None
                if option_data['type_option'] == DestinoEntrante.CAMPANA:
                    campana = Campana.objects.get(id=option_data['destination'])
                    destino_siguiente = self._get_or_create_campaign_destination(campana)
                elif option_data['type_option'] == DestinoEntrante.MENU_INTERACTIVO_INSTAGRAM:
                    destino_siguiente = self.find_destination(
                        destinos_con_opciones, option_data['destination'])
                elif option_data['type_option'] == DestinoEntrante.CLOSING_MESSAGE:
                    plantilla = PlantillaInstagram.objects.get(id=option_data['destination'])
                    try:
                        destino_siguiente = DestinoEntrante.get_nodo_ruta_entrante(plantilla)
                    except DestinoEntrante.DoesNotExist:
                        destino_siguiente = DestinoEntrante.crear_nodo_ruta_entrante(plantilla)
                if destino_siguiente:
                    option_data['destination'] = destino_siguiente.content_object.id
                    opcion = OpcionDestino.crear_opcion_destino(
                        destino_anterior=object_dict['destino_anterior'],
                        destino_siguiente=destino_siguiente,
                        valor=option_data['value'])
                    OpcionMenuInteractivoInstagram.objects.create(
                        opcion=opcion,
                        descripcion=option_data.get('description', ''))

    def find_destination(self, destinos_con_opciones, value):
        for object_dict in destinos_con_opciones:
            if object_dict['id_tmp'] == value:
                return object_dict['destino_anterior']
        return None


class DestinoEntranteInstagramSerializer(serializers.RelatedField):

    def _option_representation(self, option):
        return {
            'id': option.id,
            'type_option': option.destino_siguiente.tipo,
            'destination': option.destino_siguiente.content_object.id,
            'value': option.valor,
            'description': option.opcion_menu_instagram_app.descripcion,
            'destination_name': option.destino_siguiente.content_object.nombre,
        }

    def _menu_representation(self, value, data_list):
        menu = value.content_object
        menu_representation = {
            'id': menu.id,
            'id_tmp': menu.id,
            'is_main': menu.is_main,
            'menu_header': menu.menu_header if menu.menu_header else '',
            'wrong_answer': menu.texto_opcion_incorrecta,
            'success': menu.texto_derivacion,
            'timeout': menu.timeout or 0,
            'options': [],
        }
        data_list.append(menu_representation)
        for opcion in value.destinos_siguientes.all():
            menu_representation['options'].append(self._option_representation(opcion))
            if opcion.destino_siguiente.tipo == DestinoEntrante.MENU_INTERACTIVO_INSTAGRAM:
                if not any(item['id'] ==
                           opcion.destino_siguiente.content_object.id for item in data_list):
                    self._menu_representation(opcion.destino_siguiente, data_list)
        return data_list

    def to_representation(self, account):
        if account.destination:
            value = account.destination
            representation = {
                'type': value.tipo,
                'id': value.content_object.id,
            }
            if value.tipo == DestinoEntrante.CAMPANA:
                representation['data'] = value.content_object.id
            elif value.tipo == DestinoEntrante.MENU_INTERACTIVO_INSTAGRAM:
                data_list = []
                self._menu_representation(value, data_list)
                representation['data'] = sorted(data_list, key=lambda x: x['id'])
            return representation
        return {}


class InstagramAccountCreateSerializer(serializers.ModelSerializer):
    schedule = serializers.PrimaryKeyRelatedField(
        queryset=GrupoHorario.objects.all(), allow_null=True, required=False, source='horario')
    campaign = serializers.PrimaryKeyRelatedField(
        queryset=Campana.objects.all(), allow_null=True, required=False, write_only=True)
    welcome_message = serializers.PrimaryKeyRelatedField(
        queryset=PlantillaInstagram.objects.all(), allow_null=True, required=False)
    goodbye_message = serializers.PrimaryKeyRelatedField(
        queryset=PlantillaInstagram.objects.all(), allow_null=True, required=False)
    out_of_hours_message = serializers.PrimaryKeyRelatedField(
        queryset=PlantillaInstagram.objects.all(), allow_null=True, required=False)

    class Meta:
        model = CuentaInstagram
        fields = [
            'name', 'description', 'access_token', 'verify_token', 'app_id', 'page_id',
            'ig_user_id', 'username', 'schedule', 'campaign', 'welcome_message',
            'goodbye_message', 'out_of_hours_message', 'is_active',
        ]

    def _get_or_create_campaign_destination(self, campaign):
        try:
            return DestinoEntrante.get_nodo_ruta_entrante(campaign)
        except DestinoEntrante.DoesNotExist:
            return DestinoEntrante.crear_nodo_ruta_entrante(campaign)

    def _set_campaign_config(self, account, campaign):
        if not campaign.instagram_habilitado:
            campaign.instagram_habilitado = True
            campaign.save(update_fields=['instagram_habilitado'])
        ConfiguracionInstagramCampana.objects.update_or_create(
            campana=campaign,
            defaults={
                'cuenta': account,
                'nivel_servicio': 90,
                'is_active': True,
            })

    def create(self, validated_data):
        campaign = validated_data.pop('campaign', None)
        if campaign:
            validated_data['destination'] = self._get_or_create_campaign_destination(campaign)
        account = CuentaInstagram.objects_default.create(**validated_data)
        if campaign:
            self._set_campaign_config(account, campaign)
        return account

    def update(self, instance, validated_data):
        campaign = validated_data.pop('campaign', None)
        if campaign:
            validated_data['destination'] = self._get_or_create_campaign_destination(campaign)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if campaign:
            self._set_campaign_config(instance, campaign)
        return instance


class InstagramCampaignSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(source='nombre')
    type = serializers.IntegerField()
    instagram_habilitado = serializers.BooleanField()


class InstagramScheduleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(source='nombre')


class ViewSet(viewsets.ViewSet):
    permission_classes = [TienePermisoCanalInstagramAgente]
    authentication_classes = (SessionAuthentication, )

    @staticmethod
    def _ensure_account_destination(account, destino):
        if account.destination_id != destino.id:
            account.destination = destino
            account.save(update_fields=['destination'])

    @staticmethod
    def _link_account_to_menu_destinations(account, serialized_destination):
        menu_data = serialized_destination.get('data', [])
        if isinstance(menu_data, list):
            menu_ids = [menu.get('id') for menu in menu_data if 'id' in menu]
            if menu_ids:
                MenuInteractivoInstagram.objects.filter(id__in=menu_ids).update(account=account)

    def _apply_destination_side_effects(self, account, destino, serialized_destination):
        if destino.tipo == DestinoEntrante.CAMPANA:
            if not destino.content_object.instagram_habilitado:
                destino.content_object.instagram_habilitado = True
                destino.content_object.save(update_fields=['instagram_habilitado'])
            ConfiguracionInstagramCampana.objects.update_or_create(
                campana=destino.content_object,
                defaults={
                    'cuenta': account,
                    'nivel_servicio': 90,
                    'is_active': True,
                })
        if destino.tipo == DestinoEntrante.MENU_INTERACTIVO_INSTAGRAM:
            destino.content_object.is_main = True
            destino.content_object.save(update_fields=['is_main'])
            self._link_account_to_menu_destinations(account, serialized_destination)

    def list(self, request):
        queryset = CuentaInstagram.objects.all()
        serializer = InstagramAccountSerializer(queryset, many=True)
        return Response(
            data=get_response_data(
                status=HttpResponseStatus.SUCCESS,
                message=_('Se obtuvieron las cuentas de Instagram de forma exitosa'),
                data=serializer.data),
            status=status.HTTP_200_OK)

    def create(self, request):
        request_data = request.data.copy()
        destino_data = request_data.pop('destination', None)
        if destino_data is None and request_data.get('campaign'):
            destino_data = {
                'type': DestinoEntrante.CAMPANA,
                'data': request_data.get('campaign'),
            }
        serializer = InstagramAccountCreateSerializer(data=request_data)
        if serializer.is_valid():
            serializer_destino = DestinoDeCuentaInstagramCreateSerializer(data=destino_data)
            if serializer_destino.is_valid():
                with transaction.atomic():
                    serializer_destino.save()
                    destino = serializer_destino.destino
                    account = serializer.save(destination=destino)
                    self._ensure_account_destination(account, destino)
                    self._apply_destination_side_effects(account, destino, serializer_destino.data)
                    StreamDeCuentasInstagram().notificar_nueva_cuenta(account)
                serialized_data = InstagramAccountSerializer(account).data
                serialized_data['destination'] = serializer_destino.data
                return Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS,
                        message=_('Se creó la cuenta de Instagram de forma exitosa'),
                        data=serialized_data),
                    status=status.HTTP_201_CREATED)
            return Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR,
                    message=_('No se pudo crear la cuenta de Instagram'),
                    errors={'destination': serializer_destino.errors}),
                status=status.HTTP_400_BAD_REQUEST)
        return Response(
            data=get_response_data(
                status=HttpResponseStatus.ERROR,
                message=_('No se pudo crear la cuenta de Instagram'),
                errors=serializer.errors),
            status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        try:
            instance = CuentaInstagram.objects_default.get(pk=pk)
        except CuentaInstagram.DoesNotExist:
            return Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR,
                    message=_('No se pudo actualizar la cuenta de Instagram'),
                    data={'id': [_('No existe una cuenta de Instagram con este id')]}),
                status=status.HTTP_404_NOT_FOUND)
        request_data = request.data.copy()
        destino_data = request_data.pop('destination', None)
        if destino_data is None and request_data.get('campaign'):
            destino_data = {
                'type': DestinoEntrante.CAMPANA,
                'data': request_data.get('campaign'),
            }
        serializer = InstagramAccountCreateSerializer(instance, data=request_data)
        if serializer.is_valid():
            serializer_destino = DestinoDeCuentaInstagramCreateSerializer(
                data=destino_data, context={'account': instance})
            if serializer_destino.is_valid():
                with transaction.atomic():
                    instance.destination = None
                    instance.save(update_fields=['destination'])
                    for menu_old in instance.menuinteractivo.all():
                        try:
                            destino_old = DestinoEntrante.objects.get(
                                object_id=menu_old.pk,
                                tipo=DestinoEntrante.MENU_INTERACTIVO_INSTAGRAM)
                            opciones_destino = OpcionDestino.objects.filter(
                                destino_anterior=destino_old)
                            for option in opciones_destino:
                                if option.destino_siguiente.tipo ==\
                                        DestinoEntrante.MENU_INTERACTIVO_INSTAGRAM:
                                    option.destino_siguiente.delete()
                                option.delete()
                            destino_old.delete()
                            menu_old.delete()
                        except Exception:
                            menu_old.delete()
                    serializer_destino.save()
                    destino = serializer_destino.destino
                    account = serializer.save(destination=destino)
                    self._ensure_account_destination(account, destino)
                    self._apply_destination_side_effects(account, destino, serializer_destino.data)
                    StreamDeCuentasInstagram().notificar_nueva_cuenta(account)
                serialized_data = InstagramAccountSerializer(account).data
                serialized_data['destination'] = serializer_destino.data
                return Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS,
                        message=_('Se actualizó la cuenta de Instagram de forma exitosa'),
                        data=serialized_data),
                    status=status.HTTP_200_OK)
            return Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR,
                    message=_('No se pudo actualizar la cuenta de Instagram'),
                    errors={'destination': serializer_destino.errors}),
                status=status.HTTP_400_BAD_REQUEST)
        return Response(
            data=get_response_data(
                status=HttpResponseStatus.ERROR,
                message=_('No se pudo actualizar la cuenta de Instagram'),
                errors=serializer.errors),
            status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        try:
            instance = CuentaInstagram.objects_default.get(pk=pk)
        except CuentaInstagram.DoesNotExist:
            return Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR,
                    message=_('No se pudo eliminar la cuenta de Instagram'),
                    data={'id': [_('No existe una cuenta de Instagram con este id')]}),
                status=status.HTTP_404_NOT_FOUND)
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        StreamDeCuentasInstagram().notificar_cuenta_eliminada(instance)
        return Response(
            data=get_response_data(
                status=HttpResponseStatus.SUCCESS,
                message=_('Se eliminó la cuenta de Instagram de forma exitosa')),
            status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        try:
            instance = CuentaInstagram.objects_default.get(pk=pk)
        except CuentaInstagram.DoesNotExist:
            return Response(
                data=get_response_data(
                    status=HttpResponseStatus.ERROR,
                    message=_('No se pudo obtener la cuenta de Instagram'),
                    data={'id': [_('No existe una cuenta de Instagram con este id')]}),
                status=status.HTTP_404_NOT_FOUND)
        serializer = InstagramAccountSerializer(instance)
        return Response(
            data=get_response_data(
                status=HttpResponseStatus.SUCCESS,
                message=_('Se obtuvo la cuenta de Instagram de forma exitosa'),
                data=serializer.data),
            status=status.HTTP_200_OK)


class CampaignViewSet(viewsets.ViewSet):
    permission_classes = [TienePermisoCanalInstagramAgente]
    authentication_classes = (SessionAuthentication, )

    def list(self, request):
        estados = [Campana.ESTADO_ACTIVA, Campana.ESTADO_PAUSADA, Campana.ESTADO_INACTIVA]
        if request.user.get_is_administrador():
            queryset = Campana.objects.filter(estado__in=estados)
        elif request.user.get_is_agente():
            campana_members = request.user.get_agente_profile().campana_member.all()
            queue_names = campana_members.values_list('id_campana', flat=True)
            campaigns_pks = [Campana.get_id_from_queue_id_name(name) for name in queue_names]
            queryset = Campana.objects.filter(pk__in=campaigns_pks, estado__in=estados)
        else:
            queryset = request.user.get_supervisor_profile()\
                .campanas_asignadas_actuales().filter(estado__in=estados)
        serializer = InstagramCampaignSerializer(queryset, many=True)
        return Response(
            data=get_response_data(
                status=HttpResponseStatus.SUCCESS,
                message=_('Se obtuvieron las campañas de forma exitosa'),
                data=serializer.data),
            status=status.HTTP_200_OK)


class ScheduleViewSet(viewsets.ViewSet):
    permission_classes = [TienePermisoCanalInstagramAgente]
    authentication_classes = (SessionAuthentication, )

    def list(self, request):
        queryset = GrupoHorario.objects.all().order_by('id')
        serializer = InstagramScheduleSerializer(queryset, many=True)
        return Response(
            data=get_response_data(
                status=HttpResponseStatus.SUCCESS,
                message=_('Se obtuvieron los grupos horarios de forma exitosa'),
                data=serializer.data),
            status=status.HTTP_200_OK)
