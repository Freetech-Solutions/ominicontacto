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

import json
import random

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from mock import patch

from ominicontacto_app.models import (
    AgendaContacto, Campana, NombreCalificacion, OpcionCalificacion,
)
from ominicontacto_app.tests.factories import (
    AgendaContactoFactory, CalificacionClienteFactory, CampanaFactory,
    ContactoFactory, OpcionCalificacionFactory, QueueFactory, QueueMemberFactory,
)
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class AgendaContactoAPITest(OMLBaseTest):
    ejecutar_actualizar_permisos = True

    def setUp(self):
        super(AgendaContactoAPITest, self).setUp()
        self.agente = self.crear_agente_profile()
        self.agente_2 = self.crear_agente_profile()
        self.client.login(username=self.agente.user.username, password=PASSWORD)

        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA, type=Campana.TYPE_MANUAL)
        self.contacto = ContactoFactory.create()
        self.campana.bd_contacto.contactos.add(self.contacto)

        self.queue = QueueFactory.create(campana=self.campana)
        QueueMemberFactory.create(member=self.agente, queue_name=self.queue)

        self.nombre_calificacion_agenda = NombreCalificacion.objects.get(
            nombre=settings.CALIFICACION_REAGENDA)
        self.opcion_calificacion_agenda = OpcionCalificacionFactory.create(
            campana=self.campana, nombre=self.nombre_calificacion_agenda.nombre,
            tipo=OpcionCalificacion.AGENDA)

        self.url = reverse('api_agenda_contacto_create')

    def _post_data(self, **overrides):
        siguiente_dia = timezone.now() + timezone.timedelta(days=1)
        data = {
            'campaign_id': self.campana.id,
            'contact_id': self.contacto.id,
            'date': siguiente_dia.date().isoformat(),
            'time': siguiente_dia.time().replace(microsecond=0).isoformat(),
            'phone': random.choice(self.contacto.lista_de_telefonos_de_contacto()),
            'schedule_type': AgendaContacto.TYPE_PERSONAL,
            'observations': 'test_schedule',
        }
        data.update(overrides)
        return data

    def _post(self, data):
        return self.client.post(
            self.url,
            json.dumps(data),
            content_type='application/json',
        )

    def test_crear_agenda_exitosa(self):
        response = self._post(self._post_data())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'OK')
        self.assertTrue(data['created'])
        agenda = AgendaContacto.objects.get(pk=data['agenda_id'])
        self.assertEqual(agenda.agente, self.agente)
        self.assertEqual(agenda.contacto, self.contacto)
        self.assertEqual(agenda.campana, self.campana)

    def test_upsert_agenda_existente(self):
        agenda_existente = AgendaContactoFactory.create(
            agente=self.agente, contacto=self.contacto, campana=self.campana,
            observaciones='vieja')
        post_data = self._post_data(observations='nueva')
        response = self._post(post_data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'OK')
        self.assertFalse(data['created'])
        self.assertEqual(data['agenda_id'], agenda_existente.id)
        agenda_existente.refresh_from_db()
        self.assertEqual(agenda_existente.observaciones, 'nueva')

    def test_agente_no_asignado_a_campana_403(self):
        self.client.logout()
        self.client.login(username=self.agente_2.user.username, password=PASSWORD)
        response = self._post(self._post_data())
        self.assertEqual(response.status_code, 403)

    def test_telefono_invalido_400(self):
        response = self._post(self._post_data(phone='00110011'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'ERROR')

    def test_tipo_agenda_global_en_campana_no_dialer_400(self):
        response = self._post(self._post_data(schedule_type=AgendaContacto.TYPE_GLOBAL))
        self.assertEqual(response.status_code, 400)
        self.assertIn('schedule_type', response.json()['errors'])

    @patch('ominicontacto_app.services.agenda_contacto.get_dialer_service')
    def test_agenda_global_dialer_notifica_solo_en_create(self, get_dialer_service):
        dialer_service = get_dialer_service.return_value
        self.campana.type = Campana.TYPE_DIALER
        self.campana.save()

        response_create = self._post(self._post_data(schedule_type=AgendaContacto.TYPE_GLOBAL))
        self.assertEqual(response_create.status_code, 200)
        self.assertTrue(response_create.json()['created'])
        dialer_service.agendar_llamada.assert_called_once()

        dialer_service.agendar_llamada.reset_mock()
        response_update = self._post(self._post_data(
            schedule_type=AgendaContacto.TYPE_GLOBAL,
            observations='actualizada'))
        self.assertEqual(response_update.status_code, 200)
        self.assertFalse(response_update.json()['created'])
        dialer_service.agendar_llamada.assert_not_called()

    def test_actualiza_calificacion_agendado(self):
        calificacion = CalificacionClienteFactory.create(
            opcion_calificacion=self.opcion_calificacion_agenda,
            agente=self.agente,
            contacto=self.contacto,
            agendado=False)
        response = self._post(self._post_data())
        self.assertEqual(response.status_code, 200)
        calificacion.refresh_from_db()
        self.assertTrue(calificacion.agendado)
        self.assertEqual(calificacion.tipo_agenda, AgendaContacto.TYPE_PERSONAL)

    def test_campana_inexistente_404(self):
        response = self._post(self._post_data(campaign_id=999999999))
        self.assertEqual(response.status_code, 404)

    def test_contacto_inexistente_404(self):
        response = self._post(self._post_data(contact_id=999999999))
        self.assertEqual(response.status_code, 404)
