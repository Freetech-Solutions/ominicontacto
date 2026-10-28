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
Tests de la política Deny-by-Default de permisos sobre URLs
"""
from __future__ import unicode_literals

from django.urls import ResolverMatch, reverse

from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD
from ominicontacto_app.models import User
from ominicontacto_app.permisos import PermisoOML


def vista():
    pass


def resolver_match(url_name, namespaces=None, basename=None):
    vista.initkwargs = {'basename': basename} if basename else {}
    return ResolverMatch(vista, (), {}, url_name=url_name, namespaces=namespaces)


class PermisosDenyByDefaultTests(OMLBaseTest):

    def setUp(self):
        super(PermisosDenyByDefaultTests, self).setUp()
        self.usuario_agente = self.crear_user_agente(username='agente1')
        self.agente = self.crear_agente_profile(self.usuario_agente)
        PermisoOML.objects.create(codename='permiso_test_agente', name='permiso_test_agente')
        PermisoOML.objects.create(codename='permiso_test_otro', name='permiso_test_otro')
        permiso_agente = PermisoOML.objects.get(codename='permiso_test_agente')
        self.usuario_agente.groups.get().permissions.add(permiso_agente)
        # Recargo el usuario para no usar la cache de permisos
        self.usuario_agente = User.objects.get(id=self.usuario_agente.id)

    def test_permiso_no_registrado_es_denegado(self):
        self.assertFalse(self.usuario_agente.tiene_permiso_oml('permiso_inexistente'))
        self.assertFalse(self.usuario_agente.tiene_permiso_oml_en_url(
            resolver_match('permiso_inexistente')))

    def test_url_sin_nombre_es_denegada(self):
        self.assertFalse(self.usuario_agente.tiene_permiso_oml_en_url(resolver_match(None)))

    def test_permiso_registrado_respeta_roles(self):
        self.assertTrue(self.usuario_agente.tiene_permiso_oml('permiso_test_agente'))
        self.assertFalse(self.usuario_agente.tiene_permiso_oml('permiso_test_otro'))
        self.assertTrue(self.usuario_agente.tiene_permiso_oml_en_url(
            resolver_match('permiso_test_agente')))
        self.assertFalse(self.usuario_agente.tiene_permiso_oml_en_url(
            resolver_match('permiso_test_otro')))

    def test_url_publica_es_permitida(self):
        self.assertTrue(self.usuario_agente.tiene_permiso_oml('acerca'))
        self.assertTrue(self.usuario_agente.tiene_permiso_oml_en_url(resolver_match('acerca')))

    def test_namespace_publico_es_permitido(self):
        self.assertTrue(self.usuario_agente.tiene_permiso_oml_en_url(
            resolver_match('index', namespaces=['admin'])))

    def test_nombre_de_url_publico_con_otro_namespace_es_denegado(self):
        self.assertFalse(self.usuario_agente.tiene_permiso_oml_en_url(
            resolver_match('acerca', namespaces=['otro'])))

    def test_permiso_registrado_por_basename(self):
        self.assertTrue(self.usuario_agente.tiene_permiso_oml_en_url(
            resolver_match('permiso_test_agente-list', basename='permiso_test_agente')))
        self.assertFalse(self.usuario_agente.tiene_permiso_oml_en_url(
            resolver_match('permiso_test_otro-list', basename='permiso_test_otro')))

    def test_permiso_registrado_con_namespace(self):
        PermisoOML.objects.create(codename='test:permiso_ns', name='test:permiso_ns')
        self.assertFalse(self.usuario_agente.tiene_permiso_oml_en_url(
            resolver_match('permiso_ns', namespaces=['test'])))

    def test_deben_cumplirse_todos_los_permisos_registrados_de_la_url(self):
        self.assertFalse(self.usuario_agente.tiene_permiso_oml_en_url(
            resolver_match('permiso_test_agente', basename='permiso_test_otro')))


class MiddlewarePermisoOMLTests(OMLBaseTest):

    def setUp(self):
        super(MiddlewarePermisoOMLTests, self).setUp()
        usuario_agente = self.crear_user_agente(username='agente1')
        self.crear_agente_profile(usuario_agente)
        self.client.login(username=usuario_agente.username, password=PASSWORD)

    def test_url_publica_es_accesible(self):
        response = self.client.get(reverse('acerca'))
        self.assertEqual(response.status_code, 200)

    def test_url_registrada_para_otro_rol_es_denegada(self):
        response = self.client.get(reverse('user_list', args=(1,)))
        self.assertEqual(response.status_code, 403)

    def test_admin_no_es_bloqueado_por_el_middleware(self):
        # El admin de Django tiene su propio control de acceso (redirige al login del admin)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
