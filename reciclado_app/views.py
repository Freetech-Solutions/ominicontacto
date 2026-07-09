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

""" Vistas para el reciclados de las campanas"""

from __future__ import unicode_literals
from functools import partial

from django.db import transaction
from django.urls import reverse
from django.contrib import messages
from django.shortcuts import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from reciclado_app.forms import RecicladoForm
from reciclado_app.resultado_contactacion import (
    EstadisticasContactacion, RecicladorContactosCampanaDIALER, RecicladorContactosCampanaPreview)
from ominicontacto_app.errors import OmlRecicladoCampanaError
from ominicontacto_app.models import Campana
from ominicontacto_app.services.dialer import get_dialer_service, wombat_habilitado

import logging as logging_


logger = logging_.getLogger(__name__)


class ReciclarCampanaMixin(object):

    form_class = RecicladoForm
    template_name = 'nuevo_reciclado.html'

    def _get_campana(self):
        if not hasattr(self, '_campana_cache'):
            self._campana_cache = Campana.objects.get(pk=self.kwargs['pk_campana'])
        return self._campana_cache

    def _get_estadisticas_reciclado(self):
        if not hasattr(self, '_estadisticas_reciclado_cache'):
            campana = self._get_campana()
            estadisticas = EstadisticasContactacion()
            self._estadisticas_reciclado_cache = {
                'estadisticas': estadisticas,
                'campana': campana,
                'calificaciones': estadisticas.obtener_cantidad_calificacion(campana),
            }
        return self._estadisticas_reciclado_cache

    def _get_no_contactados_estadisticas(self):
        cache = self._get_estadisticas_reciclado()
        if 'no_contactados' not in cache:
            cache['no_contactados'] = cache['estadisticas'].obtener_cantidad_no_contactados(
                cache['campana'])
        return cache['no_contactados']

    def get_form_kwargs(self):
        kwargs = super(ReciclarCampanaMixin, self).get_form_kwargs()
        cache = self._get_estadisticas_reciclado()
        contactados_choice = [
            (contactacion.id, contactacion.label_checkbox)
            for contactacion in cache['calificaciones']
        ]
        kwargs['reciclado_choice'] = contactados_choice
        kwargs['no_contactados_choice'] = self._obtener_choices_no_contactados(
            cache['estadisticas'], cache['campana'])
        return kwargs

    def form_valid(self, form):
        reciclado_calificacion = form.cleaned_data.get('reciclado_calificacion')
        reciclado_no_contactacion = form.cleaned_data.get('reciclado_no_contactacion')
        reciclado_radio = form.cleaned_data.get('reciclado_radio')
        retomar_contactacion = form.cleaned_data.get('retomar_contactacion')

        if not (reciclado_calificacion or reciclado_no_contactacion):
            message = _(u'<strong>Operación Errónea!</strong> \
                        Debe seleccionar al menos una opcion para reciclar ')

            messages.add_message(
                self.request,
                messages.ERROR,
                message,
            )
            return self.form_invalid(form)

        campana = Campana.objects.get(pk=self.kwargs['pk_campana'])
        reciclador = self._obtener_reciclador()
        if campana.es_preview and retomar_contactacion:
            reciclador.retomar_contactacion(
                campana, reciclado_calificacion, reciclado_no_contactacion)
            return HttpResponseRedirect(reverse('campana_preview_list'))
        bd_contacto_reciclada = reciclador.reciclar(
            campana, reciclado_calificacion, reciclado_no_contactacion)
        if reciclado_radio == 'nueva_campaña':
            try:
                # Intenta reciclar la campana con el tipo de reciclado
                # seleccionado.
                campana_reciclada = Campana.objects.reciclar_campana(
                    campana, bd_contacto_reciclada)
            except OmlRecicladoCampanaError:

                message = _(u'<strong>Operación Errónea!</strong>\
                No se pudo reciclar la Campana.')

                messages.add_message(
                    self.request,
                    messages.ERROR,
                    message,
                )
                return self.form_invalid(form)

            crea_campana_template = self._reciclar_crear_nueva_campana(campana_reciclada, campana)
            return HttpResponseRedirect(crea_campana_template)
        elif reciclado_radio == 'misma_campana':
            # TODO: Ver si update_base... debe estar en _reciclar_misma por el tema de transaccion
            # con el servicio omnidialer
            campana.update_basedatoscontactos(bd_contacto_reciclada)
            update_campana = self._reciclar_misma_campana(campana)
            return HttpResponseRedirect(reverse(update_campana, kwargs={"pk_campana": campana.pk}))

    def get_context_data(self, **kwargs):
        context = super(ReciclarCampanaMixin, self).get_context_data(**kwargs)
        cache = self._get_estadisticas_reciclado()
        contactados_choice = [
            (contactacion.id, contactacion.nombre, contactacion.cantidad)
            for contactacion in cache['calificaciones']
        ]
        context['contactados'] = contactados_choice
        context['no_contactados'] = self._obtener_cantidad_no_contactados(
            cache['estadisticas'], cache['campana'])
        context['es_campana_preview'] = cache['campana'].es_preview
        return context

    def _obtener_choices_no_contactados(self, estadisticas: EstadisticasContactacion, campana):
        raise NotImplementedError()

    def _obtener_cantidad_no_contactados(self, estadisticas: EstadisticasContactacion, campana):
        raise NotImplementedError()

    def _obtener_reciclador(self):
        raise NotImplementedError()


