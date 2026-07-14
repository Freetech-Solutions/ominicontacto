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
from ominicontacto_app.tests.factories import LlamadaLogFactory
from reportes_app.models import LlamadaLog


class ApiEventoHoldTest(OMLBaseTest):

    def setUp(self):
        super(ApiEventoHoldTest, self).setUp()
        user = self.crear_user_agente(username='agente1')
        self.agente = self.crear_agente_profile(user)
        self.client.login(username=user.username, password=PASSWORD)
        self.callid = 'callid1'
        self.url = reverse('api_evento_hold')

    def test_evento_hold_inserta_hold(self):
        LlamadaLogFactory(agente_id=self.agente.id, callid=self.callid, event='CONNECT')

        response = self.client.post(self.url, {'callid': self.callid})

        self.assertEqual(response.json(), {'status': 'OK'})
        ultimo_log = LlamadaLog.objects.filter(
            agente_id=self.agente.id, callid=self.callid).last()
        self.assertEqual(ultimo_log.event, 'HOLD')

    def test_evento_hold_inserta_unhold(self):
        LlamadaLogFactory(agente_id=self.agente.id, callid=self.callid, event='HOLD')

        response = self.client.post(self.url, {'callid': self.callid})

        self.assertEqual(response.json(), {'status': 'OK'})
        ultimo_log = LlamadaLog.objects.filter(
            agente_id=self.agente.id, callid=self.callid).last()
        self.assertEqual(ultimo_log.event, 'UNHOLD')

    def test_evento_hold_no_inserta_si_llamada_finalizo(self):
        LlamadaLogFactory(
            agente_id=self.agente.id, callid=self.callid, event='COMPLETEOUTNUM')
        cantidad_logs_previa = LlamadaLog.objects.filter(
            agente_id=self.agente.id, callid=self.callid).count()

        response = self.client.post(self.url, {'callid': self.callid})

        self.assertEqual(response.json(), {'status': 'ERROR'})
        self.assertEqual(
            LlamadaLog.objects.filter(
                agente_id=self.agente.id, callid=self.callid).count(),
            cantidad_logs_previa)
