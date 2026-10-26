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
from rest_framework import serializers
from ominicontacto_app.models import SitioExterno
from ominicontacto_app.services.sistema_externo.safe_http import (
    DestinoNoPermitidoError, validar_url)


class SitioExternoSerializer(serializers.ModelSerializer):

    def validarFormato(self, formato, metodo):
        if metodo == SitioExterno.GET and formato:
            raise serializers.ValidationError({
                'formato': 'Si el método es GET, no debe indicarse formato'
            })
        if metodo == SitioExterno.POST and not formato:
            raise serializers.ValidationError({
                'formato': 'Si el método es POST, debe seleccionar un formato'
            })

    def validarObjetivo(self, objetivo, disparador, formato, metodo):
        if formato == SitioExterno.JSON and objetivo:
            raise serializers.ValidationError({
                'objetivo': 'Si el formato es JSON, '
                            'no puede haber un objetivo.'
            })
        if disparador == SitioExterno.SERVER and objetivo:
            raise serializers.ValidationError({
                'objetivo': 'Si el disparador es el servidor, '
                            'no puede haber un objetivo.'
            })
        # TODO: Revisar que los parametros de CRM no se queden sin tipo al cambiar el Disparador
        permite_omitir_objetivo = (disparador == SitioExterno.SERVER) or \
            disparador == SitioExterno.CALIFICACION and metodo == SitioExterno.POST
        if not objetivo and not permite_omitir_objetivo:
            raise serializers.ValidationError({
                'objetivo': 'Debe indicar un objetivo válido.'
            })

    def validarUrl(self, url, disparador, objetivo):
        # Sólo se valida el destino de los sitios que consulta el servidor. Los que abre el
        # navegador del agente (iframe / nueva pestaña) pueden apuntar a la red interna.
        ejecuta_en_servidor = disparador in (SitioExterno.SERVER, SitioExterno.LISTA_DINAMICA) \
            or (disparador == SitioExterno.CALIFICACION and not objetivo)
        if not ejecuta_en_servidor:
            return
        try:
            validar_url(url)
        except DestinoNoPermitidoError as e:
            raise serializers.ValidationError({'url': str(e)})

    def validate(self, data):
        metodo = data['metodo']
        formato = data['formato']
        disparador = data['disparador']
        objetivo = data['objetivo']
        self.validarFormato(formato, metodo)
        self.validarObjetivo(objetivo, disparador, formato, metodo)
        self.validarUrl(data['url'], disparador, objetivo)
        if not formato or formato is None:
            data['formato'] = 1
        return data

    class Meta:
        model = SitioExterno
        fields = '__all__'
