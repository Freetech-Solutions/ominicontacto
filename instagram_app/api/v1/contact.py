# -*- coding: utf-8 -*-
import json

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import ugettext as _
from rest_framework import decorators, response, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication

from api_app.authentication import ExpiringTokenAuthentication
from instagram_app.api.permissions import TienePermisoCanalInstagramAgente
from instagram_app.api.utils import HttpResponseStatus, get_response_data
from instagram_app.models import ConversationInstagramApp
from ominicontacto_app.models import Campana, Contacto, TelephoneValidator


MAX_SEARCH_RESULTS = 20


class ListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    phone = serializers.CharField(source='telefono')
    page_client_id = serializers.CharField(source='instagram', required=False)
    data = serializers.SerializerMethodField()
    disposition = serializers.SerializerMethodField()

    def get_disposition(self, obj):
        disposition = obj.calificacioncliente_set.last()
        return disposition.id if disposition else None

    def get_data(self, obj):
        return obj.obtener_datos()


class ContactDataMixin:
    def __init__(self, *args, **kwargs):
        self.campana = kwargs.pop('context', {}).get('campana')
        super().__init__(*args, **kwargs)

    def es_campo_telefonico(self, field):
        metadata = self.campana.bd_contacto.get_metadata()
        return field in metadata.nombres_de_columnas_de_telefonos

    def validar_telefono(self, field, value):
        try:
            TelephoneValidator(value)
        except ValidationError as error:
            raise serializers.ValidationError({field: error.message})
        return value

    def validar_page_client_id(self, field, value):
        if not value:
            raise serializers.ValidationError({field: _('campo requerido')})
        return value

    def get_datos_json(self, data):
        datos = []
        metadata = self.campana.bd_contacto.get_metadata()
        for field in metadata.nombres_de_columnas_de_datos:
            value = data.get(field, '')
            if value and self.es_campo_telefonico(field):
                self.validar_telefono(field, value)
            datos.append(value if value else "")
        return json.dumps(datos)

    def _extract_standard_fields(self, data, require_page_client_id=False):
        metadata = self.campana.bd_contacto.get_metadata()
        telefono = metadata.nombre_campo_telefono
        datos = data['datos']
        if telefono in datos:
            data['telefono'] = self.validar_telefono(telefono, datos.pop(telefono))
        else:
            data['telefono'] = getattr(self.instance, 'telefono', '')

        if 'page_client_id' in datos:
            data['page_client_id'] = self.validar_page_client_id(
                'page_client_id', datos.pop('page_client_id'))
        elif require_page_client_id:
            raise serializers.ValidationError({'page_client_id': _('campo requerido')})


class CreateSerializer(ContactDataMixin, serializers.ModelSerializer):
    page_client_id = serializers.CharField(source='instagram', required=False)

    class Meta:
        model = Contacto
        fields = [
            'id',
            'telefono',
            'datos',
            'bd_contacto',
            'page_client_id',
        ]

    def to_internal_value(self, data):
        data = data.copy()
        data['datos'] = data['datos'].copy()
        mandatory = list(self.campana.get_campos_obligatorios())
        metadata = self.campana.bd_contacto.get_metadata()
        campos_bd = metadata.nombres_de_columnas
        telefono = metadata.nombre_campo_telefono

        self._extract_standard_fields(data)
        if not data['telefono']:
            mandatory = [field for field in mandatory if field != telefono]

        if not set(data['datos'].keys()).issubset(set(campos_bd)):
            raise serializers.ValidationError({'Error': _('Error en los campos de contacto')})
        if not set(data['datos'].keys()).issuperset(set(mandatory)):
            raise serializers.ValidationError({'Error': _('Faltan campos requeridos')})
        data['datos'] = self.get_datos_json(data['datos'])
        return super(CreateSerializer, self).to_internal_value(data)


class UpdateSerializer(ContactDataMixin, serializers.ModelSerializer):
    page_client_id = serializers.CharField(source='instagram', required=True)

    class Meta:
        model = Contacto
        fields = [
            'id',
            'telefono',
            'datos',
            'bd_contacto',
            'page_client_id',
        ]

    def to_internal_value(self, data):
        data = data.copy()
        data['datos'] = data['datos'].copy()
        campos_no_editables = self.campana.get_campos_no_editables()
        campos_ocultos = self.campana.get_campos_ocultos()
        metadata = self.campana.bd_contacto.get_metadata()
        campos_bd = metadata.nombres_de_columnas

        self._extract_standard_fields(data, require_page_client_id=True)
        if not set(data['datos'].keys()).issubset(set(campos_bd)):
            raise serializers.ValidationError({'Error': _('Error en los campos de contacto')})
        if set(data['datos'].keys()).intersection(set(campos_no_editables)) or \
                set(data['datos'].keys()).intersection(set(campos_ocultos)):
            raise serializers.ValidationError(
                {'error': _('No puede editar campos ocultos o bloqueados')})
        data['datos'] = self.get_datos_json(data['datos'])
        return super(UpdateSerializer, self).to_internal_value(data)


