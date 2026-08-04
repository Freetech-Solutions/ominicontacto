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
Tests relacionados con la signación de supervisores a campañas
"""
from django.urls import reverse
from django.utils.translation import gettext as _

from ominicontacto_app.tests.utiles import OMLBaseTest
from ominicontacto_app.models import User, Campana

from mock import MagicMock

from ominicontacto_app.services.audio_conversor import ConversorDeAudioService


class AsignacionSupervisoresACampanasTests(OMLBaseTest):

    TYPES = [Campana.TYPE_ENTRANTE, Campana.TYPE_MANUAL,
             Campana.TYPE_PREVIEW, Campana.TYPE_DIALER, ]
    TYPE_SUPERVISORS_URL = {
        Campana.TYPE_ENTRANTE: 'campana_supervisors',
        Campana.TYPE_MANUAL: 'campana_manual_supervisors',
        Campana.TYPE_PREVIEW: 'campana_preview_supervisors',
        Campana.TYPE_DIALER: 'campana_dialer_supervisors'
    }
    TYPE_LIST_URL = {
        Campana.TYPE_ENTRANTE: 'campana_list',
        Campana.TYPE_MANUAL: 'campana_manual_list',
        Campana.TYPE_PREVIEW: 'campana_preview_list',
        Campana.TYPE_DIALER: 'campana_dialer_list'
    }

    def setUp(self):
        super(AsignacionSupervisoresACampanasTests, self).setUp()
        self.supervisor_creador = self.crear_supervisor_profile(rol=User.SUPERVISOR, user=None)
        self.supervisor_no_creador = self.crear_supervisor_profile(rol=User.SUPERVISOR, user=None)
        ConversorDeAudioService._convertir_audio = MagicMock()
        self.campanas = {}
        self.campanas[Campana.TYPE_PREVIEW] = self.crear_campana(
            type=Campana.TYPE_PREVIEW, user=self.supervisor_creador.user)
        self.campanas[Campana.TYPE_MANUAL] = self.crear_campana_manual(
            user=self.supervisor_creador.user)
        self.campanas[Campana.TYPE_ENTRANTE] = self.crear_campana_entrante(
            user=self.supervisor_creador.user)
        self.campanas[Campana.TYPE_DIALER] = self.crear_campana_dialer(
            user=self.supervisor_creador.user)

    def test_supervisor_tiene_acceso_a_asignar_supervisores_a_campanas_propias(self):
        for type in self.TYPES:
            supervisors_url = self.TYPE_SUPERVISORS_URL[type]
            self.client.login(username=self.supervisor_creador.user.username,
                              password=self.DEFAULT_PASSWORD)
            url = reverse(supervisors_url, args=[self.campanas[type].id, ])
            response = self.client.get(url, follow=True)
            self.assertTemplateUsed(response, 'campanas/campana_dialer/campana_supervisors.html')

    def test_supervisor_tiene_acceso_a_asignar_supervisores_a_campanas_ajenas_asignadas(self):
        for type in self.TYPES:
            campana = self.campanas[type]
            campana.supervisors.add(self.supervisor_no_creador.user)
            supervisors_url = self.TYPE_SUPERVISORS_URL[type]
            self.client.login(username=self.supervisor_no_creador.user.username,
                              password=self.DEFAULT_PASSWORD)
            url = reverse(supervisors_url, args=[campana.id, ])
            response = self.client.get(url, follow=True)
            response = self.client.get(url, follow=True)
            self.assertTemplateUsed(response, 'campanas/campana_dialer/campana_supervisors.html')

    def test_supervisor_no_tiene_acceso_a_asignar_supervisores_a_campanas_ajenas_no_asignadas(self):
        for type in self.TYPES:
            supervisors_url = self.TYPE_SUPERVISORS_URL[type]
            list_url = self.TYPE_LIST_URL[type]
            self.client.login(username=self.supervisor_no_creador.user.username,
                              password=self.DEFAULT_PASSWORD)
            url = reverse(supervisors_url, args=[self.campanas[type].id, ])
            response = self.client.get(url, follow=True)
            self.assertRedirects(response, reverse(list_url))
            self.assertContains(response,
                                _("No tiene permiso para asignar supervisores a esta campaña."))

    def test_opciones_de_reportes_email_disponibles_en_todos_los_tipos_de_campana(self):
        self.client.login(username=self.supervisor_creador.user.username,
                          password=self.DEFAULT_PASSWORD)

        for type in self.TYPES:
            campana = self.campanas[type]
            campana.estado = Campana.ESTADO_ACTIVA
            campana.email_habilitado = True
            campana.save(update_fields=['estado', 'email_habilitado'])

            response = self.client.get(reverse(self.TYPE_LIST_URL[type]))

            self.assertContains(
                response,
                'embed/email/campaigns/{0}/conversations'.format(campana.pk))
            self.assertContains(
                response,
                'embed/email/campaigns/{0}/reports'.format(campana.pk))

    def test_opciones_de_reportes_email_ocultas_si_la_canalidad_esta_desactivada(self):
        self.client.login(username=self.supervisor_creador.user.username,
                          password=self.DEFAULT_PASSWORD)

        for type in self.TYPES:
            campana = self.campanas[type]
            campana.estado = Campana.ESTADO_ACTIVA
            campana.email_habilitado = False
            campana.save(update_fields=['estado', 'email_habilitado'])

            response = self.client.get(reverse(self.TYPE_LIST_URL[type]))

            self.assertNotContains(
                response,
                'embed/email/campaigns/{0}/conversations'.format(campana.pk))
            self.assertNotContains(
                response,
                'embed/email/campaigns/{0}/reports'.format(campana.pk))
