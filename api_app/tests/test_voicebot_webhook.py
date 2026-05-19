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

from django.conf import settings
from django.urls import reverse
from mock import patch, Mock

from ominicontacto_app.models import (
    CalificacionCliente, Campana, OpcionCalificacion, User,
)
from ominicontacto_app.tests.factories import QueueMemberFactory
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class VoicebotWebhookTest(OMLBaseTest):
    """Tests para POST /api/v1/webhook/voicebot/."""

    def setUp(self):
        super(VoicebotWebhookTest, self).setUp()
        usr_supervisor = self.crear_user_supervisor(username='voicebot_sup')
        self.crear_supervisor_profile(user=usr_supervisor, rol=User.SUPERVISOR)
        usr_agente = self.crear_user_agente(username='voicebot_agent')
        self.agente = self.crear_agente_profile(usr_agente)

        bd_contacto = self.crear_base_datos_contacto(cant_contactos=1)
        self.campana = self.crear_campana_manual(
            cant_contactos=1,
            user=usr_supervisor,
            bd_contactos=bd_contacto,
        )
        self.campana.estado = Campana.ESTADO_ACTIVA
        self.campana.save()

        QueueMemberFactory.create(
            member=self.agente, queue_name=self.campana.queue_campana,
        )

        self.contacto = self.campana.bd_contacto.contactos.first()
        self.opcion_gestion_bot = OpcionCalificacion.objects.create(
            campana=self.campana,
            nombre=getattr(settings, 'VOICEBOT_CALIFICACION_NOMBRE', 'GESTION_BOT'),
            tipo=OpcionCalificacion.NO_ACCION,
        )
        self.opcion_otra = OpcionCalificacion.objects.create(
            campana=self.campana,
            nombre='SCHEDULE_CALL_BOT',
            tipo=OpcionCalificacion.NO_ACCION,
        )

        self.url = reverse('api_voicebot_webhook')
        self.call_id = '1771024232.107'
        self.client.login(username=usr_supervisor.username, password=PASSWORD)

    def _payload(self, **overrides):
        data = {
            'X-OML-Contact-ID': str(self.contacto.pk),
            'X-OML-Campaign-ID': str(self.campana.pk),
            'X-OML-Call-ID': self.call_id,
            'X-OML-Disposition': str(self.opcion_gestion_bot.pk),
        }
        data.update(overrides)
        return data

    def _post(self, payload):
        return self.client.post(
            self.url,
            json.dumps(payload),
            format='json',
            content_type='application/json',
        )

    def test_missing_contact_id_returns_400(self):
        payload = self._payload()
        del payload['X-OML-Contact-ID']
        response = self._post(payload)
        response_json = json.loads(response.content)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response_json['status'], 'ERROR')
        self.assertIn('X-OML-Contact-ID', response_json['errors'])

    def test_contact_not_found_returns_404(self):
        payload = self._payload(**{'X-OML-Contact-ID': '999999'})
        response = self._post(payload)
        response_json = json.loads(response.content)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response_json['status'], 'ERROR')

    def test_creates_disposition_successfully(self):
        response = self._post(self._payload(
            **{'X-OML-Disposition': str(self.opcion_otra.pk)},
        ))
        response_json = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json['status'], 'SUCCESS')
        self.assertTrue(
            CalificacionCliente.objects.filter(
                contacto=self.contacto,
                opcion_calificacion=self.opcion_otra,
                callid=self.call_id,
            ).exists()
        )

    @patch('api_app.views.voicebot.VoicebotWebhookView._publicar_voicebot_transfer_proceed')
    def test_publishes_redis_on_gestion_bot(self, mock_publish):
        response = self._post(self._payload())
        response_json = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json['status'], 'SUCCESS')
        mock_publish.assert_called_once_with(self.call_id)

    @patch('api_app.views.voicebot.VoicebotWebhookView._publicar_voicebot_transfer_proceed')
    def test_does_not_publish_redis_for_other_disposition(self, mock_publish):
        response = self._post(self._payload(
            **{'X-OML-Disposition': str(self.opcion_otra.pk)},
        ))
        response_json = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json['status'], 'SUCCESS')
        mock_publish.assert_not_called()

    @patch('ominicontacto_app.services.redis.connection.create_redis_connection')
    def test_redis_publish_payload(self, mock_redis_factory):
        mock_client = Mock()
        mock_redis_factory.return_value = mock_client

        response = self._post(self._payload())
        self.assertEqual(response.status_code, 200)
        mock_client.publish.assert_called_once()
        channel, message = mock_client.publish.call_args[0]
        self.assertEqual(channel, 'acd:commands:global')
        payload = json.loads(message)
        self.assertEqual(payload['action'], 'voicebot_transfer_proceed')
        self.assertEqual(payload['call_id'], self.call_id)

    def test_updates_existing_disposition(self):
        CalificacionCliente.objects.create(
            contacto=self.contacto,
            opcion_calificacion=self.opcion_otra,
            observaciones='prev',
            agente=self.agente,
            callid='old-call-id',
        )
        response = self._post(self._payload(
            **{'X-OML-Disposition': str(self.opcion_gestion_bot.pk)},
        ))
        response_json = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertIn('updated', response_json['message'].lower())

        calificacion = CalificacionCliente.objects.get(
            contacto=self.contacto,
            opcion_calificacion__campana=self.campana,
        )
        self.assertEqual(calificacion.opcion_calificacion_id, self.opcion_gestion_bot.pk)
        self.assertEqual(calificacion.callid, self.call_id)
