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

"""
Tests del listado de campañas dialer
"""
from mock import patch

from django.urls import reverse

from ominicontacto_app.models import Campana
from ominicontacto_app.services.audio_conversor import ConversorDeAudioService
from ominicontacto_app.tests.utiles import OMLBaseTest
from ominicontacto_app.views_campana_dialer import CampanaDialerListView


@patch.object(CampanaDialerListView, 'FINALIZADAS_POR_PAGINA', 2)
class CampanaDialerListViewTests(OMLBaseTest):

    def setUp(self):
        super(CampanaDialerListViewTests, self).setUp()
        # crear_campana_dialer convierte un audio con sox, que no está en el pipeline
        patcher = patch.object(ConversorDeAudioService, '_convertir_audio')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.admin = self.crear_administrador()
        self.client.login(username=self.admin.username, password=self.DEFAULT_PASSWORD)
        self.activa = self._crear_campana(Campana.ESTADO_ACTIVA)
        self.finalizadas = [self._crear_campana(Campana.ESTADO_FINALIZADA) for _ in range(3)]

    def _crear_campana(self, estado):
        campana = self.crear_campana_dialer(cant_contactos=2, user=self.admin)
        campana.estado = estado
        campana.save()
        return campana

    def _get_listado(self, **params):
        return self.client.get(reverse('campana_dialer_list'), params)

    def _ids(self, campanas):
        return [campana.pk for campana in campanas]

    def test_campanas_finalizadas_se_paginan(self):
        response = self._get_listado()
        pagina = response.context['finalizadas']
        self.assertEqual(pagina.number, 1)
        self.assertEqual(pagina.paginator.num_pages, 2)
        ids_esperados = sorted(self._ids(self.finalizadas), reverse=True)
        self.assertEqual(self._ids(pagina), ids_esperados[:2])
        self.assertNotContains(response, 'id="camp-data-{0}"'.format(ids_esperados[2]))

    def test_segunda_pagina_de_finalizadas(self):
        response = self._get_listado(finalizadas_page=2)
        pagina = response.context['finalizadas']
        self.assertEqual(pagina.number, 2)
        self.assertEqual(self._ids(pagina), [min(self._ids(self.finalizadas))])

    def test_pagina_invalida_de_finalizadas(self):
        response = self._get_listado(finalizadas_page='x')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['finalizadas'].number, 1)
        response = self._get_listado(finalizadas_page=99)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['finalizadas'].number, 2)

    def test_links_de_paginacion_con_ancla(self):
        response = self._get_listado()
        self.assertContains(response, 'id="campanas-finalizadas"')
        self.assertContains(response, '?finalizadas_page=2#campanas-finalizadas')

    def test_campanas_activas_no_se_paginan(self):
        response = self._get_listado(finalizadas_page=2)
        self.assertEqual(self._ids(response.context['activas']), [self.activa.pk])
        self.assertContains(response, 'id="camp-data-{0}"'.format(self.activa.pk))

    def test_finalizadas_muestran_solo_nombre_de_base_de_datos(self):
        response = self._get_listado()
        self.assertContains(response, str(self.activa.bd_contacto))
        finalizada = response.context['finalizadas'][0]
        self.assertContains(response, finalizada.bd_contacto.nombre)
        self.assertNotContains(response, str(finalizada.bd_contacto))

    def test_datos_de_campanas_incluyen_todas_las_finalizadas(self):
        response = self._get_listado()
        datos = response.context['datos_campanas']
        for campana in self.finalizadas:
            self.assertEqual(datos[campana.pk]['status'], Campana.ESTADO_FINALIZADA)
