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
from __future__ import unicode_literals

from django.urls import reverse

from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class ReporteGraficoAgenteViewTests(OMLBaseTest):
    def setUp(self):
        super(ReporteGraficoAgenteViewTests, self).setUp()
        self.admin = self.crear_administrador(username='admin_reporte_grafico_agente')
        self.agente = self.crear_agente_profile()

    def test_usuario_no_logueado_no_accede_reporte_grafico_agente(self):
        url = reverse('agente_reporte_grafico', args=[self.agente.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_usuario_logueado_accede_reporte_grafico_agente(self):
        self.client.login(username=self.admin.username, password=PASSWORD)
        url = reverse('agente_reporte_grafico', args=[self.agente.pk])
        response = self.client.get(url, {
            'date_start': '2026-02-26',
            'date_end': '2026-02-26',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reporte_grafico_agente_blank.html')
