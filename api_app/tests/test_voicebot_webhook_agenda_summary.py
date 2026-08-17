# -*- coding: utf-8 -*-
# Copyright (C) 2026 Freetech Solutions

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

import json

from django.urls import reverse
from django.utils import timezone
from mock import patch

from ominicontacto_app.models import (
    AgendaContacto, CalificacionCliente, Campana, OpcionCalificacion, User,
)
from ominicontacto_app.tests.factories import OpcionCalificacionFactory, QueueMemberFactory
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class VoicebotWebhookAgendaSummaryTest(OMLBaseTest):
    """Si ya hay agenda, /webhook/voicebot/ y /webhook/verloop/ anexan el
    call_summary y no publican voicebot_transfer_proceed.
    """

    def setUp(self):
        super(VoicebotWebhookAgendaSummaryTest, self).setUp()
        usr_supervisor = self.crear_user_supervisor(username='voicebot_summary_sup')
        self.crear_supervisor_profile(user=usr_supervisor, rol=User.SUPERVISOR)

        usr_bot = self.crear_user_agente(username='voicebot_summary_agent')
        self.agente_bot = self.crear_agente_profile(usr_bot)
        self.agente_bot.voicebot = True
        self.agente_bot.save()

        bd_contacto = self.crear_base_datos_contacto(cant_contactos=1)
        self.campana = self.crear_campana_manual(
            cant_contactos=1,
            user=usr_supervisor,
            bd_contactos=bd_contacto,
        )
        self.campana.estado = Campana.ESTADO_ACTIVA
        self.campana.save()

        QueueMemberFactory.create(
            member=self.agente_bot, queue_name=self.campana.queue_campana,
        )

        self.contacto = self.campana.bd_contacto.contactos.first()
        self.phone = self.contacto.lista_de_telefonos_de_contacto()[0]
        self.call_id = '1786917072.25'
        self.summary = 'The customer confirmed a callback tomorrow after 3pm.'

        self.opcion_gestion = OpcionCalificacionFactory(
            campana=self.campana,
            nombre='GESTION_BOT',
            tipo=OpcionCalificacion.GESTION,
            formulario=None,
        )

        self.url_agenda = reverse('api_voicebot_agenda_webhook')
        self.url_voicebot = reverse('api_voicebot_webhook')
        self.url_verloop = reverse('api_verloop_webhook')
        self.client.login(username=usr_supervisor.username, password=PASSWORD)

    def _fecha_hora_futura(self):
        futuro = timezone.now() + timezone.timedelta(days=1)
        return futuro.date().isoformat(), futuro.time().replace(microsecond=0).isoformat()

    def _post(self, url, payload):
        return self.client.post(
            url,
            json.dumps(payload),
            format='json',
            content_type='application/json',
        )

    def _crear_agenda(self, request='Llamame mañana después de las 3'):
        fecha, hora = self._fecha_hora_futura()
        response = self._post(self.url_agenda, {
            'X-OML-Campaign-ID': str(self.campana.pk),
            'X-OML-Contact-ID': str(self.contacto.pk),
            'X-OML-Call-ID': self.call_id,
            'phone': self.phone,
            'callback_valid': 'true',
            'callback_date': fecha,
            'callback_time': hora,
            'callback_request': request,
            'callback_rule': 'explicit_time',
        })
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _payload_voicebot(self, **overrides):
        data = {
            'X-OML-Contact-ID': str(self.contacto.pk),
            'X-OML-Campaign-ID': str(self.campana.pk),
            'X-OML-Call-ID': self.call_id,
            'X-OML-Disposition': str(self.opcion_gestion.pk),
            'call_summary': self.summary,
        }
        data.update(overrides)
        return data

    def _payload_verloop(self, **overrides):
        data = {
            'X-Verloop-customerID': str(self.contacto.pk),
            'X-Verloop-CampID': str(self.campana.pk),
            'X-Verloop-callID': self.call_id,
            'X-Verloop-Disposition': str(self.opcion_gestion.pk),
            'analysis': {
                'user_defined': {
                    'call_summary': self.summary,
                },
            },
        }
        data.update(overrides)
        return data

    def _assert_agenda_intacta_con_summary(self, agenda_id, calificacion_id, request_inicial):
        agenda = AgendaContacto.objects.get(pk=agenda_id)
        self.assertIn(request_inicial, agenda.observaciones)
        self.assertIn(self.summary, agenda.observaciones)

        calificacion = CalificacionCliente.objects.get(pk=calificacion_id)
        self.assertEqual(calificacion.opcion_calificacion.tipo, OpcionCalificacion.AGENDA)
        self.assertNotEqual(calificacion.opcion_calificacion.nombre, 'GESTION_BOT')

    @patch('api_app.views.voicebot.publicar_voicebot_transfer_proceed')
    def test_voicebot_webhook_appends_summary_and_skips_acd(self, mock_publish):
        agenda_data = self._crear_agenda()
        response = self._post(self.url_voicebot, self._payload_voicebot())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'SUCCESS')
        self.assertTrue(data['data']['appended'])
        self.assertEqual(data['data']['agenda_id'], agenda_data['agenda_id'])
        self.assertEqual(data['data']['calificacion_id'], agenda_data['calificacion_id'])

        self._assert_agenda_intacta_con_summary(
            agenda_data['agenda_id'], agenda_data['calificacion_id'],
            'Llamame mañana después de las 3')
        mock_publish.assert_not_called()

    @patch('api_app.views.verloop.publicar_voicebot_transfer_proceed')
    def test_verloop_webhook_appends_summary_and_skips_acd(self, mock_publish):
        agenda_data = self._crear_agenda()
        response = self._post(self.url_verloop, self._payload_verloop())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'SUCCESS')
        self.assertTrue(data['data']['appended'])
        self.assertEqual(data['data']['agenda_id'], agenda_data['agenda_id'])

        self._assert_agenda_intacta_con_summary(
            agenda_data['agenda_id'], agenda_data['calificacion_id'],
            'Llamame mañana después de las 3')
        mock_publish.assert_not_called()

    @patch('api_app.views.voicebot.publicar_voicebot_transfer_proceed')
    def test_retry_does_not_duplicate_summary(self, mock_publish):
        agenda_data = self._crear_agenda()
        self._post(self.url_voicebot, self._payload_voicebot())
        response = self._post(self.url_voicebot, self._payload_voicebot())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['data']['appended'])

        agenda = AgendaContacto.objects.get(pk=agenda_data['agenda_id'])
        self.assertEqual(agenda.observaciones.count(self.summary), 1)
        mock_publish.assert_not_called()

    @patch('api_app.views.voicebot.publicar_voicebot_transfer_proceed')
    def test_without_prior_agenda_still_qualifies_and_transfers(self, mock_publish):
        response = self._post(self.url_voicebot, self._payload_voicebot())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'SUCCESS')
        self.assertNotIn('agenda_id', data.get('data', {}))

        calificacion = CalificacionCliente.objects.get(
            contacto=self.contacto, opcion_calificacion__campana=self.campana)
        self.assertEqual(calificacion.opcion_calificacion.nombre, 'GESTION_BOT')
        mock_publish.assert_called_once_with(self.call_id)
        self.assertFalse(AgendaContacto.objects.filter(contacto=self.contacto).exists())
