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
from ominicontacto_app.models import AutenticacionSitioExterno
from ominicontacto_app.services.sistema_externo.safe_http import (
    DestinoNoPermitidoError, validar_url)


class ValidarUrlAutenticacionMixin(object):

    def validate_url(self, url):
        try:
            validar_url(url)
        except DestinoNoPermitidoError as e:
            raise serializers.ValidationError(str(e))
        return url


class AutenticacionSitioExternoSerializer(ValidarUrlAutenticacionMixin,
                                          serializers.ModelSerializer):

    class Meta:
        model = AutenticacionSitioExterno
        fields = '__all__'


class AutenticacionSitioExternoTestSerializer(ValidarUrlAutenticacionMixin,
                                              serializers.ModelSerializer):

    class Meta:
        model = AutenticacionSitioExterno
        exclude = [
            "id",
            "nombre",
        ]
