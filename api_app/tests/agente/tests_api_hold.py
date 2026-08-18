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

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD
from reportes_app.models import AgentActivityEventV2


class ApiEventoHoldTest(OMLBaseTest):

    def setUp(self):
        super(ApiEventoHoldTest, self).setUp()
        user = self.crear_user_agente(username='agente1')
        self.agente = self.crear_agente_profile(user)
        self.client.login(username=user.username, password=PASSWORD)
        self.callid = 'callid1'
        self.url = reverse('api_evento_hold')

    def _ultimo_evento_hold(self):
        return AgentActivityEventV2.objects.filter(
            agente_id=self.agente.id,
            metadata__callid=self.callid,
            event_type__in=[
                AgentActivityEventV2.EventType.STATE_ON_HOLD,
                AgentActivityEventV2.EventType.STATE_OFF_HOLD,
            ],
        ).order_by('-id').first()

    def test_evento_hold_inserta_hold(self):
        response = self.client.post(self.url, {'callid': self.callid})

        self.assertEqual(response.json(), {'status': 'OK'})
        ultimo = self._ultimo_evento_hold()
        self.assertIsNotNone(ultimo)
        self.assertEqual(ultimo.event_type, AgentActivityEventV2.EventType.STATE_ON_HOLD)
        self.assertEqual(ultimo.metadata.get('callid'), self.callid)

    def test_evento_hold_inserta_unhold(self):
        AgentActivityEventV2.objects.create(
            agente_id=self.agente.id,
            ts=timezone.now() - timedelta(seconds=1),
            event_type=AgentActivityEventV2.EventType.STATE_ON_HOLD,
            metadata={'callid': self.callid},
        )

        response = self.client.post(self.url, {'callid': self.callid})

        self.assertEqual(response.json(), {'status': 'OK'})
        ultimo = self._ultimo_evento_hold()
        self.assertIsNotNone(ultimo)
        self.assertEqual(ultimo.event_type, AgentActivityEventV2.EventType.STATE_OFF_HOLD)

    def test_evento_hold_requiere_callid(self):
        response = self.client.post(self.url, {})

        self.assertEqual(response.json(), {'status': 'ERROR'})
        self.assertIsNone(self._ultimo_evento_hold())
