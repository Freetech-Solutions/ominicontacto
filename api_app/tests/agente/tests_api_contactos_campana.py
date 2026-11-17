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

from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ominicontacto_app.models import Campana, User
from ominicontacto_app.tests.factories import (
    CampanaFactory, ContactoFactory, QueueFactory, QueueMemberFactory)
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class ApiContactosCampanaTest(OMLBaseTest):
    """ Tests de API_ObtenerContactosCampanaView: un agente sólo puede leer los
        contactos de las campañas de las que es miembro. """

    def setUp(self):
        super(ApiContactosCampanaTest, self).setUp()
        self.agente = self.crear_agente_profile()
        self.campana_dialer, self.contacto_camp_dialer = self._crear_campana_con_contacto(
            self.agente, Campana.TYPE_DIALER)
        self.campana_preview, self.contacto_camp_preview = self._crear_campana_con_contacto(
            self.agente, Campana.TYPE_PREVIEW)
        self.client.login(username=self.agente.user.username, password=PASSWORD)

    def _crear_campana_con_contacto(self, agente, tipo_campana):
        campana = CampanaFactory.create(type=tipo_campana, estado=Campana.ESTADO_ACTIVA)
        queue = QueueFactory.create(campana=campana)
        if agente is not None:
            QueueMemberFactory.create(
                member=agente, queue_name=queue, id_campana=campana.get_queue_id_name())
        contacto = ContactoFactory.create(bd_contacto=campana.bd_contacto)
        return campana, contacto

    def _get_contactos(self, campana_pk, length=10):
        url = reverse('api_contactos_campana', kwargs={'pk_campana': campana_pk})
        return self.client.get(
            url, {'start': 0, 'length': length, 'draw': 1, 'search[value]': ''})

    def test_devuelve_datos_campana_agente(self):
        response = self._get_contactos(self.campana_dialer.pk, length=1)

        self.assertEqual(response.status_code, 200)
        json_content = response.json()
        self.assertEqual(json_content['draw'], 1)
        self.assertEqual(json_content['recordsTotal'], 1)
        self.assertEqual(json_content['recordsFiltered'], 1)
        self.assertEqual(json_content['data'][0][1], str(self.contacto_camp_dialer.telefono))

    def test_no_devuelve_datos_campana_de_la_que_agente_no_es_miembro(self):
        otro_agente = self.crear_agente_profile()
        campana_ajena, contacto_ajeno = self._crear_campana_con_contacto(
            otro_agente, Campana.TYPE_DIALER)

        response = self._get_contactos(campana_ajena.pk)

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(str(contacto_ajeno.telefono), response.content.decode())

    def test_no_devuelve_datos_campana_sin_miembros(self):
        campana_ajena, _ = self._crear_campana_con_contacto(None, Campana.TYPE_MANUAL)

        response = self._get_contactos(campana_ajena.pk)

        self.assertEqual(response.status_code, 404)

    def test_campana_inexistente_devuelve_404(self):
        response = self._get_contactos(999999)

        self.assertEqual(response.status_code, 404)

    def test_agente_deja_de_acceder_al_ser_removido_de_campana(self):
        self.assertEqual(self._get_contactos(self.campana_dialer.pk).status_code, 200)

        self.agente.campana_member.filter(queue_name__campana=self.campana_dialer).delete()

        self.assertEqual(self._get_contactos(self.campana_dialer.pk).status_code, 404)

    def test_agente_solo_accede_a_sus_campanas(self):
        otro_agente = self.crear_agente_profile()
        campana_otro, contacto_otro = self._crear_campana_con_contacto(
            otro_agente, Campana.TYPE_PREVIEW)

        response_propia = self._get_contactos(self.campana_preview.pk)
        response_ajena = self._get_contactos(campana_otro.pk)

        self.assertEqual(response_propia.status_code, 200)
        telefonos = [fila[1] for fila in response_propia.json()['data']]
        self.assertIn(str(self.contacto_camp_preview.telefono), telefonos)
        self.assertNotIn(str(contacto_otro.telefono), telefonos)
        self.assertEqual(response_ajena.status_code, 404)

    def _get_contactos_con_token(self, user, campana_pk):
        token = Token.objects.create(user=user).key
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        url = reverse('api_contactos_campana', args=(campana_pk,))
        return client.get(url, {'search[value]': 1, 'start': 1, 'length': 10, 'draw': 10},
                          format='json')

    def test_es_accesible_usando_token_agente(self):
        self.actualizar_permisos()
        ContactoFactory(bd_contacto=self.campana_dialer.bd_contacto)
        cantidad = self.campana_dialer.bd_contacto.contactos.count()

        response = self._get_contactos_con_token(self.agente.user, self.campana_dialer.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['recordsTotal'], cantidad)

    def test_no_es_accesible_usando_token_no_agente(self):
        self.actualizar_permisos()
        supervisor_admin = self.crear_supervisor_profile(rol=User.ADMINISTRADOR)

        response = self._get_contactos_con_token(supervisor_admin.user, self.campana_dialer.pk)

        self.assertEqual(response.status_code, 403)

    def test_token_agente_no_accede_a_campana_de_la_que_no_es_miembro(self):
        self.actualizar_permisos()
        otro_agente = self.crear_agente_profile()
        campana_ajena, _ = self._crear_campana_con_contacto(otro_agente, Campana.TYPE_DIALER)

        response = self._get_contactos_con_token(self.agente.user, campana_ajena.pk)

        self.assertEqual(response.status_code, 404)
