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


class AgentsActivityV2TabsViewTests(OMLBaseTest):
    def setUp(self):
        super(AgentsActivityV2TabsViewTests, self).setUp()
        admin = self.crear_administrador(username='admin_agents_activity_v2_tabs')
        self.client.login(username=admin.username, password=PASSWORD)
        self.url = reverse('reportes_agents_activity_v2')

    def test_renderiza_tab_listado_y_tabla_performance(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="agentsActivityTabsL1"')
        self.assertContains(response, 'id="tab-listado-link"')
        self.assertContains(response, 'href="#tab-listado"')
        self.assertContains(response, 'id="tab-listado"')
        self.assertContains(response, 'id="tab-analisis-link"')
        self.assertContains(response, 'href="#tab-analisis"')
        self.assertContains(response, 'id="tab-analisis"')
        self.assertContains(response, 'id="csv_agents_activity_listado_task_id"')
        self.assertContains(response, 'id="csv_agents_activity_listado_api_export_url"')
        self.assertContains(response, 'id="csv_agents_activity_listado_download_url_prefix"')
        self.assertContains(response, 'id="csvAgentsActivityListadoDescarga"')
        self.assertContains(response, 'id="csvAgentsActivityListadoDescargaLink"')
        self.assertContains(response, 'id="barraProgresoCSVAgentsActivityListado"')
        self.assertContains(response, 'id="reporte-performance-tbody"')
