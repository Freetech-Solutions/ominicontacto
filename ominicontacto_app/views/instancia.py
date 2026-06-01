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

""" Vistas que tienen que ver con la instancia: Registro, Acerca De, Marketplace
"""

import logging

from constance import config as config_constance
from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from ominicontacto_app import version
from ominicontacto_app.forms.base import RegistroForm
from ominicontacto_app.services.key_server_request import KeyServerRequest


logger = logging.getLogger(__name__)


class AcercaTemplateView(TemplateView):
    """
    Esta vista es para generar el Acerca de la app.
    """

    template_name = 'acerca/acerca.html'

    def get_context_data(self, **kwargs):
        context = super(
            AcercaTemplateView, self).get_context_data(**kwargs)

        context['branch'] = version.OML_BRANCH
        context['commit'] = version.OML_COMMIT
        context['fecha_deploy'] = version.OML_BUILD_DATE
        return context


class RegistroFormView(FormView):
    """Vista que se encarga de registrar un usuario en el servidor de llaves y crear al usuario
    settings para que los pueda usar en los accesos a funcionalidades
    """

    template_name = 'registro.html'
    form_class = RegistroForm

    def get_success_url(self):
        return reverse('registrar_usuario')

    def get_context_data(self, **kwargs):
        context = super(RegistroFormView, self).get_context_data(**kwargs)
        registered = (config_constance.CLIENT_NAME != '' and config_constance.CLIENT_KEY != '')
        context['registered'] = registered
        return context

    def _create_credentials(self, form):
        key_server_request = KeyServerRequest()
        try:
            client = form.cleaned_data['nombre']
            password = form.cleaned_data['password']
            email = form.cleaned_data['email']
            telefono = form.cleaned_data['telefono']
        except AttributeError:
            msg = _('No tiene settings de conexion configurados')
            logger.error(msg)
            return {'status': 'ERROR', 'msg': msg}
        post_data = {'client': client, 'password': password, 'email': email, 'phone': telefono}
        try:
            result = key_server_request.post('/retrieve_key/', json=post_data)
        except Exception as e:
            msg = _('Error en el intento de conexion con el servidor de llaves '
                    'debido {0}'.format(e))
            logger.error(msg)
            return {'status': 'ERROR', 'msg': msg}
        try:
            return result.json()
        except ValueError:
            return {'status': 'ERROR', 'msg': _('Error al parsear el resultado de la peticion')}

    def form_valid(self, form):
        result = self._create_credentials(form)
        if result['status'] == 'ERROR':
            message = result['msg']
            messages.error(self.request, message)
            return render(self.request, 'registro.html', {'form': form})
        message = _('Registro exitoso, se le ha enviado un e-mail con su llave de registro.')
        messages.success(self.request, message)
        config_constance.CLIENT_NAME = result['user_name']
        config_constance.CLIENT_PASSWORD = form.cleaned_data['password']
        config_constance.CLIENT_KEY = result['user_key']
        config_constance.CLIENT_EMAIL = result['user_email']
        config_constance.CLIENT_PHONE = result['user_phone']
        return super(RegistroFormView, self).form_valid(form)


class AddonsInfoView(TemplateView):
    """Vista que se muestra todos los addons disponibles
    """

    template_name = 'addons.html'

    def _obtener_datos_addons(self):
        key_server_request = KeyServerRequest()
        try:
            info_addons = key_server_request.get('/addons/info')
        except Exception as e:
            logger.info(_("No se pudo acceder a la url debido a: {0}".format(e)))
            return []
        else:
            info_addons_list = info_addons.json()['data']
            return info_addons_list

    def get_context_data(self, **kwargs):
        context = super(AddonsInfoView, self).get_context_data(**kwargs)
        context['addons_info'] = self._obtener_datos_addons()
        return context
