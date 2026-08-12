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

from ominicontacto_app.models import (
    AgendaContacto, CalificacionCliente, Campana, OpcionCalificacion, User,
)
from ominicontacto_app.tests.factories import QueueMemberFactory
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class VoicebotAgendaWebhookTest(OMLBaseTest):
    """Tests para POST /api/v1/webhook/voicebot/agenda/."""

    def setUp(self):
        super(VoicebotAgendaWebhookTest, self).setUp()
        usr_supervisor = self.crear_user_supervisor(username='voicebot_agenda_sup')
        self.crear_supervisor_profile(user=usr_supervisor, rol=User.SUPERVISOR)

        usr_bot = self.crear_user_agente(username='voicebot_agent')
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

        self.url = reverse('api_voicebot_agenda_webhook')
        self.call_id = '1771024232.107'
        self.client.login(username=usr_supervisor.username, password=PASSWORD)

    def _fecha_hora_futura(self):
        futuro = timezone.now() + timezone.timedelta(days=1)
        return futuro.date().isoformat(), futuro.time().replace(microsecond=0).isoformat()

    def _payload(self, **overrides):
        fecha, hora = self._fecha_hora_futura()
        data = {
            'X-OML-Campaign-ID': str(self.campana.pk),
            'X-OML-Contact-ID': str(self.contacto.pk),
            'X-OML-Call-ID': self.call_id,
            'phone': self.phone,
            'callback_valid': 'true',
            'callback_date': fecha,
            'callback_time': hora,
            'callback_request': 'Llamame mañana después de las 3',
            'callback_rule': 'explicit_time',
        }
        data.update(overrides)
        return data

    def _post(self, payload, **headers):
        return self.client.post(
            self.url,
            json.dumps(payload),
            format='json',
            content_type='application/json',
            **headers
        )

    # ------------------------------------------------------------------
    # Validaciones de campos obligatorios
    # ------------------------------------------------------------------

    def test_missing_campaign_id_returns_400(self):
        payload = self._payload()
        del payload['X-OML-Campaign-ID']
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('X-OML-Campaign-ID', response.json()['errors'])

    def test_missing_contact_id_returns_400(self):
        payload = self._payload()
        del payload['X-OML-Contact-ID']
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('X-OML-Contact-ID', response.json()['errors'])

    def test_missing_call_id_returns_400(self):
        payload = self._payload()
        del payload['X-OML-Call-ID']
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('X-OML-Call-ID', response.json()['errors'])

    def test_missing_phone_returns_400(self):
        payload = self._payload()
        del payload['phone']
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone', response.json()['errors'])

    def test_invalid_campaign_id_returns_400(self):
        response = self._post(self._payload(**{'X-OML-Campaign-ID': 'abc'}))
        self.assertEqual(response.status_code, 400)
        self.assertIn('X-OML-Campaign-ID', response.json()['errors'])

    # ------------------------------------------------------------------
    # Validaciones de dominio
    # ------------------------------------------------------------------

    def test_campaign_not_found_returns_404(self):
        response = self._post(self._payload(**{'X-OML-Campaign-ID': '999999'}))
        self.assertEqual(response.status_code, 404)

    def test_inactive_campaign_returns_404(self):
        self.campana.estado = Campana.ESTADO_INACTIVA
        self.campana.save()
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 404)

    def test_contact_not_found_returns_404(self):
        response = self._post(self._payload(**{'X-OML-Contact-ID': '999999'}))
        self.assertEqual(response.status_code, 404)

    def test_contact_from_other_database_returns_400(self):
        otra_bd = self.crear_base_datos_contacto(cant_contactos=1)
        otro_contacto = otra_bd.contactos.first()
        response = self._post(self._payload(**{'X-OML-Contact-ID': str(otro_contacto.pk)}))
        self.assertEqual(response.status_code, 400)
        self.assertIn('contact', response.json()['errors'])

    def test_invalid_phone_returns_400(self):
        response = self._post(self._payload(phone='00000000'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone', response.json()['errors'])

    def test_campaign_without_voicebot_agent_returns_400(self):
        self.agente_bot.voicebot = False
        self.agente_bot.save()
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 400)
        self.assertIn('campaign', response.json()['errors'])
        self.assertFalse(CalificacionCliente.objects.filter(contacto=self.contacto).exists())
        self.assertFalse(AgendaContacto.objects.filter(contacto=self.contacto).exists())

    # ------------------------------------------------------------------
    # Casos de éxito
    # ------------------------------------------------------------------

    def test_creates_disposition_and_agenda(self):
        payload = self._payload()
        response = self._post(payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'OK')
        self.assertTrue(data['created'])
        self.assertIsNotNone(data['agenda_id'])
        self.assertEqual(data['warnings'], [])

        agenda = AgendaContacto.objects.get(pk=data['agenda_id'])
        self.assertEqual(agenda.agente, self.agente_bot)
        self.assertEqual(agenda.contacto, self.contacto)
        self.assertEqual(agenda.campana, self.campana)
        self.assertEqual(agenda.telefono, self.phone)
        self.assertEqual(agenda.tipo_agenda, AgendaContacto.TYPE_PERSONAL)
        self.assertEqual(agenda.fecha.isoformat(), payload['callback_date'])
        self.assertIn('Llamame mañana', agenda.observaciones)

        calificacion = CalificacionCliente.objects.get(
            contacto=self.contacto, opcion_calificacion__campana=self.campana)
        self.assertEqual(calificacion.id, data['calificacion_id'])
        self.assertEqual(calificacion.opcion_calificacion.tipo, OpcionCalificacion.AGENDA)
        self.assertEqual(calificacion.callid, self.call_id)
        self.assertEqual(calificacion.agente, self.agente_bot)
        self.assertFalse(calificacion.es_calificacion_manual)
        calificacion.refresh_from_db()
        self.assertTrue(calificacion.agendado)
        self.assertEqual(calificacion.tipo_agenda, AgendaContacto.TYPE_PERSONAL)

    def test_upsert_updates_existing_agenda(self):
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 200)
        agenda_id = response.json()['agenda_id']

        fecha_nueva, hora_nueva = self._fecha_hora_futura()
        fecha_nueva = (timezone.now() + timezone.timedelta(days=3)).date().isoformat()
        response = self._post(self._payload(
            callback_date=fecha_nueva, callback_time=hora_nueva,
            callback_request='Reagendado'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['created'])
        self.assertEqual(data['agenda_id'], agenda_id)
        self.assertEqual(AgendaContacto.objects.filter(contacto=self.contacto).count(), 1)
        agenda = AgendaContacto.objects.get(pk=agenda_id)
        self.assertEqual(agenda.fecha.isoformat(), fecha_nueva)
        self.assertIn('Reagendado', agenda.observaciones)

    def test_callback_valid_false_only_creates_disposition(self):
        payload = self._payload(callback_valid='false')
        response = self._post(payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'OK')
        self.assertIsNone(data['agenda_id'])
        self.assertFalse(data['created'])
        self.assertTrue(len(data['warnings']) > 0)

        self.assertFalse(AgendaContacto.objects.filter(contacto=self.contacto).exists())
        calificacion = CalificacionCliente.objects.get(
            contacto=self.contacto, opcion_calificacion__campana=self.campana)
        self.assertEqual(calificacion.opcion_calificacion.tipo, OpcionCalificacion.AGENDA)
        self.assertFalse(calificacion.agendado)

    def test_invalid_callback_datetime_only_creates_disposition(self):
        payload = self._payload(callback_date='manana', callback_time='tarde')
        response = self._post(payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data['agenda_id'])
        self.assertTrue(len(data['warnings']) > 0)
        self.assertFalse(AgendaContacto.objects.filter(contacto=self.contacto).exists())
        self.assertTrue(CalificacionCliente.objects.filter(contacto=self.contacto).exists())

    def test_fields_accepted_as_headers(self):
        fecha, hora = self._fecha_hora_futura()
        payload = {
            'phone': self.phone,
            'callback_valid': 'true',
            'callback_date': fecha,
            'callback_time': hora,
        }
        response = self._post(
            payload,
            HTTP_X_OML_CAMPAIGN_ID=str(self.campana.pk),
            HTTP_X_OML_CONTACT_ID=str(self.contacto.pk),
            HTTP_X_OML_CALL_ID=self.call_id,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()['agenda_id'])

    def test_model_validation_error_returns_400_and_rolls_back(self):
        grupo = self.agente_bot.grupo
        grupo.limitar_agendas_personales = True
        grupo.cantidad_agendas_personales = 0
        grupo.save()

        response = self._post(self._payload())
        self.assertEqual(response.status_code, 400)
        self.assertIn('agenda', response.json()['errors'])
        # La transacción debe revertir también la calificación
        self.assertFalse(CalificacionCliente.objects.filter(contacto=self.contacto).exists())
        self.assertFalse(AgendaContacto.objects.filter(contacto=self.contacto).exists())

    def test_unauthenticated_request_rejected(self):
        self.client.logout()
        response = self._post(self._payload())
        self.assertIn(response.status_code, (401, 403))