class ReciclarCampanaDialerFormView(ReciclarCampanaMixin, FormView):
    """
    Esta vista muestra los distintos tipo de reciclados de las campanas
    dialer
    """
    def dispatch(self, request, *args, **kwargs):
        campana = self._get_campana()
        cache = self._get_estadisticas_reciclado()
        contactados = [
            (contactacion.id, contactacion.label_checkbox)
            for contactacion in cache['calificaciones']
        ]
        no_contactados = self._obtener_choices_no_contactados(
            cache['estadisticas'], cache['campana'])
        if campana.estado not in [Campana.ESTADO_FINALIZADA, Campana.ESTADO_PAUSADA]:
            message = _(u'Solo se pueden reciclar campañas finalizadas y/o pausadas.')
            messages.add_message(self.request, messages.WARNING, message)
            return HttpResponseRedirect(reverse('campana_dialer_list'))
        if not (contactados or no_contactados) and campana.estado != Campana.ESTADO_FINALIZADA:
            message = _(u'Esta campaña no se puede reciclar.')
            messages.add_message(self.request, messages.WARNING, message)
            return HttpResponseRedirect(reverse('campana_dialer_list'))
        return super(ReciclarCampanaMixin, self).dispatch(request, *args, **kwargs)

    def _reciclar_crear_nueva_campana(self, campana_reciclada, campana):
        if campana.estado != Campana.ESTADO_FINALIZADA:
            campana.estado = Campana.ESTADO_FINALIZADA
            campana.save()
            dialer_service = get_dialer_service()
            dialer_service.terminar_campana(campana)
        crea_campana_template = reverse("crea_campana_dialer_template",
                                        kwargs={"pk_campana_template": campana_reciclada.pk,
                                                "borrar_template": 1})
        return crea_campana_template

    def _reciclar_misma_campana(self, campana):
        # TODO: Ver que pasa con la llamada a
        # campana.update_basedatoscontactos(bd_contacto_reciclada) antes de que se llame a esta
        # funcion y el transaction siguiente
        with transaction.atomic():
            campana.estado = Campana.ESTADO_INACTIVA
            campana.save()
            if wombat_habilitado():
                # Intento cambiar la BD en wombat como parte de la transaccion
                self._cambiar_bd_contactos_en_dialer(campana)

        # Cambio BD en OMniDialer una vez que ya se cambió en base
        if not wombat_habilitado():
            transaction.on_commit(partial(self._safe_cambiar_bd_contactos_en_dialer, campana))

        update_campana = "campana_dialer_update"
        return update_campana

    def _safe_cambiar_bd_contactos_en_dialer(self, campana):
        try:
            self._cambiar_bd_contactos_en_dialer(campana)
        except Exception as e:
            logger.error(e)
            messages.add_message(
                self.request,
                messages.ERROR,
                _('<strong>¡ATENCIÓN!</strong> Error al sincronizar con el servicio Discador. '
                  'Por favor contacte un administrador.'))

    def _cambiar_bd_contactos_en_dialer(self, campana):
        params = {'telefonos': [], 'evitar_duplicados': False,
                  'evitar_sin_telefono': False, 'prefijo_discador': ''}
        dialer_service = get_dialer_service()
        dialer_service.cambiar_bd_contactos(campana, params)

    def _obtener_choices_no_contactados(self, estadisticas: EstadisticasContactacion, campana):
        no_contactados = self._get_no_contactados_estadisticas()
        return [(value.id, value.label_checkbox)
                for key, value in no_contactados.items()]

    def _obtener_cantidad_no_contactados(self, estadisticas: EstadisticasContactacion, campana):
        no_contactados = self._get_no_contactados_estadisticas()
        return [(value.id, value.nombre, value.cantidad) for key, value in no_contactados.items()]

    def _obtener_reciclador(self):
        return RecicladorContactosCampanaDIALER()


class ReciclarCampanaPreviewFormView(ReciclarCampanaMixin, FormView):
    """
    Esta vista muestra los distintos tipo de reciclados de las campanas
    preview
    """
    def _reciclar_crear_nueva_campana(self, campana_reciclada, campana):
        crea_campana_template = reverse("campana_preview_template_create_campana",
                                        kwargs={"pk_campana_template": campana_reciclada.pk,
                                                "borrar_template": 1})
        return crea_campana_template

    def _reciclar_misma_campana(self, campana):
        campana.estado = Campana.ESTADO_ACTIVA
        campana.save()
        campana.establecer_valores_iniciales_agente_contacto(False, False)
        update_campana = "campana_preview_update"
        return update_campana

    def _obtener_choices_no_contactados(self, estadisticas: EstadisticasContactacion, campana):
        no_calificados = estadisticas.obtener_cantidad_no_calificados(campana)
        return [('0', _('No calificados') + ' ' + str(no_calificados)), ]

    def _obtener_cantidad_no_contactados(self, estadisticas: EstadisticasContactacion, campana):
        no_calificados = estadisticas.obtener_cantidad_no_calificados(campana)
        return [('0', _('No calificados'), no_calificados), ]

    def _obtener_reciclador(self):
        return RecicladorContactosCampanaPreview()