class ViewSet(viewsets.ViewSet):
    permission_classes = [TienePermisoCanalInstagramAgente]
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)

    def _contact_queryset(self, campana):
        return Contacto.objects.filter(
            bd_contacto=campana.bd_contacto
        ).select_related('bd_contacto')

    def _active_contact_ids(self, campana, exclude_conversation_id=None):
        conversations = ConversationInstagramApp.objects.filter(
            is_disposition=False,
            campana_id=campana.pk,
            client_id__isnull=False,
        )
        if exclude_conversation_id:
            conversations = conversations.exclude(pk=exclude_conversation_id)
        return conversations.values_list('client_id', flat=True)

    def list(self, request, campana_pk):
        try:
            filtro = request.GET.get('search')
            campana = Campana.objects.get(id=campana_pk)
            listado_de_contacto = Contacto.objects.contactos_by_filtro_bd_contacto(
                campana.bd_contacto, filtro)
        except Exception:
            listado_de_contacto = Contacto.objects.contactos_by_bd_contacto(
                campana.bd_contacto)
        serializer = ListSerializer(listado_de_contacto, many=True)
        return response.Response(
            data=get_response_data(
                status=HttpResponseStatus.SUCCESS,
                message=_('Se obtuvieron los contactos de forma exitosa'),
                data=serializer.data),
            status=status.HTTP_200_OK)

    @decorators.action(
        detail=False,
        methods=["post"],
        url_path='create_contact_from_conversation/(?P<conversacion_pk>[^/.]+)')
    def create_contact_from_conversation(self, request, campana_pk, conversacion_pk):
        try:
            campana = Campana.objects.get(id=campana_pk)
            request_data = request.data.copy()
            conversation = ConversationInstagramApp.objects.get(id=conversacion_pk)
            if 'page_client_id' not in request_data and conversation.ig_scoped_id:
                request_data['page_client_id'] = conversation.ig_scoped_id
            data = {
                "bd_contacto": campana.bd_contacto.id,
                "datos": request_data,
            }
            serializer = CreateSerializer(data=data, context={'campana': campana})
            if serializer.is_valid():
                client = serializer.save()
                conversation.client = client
                conversation.save(update_fields=['client'])
                return response.Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS,
                        message=_('Se creo el nuevo contacto de forma exitosa'),
                        data=ListSerializer(client).data),
                    status=status.HTTP_201_CREATED)
            return response.Response(
                data=get_response_data(
                    message=_('Error en los datos'), errors=serializer.errors),
                status=status.HTTP_400_BAD_REQUEST)
        except ConversationInstagramApp.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Conversación no encontrada')),
                status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al crear el contacto')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, campana_pk):
        try:
            campana = Campana.objects.get(id=campana_pk)
            data = {
                "bd_contacto": campana.bd_contacto.id,
                "datos": request.data.copy(),
            }
            serializer = CreateSerializer(data=data, context={'campana': campana})
            if serializer.is_valid():
                client = serializer.save()
                return response.Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS,
                        message=_('Se creo el nuevo contacto de forma exitosa'),
                        data=ListSerializer(client).data),
                    status=status.HTTP_201_CREATED)
            return response.Response(
                data=get_response_data(
                    message=_('Error en los datos'), errors=serializer.errors),
                status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al crear el contacto')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, campana_pk, pk):
        try:
            campana = Campana.objects.get(id=campana_pk)
            data = {"datos": request.data.copy()}
            instance = Contacto.objects.get(pk=pk)
            serializer = UpdateSerializer(
                instance, data=data, partial=True, context={'campana': campana})
            if serializer.is_valid():
                client = serializer.save()
                return response.Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS,
                        message=_('Se actualizo el nuevo contacto de forma exitosa'),
                        data=ListSerializer(client).data),
                    status=status.HTTP_201_CREATED)
            return response.Response(
                data=get_response_data(
                    status=status.HTTP_400_BAD_REQUEST,
                    message=_('Error en los datos'), errors=serializer.errors))
        except Contacto.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Contacto no encontrado')),
                status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al actualizar el contacto')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=False, methods=["get"])
    def db_fields(self, request, campana_pk):
        try:
            campana = Campana.objects.get(id=campana_pk)
            metadata = campana.bd_contacto.get_metadata()
            data = []
            for index, name in enumerate(metadata.nombres_de_columnas, start=0):
                data.append({
                    'name': name,
                    'mandatory': name in campana.get_campos_obligatorios()
                    or name == metadata.nombre_campo_telefono,
                    'block': name in campana.get_campos_no_editables(),
                    'hide': name in campana.get_campos_ocultos(),
                    'is_phone_field': index in metadata.columnas_con_telefono,
                })
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    data=data),
                status=status.HTTP_200_OK)
        except Exception:
            return response.Response(
                data=get_response_data(
                    message=_('Error al obtener los campos de contacto')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=False, methods=["post"])
    def suggest_match(self, request, campana_pk):
        try:
            campana = Campana.objects.get(id=campana_pk)
            conversation_id = request.data.get('conversation_id')
            if not conversation_id:
                return response.Response(
                    data=get_response_data(message=_('Conversación requerida')),
                    status=status.HTTP_400_BAD_REQUEST)
            conversation = ConversationInstagramApp.objects.only(
                'id', 'ig_scoped_id'
            ).get(id=conversation_id)
            if not conversation.ig_scoped_id:
                return response.Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS,
                        message=_('Sin coincidencia sugerida'),
                        data=None),
                    status=status.HTTP_200_OK)
            active_contact_ids = self._active_contact_ids(
                campana, exclude_conversation_id=conversation.pk)
            queryset = self._contact_queryset(campana).filter(
                instagram=conversation.ig_scoped_id
            ).exclude(id__in=list(active_contact_ids))
            contact = queryset.only(
                'id', 'telefono', 'instagram', 'datos', 'bd_contacto_id',
                'bd_contacto__metadata'
            ).first()
            serializer = ListSerializer(contact) if contact else None
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se obtuvo la coincidencia sugerida'),
                    data=serializer.data if serializer else None),
                status=status.HTTP_200_OK)
        except ConversationInstagramApp.DoesNotExist:
            return response.Response(
                data=get_response_data(message=_('Conversación no encontrada')),
                status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al obtener coincidencia sugerida')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=False, methods=["post"])
    def search(self, request, campana_pk):
        try:
            campana = Campana.objects.get(id=campana_pk)
            search = (request.data.get('search') or '').strip()
            phone = (request.data.get('phone') or '').strip()
            name = (request.data.get('name') or '').strip()
            conversation_id = request.data.get('conversation_id')
            try:
                limit = int(request.data.get('limit', MAX_SEARCH_RESULTS))
            except (TypeError, ValueError):
                limit = MAX_SEARCH_RESULTS
            limit = max(1, min(limit, 50))

            active_contact_ids = list(
                self._active_contact_ids(campana, exclude_conversation_id=conversation_id))
            base_queryset = self._contact_queryset(campana)
            if active_contact_ids:
                base_queryset = base_queryset.exclude(id__in=active_contact_ids)

            candidate_terms = [term for term in [search, phone, name] if term]
            if not candidate_terms:
                return response.Response(
                    data=get_response_data(
                        status=HttpResponseStatus.SUCCESS,
                        message=_('Se obtuvieron los contactos de forma exitosa'),
                        data=[]),
                    status=status.HTTP_200_OK)
            filters = Q()
            for term in candidate_terms:
                filters |= (
                    Q(telefono__icontains=term) |
                    Q(instagram__icontains=term) |
                    Q(id_externo__icontains=term) |
                    Q(datos__icontains=term)
                )
            contactos = base_queryset.filter(filters).only(
                'id', 'telefono', 'instagram', 'datos', 'bd_contacto_id',
                'bd_contacto__metadata'
            ).distinct()[:limit]
            serializer = ListSerializer(contactos, many=True)
            return response.Response(
                data=get_response_data(
                    status=HttpResponseStatus.SUCCESS,
                    message=_('Se obtuvieron los contactos de forma exitosa'),
                    data=serializer.data),
                status=status.HTTP_200_OK)
        except Exception:
            return response.Response(
                data=get_response_data(message=_('Error al obtener contactos')),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
