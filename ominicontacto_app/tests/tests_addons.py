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
Tests de los puntos de enganche del core con los addons: rutas que un addon redefine
(ADDON_URL_OVERRIDES), tags genéricos de mensajes y tareas programadas que trae un addon
"""
from __future__ import unicode_literals

from constance.admin import ConstanceForm, get_values
from constance.test import override_config
from mock import patch
from django.conf import settings
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import resolve, reverse

from ominicontacto.urls import rutas_redefinidas_por_addons
from ominicontacto_app.services.asterisk.regeneracion_cronos import RegeneracionCronosService
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD
from ominicontacto_app.views.base import ConsolaAgenteView
from ominicontacto_app.views.instancia import RegistroFormView

CRONOS = 'ominicontacto_app.services.asterisk.regeneracion_cronos.'
TEXTO = 'Mensaje de prueba'
CLAVES_CONCURRENCIA = ('AGENT_CONCURRENCY_STATE', )


class RutasRedefinidasPorAddonsTest(TestCase):

    def test_sin_addons_la_consola_y_el_registro_son_los_del_core(self):
        self.assertIs(resolve(reverse('consola_de_agente')).func.view_class, ConsolaAgenteView)
        self.assertIs(resolve(reverse('registrar_usuario')).func.view_class, RegistroFormView)

    def test_carga_las_rutas_del_modulo(self):
        rutas = rutas_redefinidas_por_addons(['reciclado_app.urls'])
        self.assertEqual(len(rutas), 1)
        self.assertEqual(rutas[0].urlconf_name.__name__, 'reciclado_app.urls')

    def test_addon_sin_el_modulo_sigue_con_las_vistas_del_core(self):
        self.assertEqual(rutas_redefinidas_por_addons(['ominicontacto_app.no_existe']), [])

    def test_addon_no_instalado_sigue_con_las_vistas_del_core(self):
        with self.assertLogs('ominicontacto.urls', level='ERROR'):
            self.assertEqual(rutas_redefinidas_por_addons(['addon_no_instalado.urls']), [])

    @patch('ominicontacto.urls.include', side_effect=ImportError('vista inexistente'))
    def test_modulo_que_falla_al_importar_sigue_con_las_vistas_del_core(self, include):
        with self.assertLogs('ominicontacto.urls', level='ERROR'):
            self.assertEqual(rutas_redefinidas_por_addons(['reciclado_app.urls']), [])


class TagsDeMensajesTest(OMLBaseTest):

    def mensaje(self, extra_tags, level=constants.ERROR):
        return Message(level, TEXTO, extra_tags=extra_tags)

    def test_ignore_regular_msg_no_se_muestra_como_alerta(self):
        html = render_to_string('messages.html', {'messages': [self.mensaje('ignore_regular_msg')]})
        self.assertNotIn(TEXTO, html)

    def test_los_demas_mensajes_se_muestran_como_alerta(self):
        html = render_to_string('messages.html', {'messages': [self.mensaje('')]})
        self.assertIn(TEXTO, html)

    @patch('django.contrib.messages.context_processors.get_messages')
    def test_popup_msg_se_muestra_como_pop_up_en_el_login(self, get_messages):
        get_messages.return_value = [self.mensaje('ignore_regular_msg popup_msg')]
        response = self.client.get(reverse('login'))
        self.assertContains(response, 'Swal.fire')
        self.assertContains(response, TEXTO, count=1)

    @patch('django.contrib.messages.context_processors.get_messages')
    def test_sin_popup_msg_no_hay_pop_up_en_el_login(self, get_messages):
        get_messages.return_value = [self.mensaje('')]
        response = self.client.get(reverse('login'))
        self.assertNotContains(response, 'Swal.fire')
        self.assertContains(response, TEXTO, count=1)


@patch(CRONOS + 'CronTab')
class TareasProgramadasDeAddonsTest(TestCase):

    def comentarios_programados(self, crontab):
        return [c[1]['comment'] for c in crontab.return_value.new.call_args_list]

    @patch(CRONOS + 'get_commands',
           return_value={'sincronizar_concurrencia_agentes': 'enterprise_app'})
    def test_con_el_comando_del_addon_se_programa(self, get_commands, crontab):
        RegeneracionCronosService().regenerar_cronos()
        self.assertIn('sincronizar_concurrencia_agentes', self.comentarios_programados(crontab))

    @patch(CRONOS + 'get_commands', return_value={})
    def test_sin_el_addon_se_quita(self, get_commands, crontab):
        RegeneracionCronosService().regenerar_cronos()
        self.assertNotIn('sincronizar_concurrencia_agentes', self.comentarios_programados(crontab))
        crontab.return_value.remove_all.assert_any_call(comment='sincronizar_concurrencia_agentes')


class RegistroSinAddonTest(OMLBaseTest):
    ejecutar_actualizar_permisos = True

    def test_sin_addon_no_muestra_el_maximo_de_agentes_concurrentes(self):
        admin = self.crear_administrador()
        admin.is_superuser = True
        admin.save()
        self.client.login(username=admin.username, password=PASSWORD)
        with override_config(CLIENT_NAME='cliente', CLIENT_KEY='OMLkey'):
            response = self.client.get(reverse('registrar_usuario'))
        self.assertContains(response, 'id="sendKey"')
        self.assertNotContains(response, 'id="concurrency"')
        self.assertNotContains(response, 'sync-concurrency.js')


class ClavesDeConcurrenciaEnElAdminTest(OMLBaseTest):
    """ Las claves del límite de agentes concurrentes no se ven ni se editan en constance """

    def test_no_se_muestran_en_el_admin_de_constance(self):
        admin = self.crear_administrador()
        admin.is_superuser = admin.is_staff = True  # el admin por defecto de la plataforma
        admin.save()
        self.client.login(username=admin.username, password=PASSWORD)
        response = self.client.get(reverse('admin:constance_config_changelist'))
        self.assertContains(response, 'CLIENT_NAME')
        for clave in CLAVES_CONCURRENCIA:
            self.assertNotContains(response, clave)

    def test_son_de_solo_lectura(self):
        form = ConstanceForm(initial=get_values())
        for clave in CLAVES_CONCURRENCIA:
            self.assertTrue(form.fields[clave].disabled, clave)

    @override_config(AGENT_CONCURRENCY_STATE='valor firmado')
    def test_un_post_armado_no_cambia_el_valor(self):
        form = ConstanceForm(data={'AGENT_CONCURRENCY_STATE': 'otro'}, initial=get_values())
        form.is_valid()
        self.assertEqual(form['AGENT_CONCURRENCY_STATE'].value(), 'valor firmado')

    def test_no_quedan_claves_de_concurrencia_sin_firmar(self):
        for clave in ('AGENT_CONCURRENCY_LIMIT', 'AGENT_CONCURRENCY_STATUS',
                      'AGENT_CONCURRENCY_CHECKED_AT'):
            self.assertNotIn(clave, settings.CONSTANCE_CONFIG)
