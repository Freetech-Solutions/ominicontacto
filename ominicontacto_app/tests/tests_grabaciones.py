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
Tests relacionados con las grabaciones
"""

from __future__ import unicode_literals

import json
import os
from urllib.parse import urlencode
from unittest.mock import MagicMock, patch
from django.conf import settings
from django.urls import reverse
from django.utils.timezone import now, timedelta
from django.contrib.auth.models import Group
from django.test import TransactionTestCase, override_settings

from simple_history.utils import update_change_reason

from ominicontacto_app.models import GrabacionMarca, OpcionCalificacion, Campana, User

from ominicontacto_app.bgtasks.mixins import SearchRecordingsMixin
from ominicontacto_app.tests.factories import CalificacionClienteFactory, CampanaFactory, \
    ContactoFactory, GrabacionMarcaFactory, LlamadaLogFactory, \
    OpcionCalificacionFactory, QueueFactory, QueueMemberFactory
from ominicontacto_app.tests.utiles import OMLTestUtilsMixin

from ominicontacto_app.utiles import fecha_hora_local, fecha_local
from reportes_app.models import LlamadaLog


class BaseGrabacionesTests(TransactionTestCase, OMLTestUtilsMixin):

    databases = {'default', 'replica'}

    def setUp(self):
        super(BaseGrabacionesTests, self).setUp()
        Group.objects.get_or_create(name=User.SUPERVISOR)
        Group.objects.get_or_create(name=User.AGENTE)

        self.supervisor1 = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.supervisor2 = self.crear_supervisor_profile(rol=User.SUPERVISOR)

        self.agente1 = self.crear_agente_profile()
        self.agente2 = self.crear_agente_profile()

        self.campana1 = CampanaFactory(estado=Campana.ESTADO_ACTIVA)
        self.queue_campana_1 = QueueFactory(campana=self.campana1)
        QueueMemberFactory(member=self.agente1, queue_name=self.queue_campana_1)
        self.campana1.supervisors.add(self.supervisor1.user)

        self.campana2 = CampanaFactory(estado=Campana.ESTADO_ACTIVA)
        self.queue_campana_2 = QueueFactory(campana=self.campana2)
        QueueMemberFactory(member=self.agente2, queue_name=self.queue_campana_2)
        self.campana2.supervisors.add(self.supervisor2.user)

        self.contacto = ContactoFactory(id_externo='id_ext')
        self.campana3 = CampanaFactory(estado=Campana.ESTADO_ACTIVA)
        self.campana3.bd_contacto.genera_contactos([self.contacto])
        self.campana3.supervisors.add(self.supervisor1.user)

        self.opcion_calificacion = OpcionCalificacionFactory(
            campana=self.campana1, tipo=OpcionCalificacion.GESTION)
        self.calificacion = CalificacionClienteFactory(opcion_calificacion=self.opcion_calificacion)
        update_change_reason(self.calificacion, 'calificacion')

        self.llamada_log1 = LlamadaLogFactory.create(duracion_llamada=1, agente_id=self.agente1.id,
                                                     callid=self.calificacion.callid,
                                                     campana_id=self.campana1.id,
                                                     contacto_id='-1', event='COMPLETEAGENT')
        self.llamada_log2 = LlamadaLogFactory.create(duracion_llamada=1, agente_id=self.agente1.id,
                                                     campana_id=self.campana1.id,
                                                     event='COMPLETEAGENT')
        self.llamada_log3 = LlamadaLogFactory.create(duracion_llamada=1, agente_id=self.agente1.id,
                                                     campana_id=self.campana1.id,
                                                     event='COMPLETEAGENT')
        self.marca_campana1 = GrabacionMarcaFactory(callid=self.llamada_log1.callid)
        self.marca_campana2 = GrabacionMarcaFactory(callid=self.llamada_log2.callid)

        self.llamada_log2_1 = LlamadaLogFactory.create(duracion_llamada=1,
                                                       agente_id=self.agente2.id,
                                                       campana_id=self.campana2.id,
                                                       event='COMPLETEAGENT')
        self.marca_campana2_1 = GrabacionMarcaFactory(callid=self.llamada_log2_1.callid)

        self.llamada_log3_1 = LlamadaLogFactory.create(numero_marcado=self.contacto.telefono,
                                                       agente_id=self.agente2.id,
                                                       campana_id=self.campana3.id,
                                                       event='COMPLETEAGENT')

        (_, hace_mucho, ahora) = self._obtener_fechas()
        self.rango_hace_mucho = hace_mucho.date().strftime('%d/%m/%Y') + ' - ' + \
            ahora.date().strftime('%d/%m/%Y')

    def _obtener_fechas(self):
        hoy = fecha_hora_local(now())
        hace_mucho = hoy - timedelta(days=3)
        ahora = fecha_hora_local(now())
        return (hoy, hace_mucho, ahora)

    def _search_recordings(self, user, formdata):
        """
        Valida los filtros y ejecuta la búsqueda tal como lo hace el worker de
        background-tasks, sin pasar por websockets ni channel layer.
        El circuito de mensajes se testea en tests_bgtasks_busqueda_grabaciones.
        """
        formdata.setdefault("pagina", "1")
        formdata.setdefault("grabaciones_x_pagina", "10")
        formdata.setdefault("BASE_URL", "/")
        mixin = SearchRecordingsMixin()
        campanas, _, form_is_valid, query, errors, role = \
            mixin.parse_recording_search_request(user, urlencode(formdata))
        self.assertTrue(form_is_valid, errors)
        return mixin.build_recording_search_result(
            query, [campana.id for campana in campanas], role, {"BASE_URL": formdata["BASE_URL"]}
        )

    @staticmethod
    def llamadalog_filter_update(filter_id, **update_attrs):
        LlamadaLog.objects.filter(id=filter_id).update(**update_attrs)


class GrabacionesTests(BaseGrabacionesTests):

    def setUp(self):
        super(GrabacionesTests, self).setUp()
        self.client.login(username=self.supervisor1.user, password=self.DEFAULT_PASSWORD)

    def test_vista_creacion_grabaciones_marcadas(self):
        url = reverse('grabacion_marcar')
        descripcion = 'descripcion de prueba'
        post_data = {'callid': self.llamada_log3.callid,
                     'descripcion': descripcion}
        self.client.post(url, post_data)

        self.assertTrue(GrabacionMarca.objects.filter(
            callid=self.llamada_log3.callid, descripcion=descripcion).exists())

    def test_usuarios_no_logueados_no_acceden_a_vista_creacion_grabaciones_marcadas(self):
        self.client.logout()
        url = reverse('grabacion_marcar')
        descripcion = 'descripcion de prueba'
        post_data = {'callid': self.llamada_log3.callid,
                     'descripcion': descripcion}
        self.client.post(url, post_data)
        self.assertFalse(GrabacionMarca.objects.filter(
            callid=self.llamada_log3.callid, descripcion=descripcion).exists())

    def test_usuarios_no_logueados_no_acceden_a_obtener_descripciones_grabaciones(self):
        self.client.logout()
        url = reverse('grabacion_descripcion', kwargs={'callid': self.llamada_log1.callid})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.template_name, 'registration/login.html')

    def test_respuesta_api_descripciones_grabaciones_marcadas(self):
        url = reverse('grabacion_descripcion', kwargs={'callid': self.llamada_log2.callid})
        response = self.client.get(url, follow=True)
        data_response = json.loads(response.content)
        self.assertEqual(data_response['result'], 'Descripción')

    def test_respuesta_api_descripciones_grabaciones_no_marcadas(self):
        url = reverse('grabacion_descripcion', kwargs={'callid': self.llamada_log3.callid})
        response = self.client.get(url, follow=True)
        data_response = json.loads(response.content)
        self.assertEqual(data_response['result'], 'No encontrada')

    def test_url_de_grabacion_segun_fecha(self):
        hoy = now()
        hace_mucho = hoy - timedelta(days=3)
        self.llamada_log2.time = hace_mucho
        self.llamada_log1.time = hoy
        self.assertTrue(self.llamada_log2.url_archivo_grabacion.endswith(settings.MONITORFORMAT))
        self.assertTrue(self.llamada_log1.url_archivo_grabacion.endswith(settings.MONITORFORMAT))


class FiltrosBusquedaGrabacionesSupervisorTests(BaseGrabacionesTests):

    def setUp(self):
        super(FiltrosBusquedaGrabacionesSupervisorTests, self).setUp()
        self.usuario = self.supervisor1.user

    def test_filtro_grabaciones_marcadas(self):
        self.assertEqual(LlamadaLog.objects.obtener_grabaciones_marcadas().count(), 3)

    def test_supervisor_busca_solo_en_campanas_asignadas(self):
        campanas, _, _, _, _, role = SearchRecordingsMixin().parse_recording_search_request(
            self.usuario, urlencode({"fecha": self.rango_hace_mucho}))
        self.assertEqual(role, "supervisor")
        self.assertEqual(set(campanas), {self.campana1, self.campana3})

    def test_filtros_invalidos_devuelven_errores(self):
        _, _, form_is_valid, _, errors, _ = SearchRecordingsMixin().parse_recording_search_request(
            self.usuario, urlencode({
                "fecha": self.rango_hace_mucho,
                "pagina": "1",
                "grabaciones_x_pagina": "7",
            }))
        self.assertFalse(form_is_valid)
        self.assertIn("grabaciones_x_pagina", errors)

    def test_fecha_ausente_o_mal_formada_devuelve_error(self):
        for fecha in (None, '', '01/01/2024', '01/01/2024 - ', 'hoy - mañana',
                      '31/02/2024 - 01/03/2024'):
            formdata = {"pagina": "1", "grabaciones_x_pagina": "10"}
            if fecha is not None:
                formdata["fecha"] = fecha
            _, _, form_is_valid, _, errors, _ = \
                SearchRecordingsMixin().parse_recording_search_request(
                    self.usuario, urlencode(formdata))
            self.assertFalse(form_is_valid, msg=repr(fecha))
            self.assertIn("fecha", errors, msg=repr(fecha))

    def test_buscar_grabaciones_por_duracion(self):
        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
        })["fragments"]["#table-body"]
        self.assertIn(self.llamada_log1.numero_marcado, response)
        self.assertIn(self.llamada_log2.numero_marcado, response)
        self.assertIn(self.llamada_log3.numero_marcado, response)
        # Aseguro que no traiga la grabacion de una campaña que no tiene asignada.
        self.assertNotIn(self.llamada_log2_1.numero_marcado, response)

        self.llamadalog_filter_update(
            self.llamada_log2.id,
            duracion_llamada=15,
            numero_marcado='42222222',
        )
        self.llamadalog_filter_update(
            self.llamada_log1.id,
            duracion_llamada=15,
            numero_marcado='41111111',
        )
        self.llamadalog_filter_update(
            self.llamada_log3.id,
            duracion_llamada=12,
            numero_marcado='43333333',
        )

        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
            "duracion": 12,
        })["fragments"]["#table-body"]
        self.assertIn('41111111', response)
        self.assertIn('42222222', response)
        self.assertIn('43333333', response)
        self.assertNotIn(self.llamada_log2_1.numero_marcado, response)

        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
            "duracion": 15,
        })["fragments"]["#table-body"]
        self.assertIn('41111111', response)
        self.assertIn('42222222', response)
        self.assertNotIn('43333333', response)

        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
            "duracion": 16,
        })["fragments"]["#table-body"]
        self.assertNotIn('41111111', response)
        self.assertNotIn('42222222', response)
        self.assertNotIn('43333333', response)

    def test_buscar_grabaciones_por_fecha(self):
        (hoy, hace_mucho, ahora) = self._obtener_fechas()
        if hoy.date() < ahora.date():
            (hoy, hace_mucho, ahora) = self._obtener_fechas()
        self.llamadalog_filter_update(
            self.llamada_log2.id,
            time=hace_mucho,
            numero_marcado='42222222',
        )
        self.llamadalog_filter_update(
            self.llamada_log1.id,
            time=hoy,
            numero_marcado='41111111',
        )
        self.llamadalog_filter_update(
            self.llamada_log3.id,
            time=hoy,
            numero_marcado='43333333',
        )
        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
        })["fragments"]["#table-body"]
        self.assertIn('41111111', response)
        self.assertIn('42222222', response)
        self.assertIn('43333333', response)

        rango_hoy = ahora.date().strftime('%d/%m/%Y') + ' - ' + ahora.date().strftime('%d/%m/%Y')
        response = self._search_recordings(self.usuario, {
            "fecha": rango_hoy,
        })["fragments"]["#table-body"]
        self.assertNotIn('42222222', response)
        self.assertIn('41111111', response)
        self.assertIn('43333333', response)

    def test_filtro_grabaciones_calificadas_gestion_muestra_gestionadas(self):
        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
            "gestion": True,
        })["fragments"]["#table-body"]
        self.assertIn(self.llamada_log1.numero_marcado, response)
        self.assertNotIn(self.llamada_log2.numero_marcado, response)
        self.assertNotIn(self.llamada_log3.numero_marcado, response)

    def test_filtro_grabaciones_calificadas_gestion_excluye_no_gestionadas(self):
        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
            "gestion": False,
        })["fragments"]["#table-body"]
        self.assertIn(self.llamada_log1.numero_marcado, response)
        self.assertIn(self.llamada_log2.numero_marcado, response)
        self.assertIn(self.llamada_log3.numero_marcado, response)

    def test_buscar_grabaciones_por_callid(self):
        self.llamadalog_filter_update(self.llamada_log1.id, callid='1')
        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
            "callid": "1",
        })["fragments"]["#table-body"]
        self.assertIn(self.llamada_log1.numero_marcado, response)
        self.assertNotIn(self.llamada_log2.numero_marcado, response)
        self.assertNotIn(self.llamada_log3.numero_marcado, response)

    def test_buscar_grabaciones_por_id_contacto_externo(self):
        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
            "id_contacto_externo": "id_ext"
        })["fragments"]["#table-body"]
        self.assertIn(self.llamada_log3_1.numero_marcado, response)
        self.assertNotIn(self.llamada_log1.numero_marcado, response)
        self.assertNotIn(self.llamada_log3.numero_marcado, response)


class FiltrosBusquedaGrabacionesAgenteTests(BaseGrabacionesTests):

    def setUp(self):
        super(FiltrosBusquedaGrabacionesAgenteTests, self).setUp()
        self.usuario = self.agente1.user

    def test_agente_no_puede_buscar_como_otro_agente(self):
        _, _, form_is_valid, query, _, role = \
            SearchRecordingsMixin().parse_recording_search_request(
                self.usuario, urlencode({
                    "fecha": self.rango_hace_mucho,
                    "pagina": "1",
                    "grabaciones_x_pagina": "10",
                    "agente": self.agente2.id,
                }))
        self.assertTrue(form_is_valid)
        self.assertEqual(role, "agente")
        self.assertEqual(query["agente"], self.agente1.id)

    def test_ve_solamente_grabaciones_propias(self):
        response = self._search_recordings(self.usuario, {
            "fecha": self.rango_hace_mucho,
        })["fragments"]["#table-body"]
        self.assertIn(self.llamada_log1.numero_marcado, response)
        self.assertIn(self.llamada_log2.numero_marcado, response)
        self.assertIn(self.llamada_log3.numero_marcado, response)
        self.assertNotIn(self.llamada_log2_1.numero_marcado, response)

    def test_ve_solamente_grabaciones_propias_antes_de_filtrar(self):
        agente3 = self.crear_agente_profile()
        QueueMemberFactory(member=agente3, queue_name=self.queue_campana_1)
        llamada_log3_3 = LlamadaLogFactory.create(
            duracion_llamada=1, agente_id=agente3.id, campana_id=self.campana1.id)

        ahora = self._obtener_fechas()[2]
        rango_hoy = ahora.date().strftime('%d/%m/%Y') + ' - ' + ahora.date().strftime('%d/%m/%Y')
        response = self._search_recordings(self.usuario, {
            "fecha": rango_hoy,
        })
        self.assertIn(self.llamada_log1.numero_marcado, response["fragments"]["#table-body"])
        self.assertIn(self.llamada_log2.numero_marcado, response["fragments"]["#table-body"])
        self.assertIn(self.llamada_log3.numero_marcado, response["fragments"]["#table-body"])
        self.assertNotIn(llamada_log3_3.numero_marcado, response["fragments"]["#table-body"])


def _filename_desde_log(llamada_log):
    dia = fecha_local(llamada_log.time).strftime('%Y-%m-%d')
    return f'/{dia}/{llamada_log.callid}.{settings.MONITORFORMAT}'


@patch.dict(os.environ, {'S3_STORAGE_ENABLED': 'true'})
class AutorizacionGrabacionesTests(BaseGrabacionesTests):
    """IDOR/BFLA: oráculo de firma, call_record, descripción y exportación."""

    def _filename_propia_agente1(self):
        return _filename_desde_log(self.llamada_log1)

    def _filename_ajena(self):
        return _filename_desde_log(self.llamada_log2_1)

    @patch('api_app.views.grabaciones.StorageService')
    def test_agente_firma_grabacion_propia_ok(self, mock_storage_cls):
        mock_storage = MagicMock()
        mock_storage.get_file_url.return_value = 'https://example.test/signed'
        mock_storage_cls.return_value = mock_storage
        self.client.login(username=self.agente1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_grabacion_archivo')
        response = self.client.get(url, {'filename': self._filename_propia_agente1()})
        self.assertEqual(response.status_code, 302)
        mock_storage.get_file_url.assert_called_once()

    @patch('api_app.views.grabaciones.StorageService')
    def test_agente_no_firma_grabacion_ajena(self, mock_storage_cls):
        self.client.login(username=self.agente1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_grabacion_archivo')
        response = self.client.get(url, {'filename': self._filename_ajena()})
        self.assertEqual(response.status_code, 404)
        mock_storage_cls.return_value.get_file_url.assert_not_called()

    @patch('api_app.views.grabaciones.StorageService')
    def test_supervisor_firma_campana_asignada_ok(self, mock_storage_cls):
        mock_storage = MagicMock()
        mock_storage.get_file_url.return_value = 'https://example.test/signed'
        mock_storage_cls.return_value = mock_storage
        self.client.login(username=self.supervisor1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_grabacion_archivo')
        response = self.client.get(url, {'filename': self._filename_propia_agente1()})
        self.assertEqual(response.status_code, 302)

    @patch('api_app.views.grabaciones.StorageService')
    def test_supervisor_no_firma_campana_ajena(self, mock_storage_cls):
        self.client.login(username=self.supervisor1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_grabacion_archivo')
        response = self.client.get(url, {'filename': self._filename_ajena()})
        self.assertEqual(response.status_code, 404)
        mock_storage_cls.return_value.get_file_url.assert_not_called()

    def test_filename_invalido_o_traversal_devuelve_404(self):
        self.client.login(username=self.supervisor1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_grabacion_archivo')
        for bad in ('', '../etc/passwd', '/secret/key.txt', '/zip/../etc/passwd'):
            response = self.client.get(url, {'filename': bad} if bad else {})
            self.assertEqual(response.status_code, 404, msg=repr(bad))

    @patch('api_app.views.grabaciones.StorageService')
    def test_firma_fecha_historica_sin_guiones_ok(self, mock_storage_cls):
        mock_storage = MagicMock()
        mock_storage.get_file_url.return_value = 'https://example.test/signed'
        mock_storage_cls.return_value = mock_storage
        self.client.login(username=self.supervisor1.user, password=self.DEFAULT_PASSWORD)
        dia = fecha_local(self.llamada_log1.time).strftime('%Y%m%d')
        filename = f'/{dia}/{self.llamada_log1.callid}.{settings.MONITORFORMAT}'
        url = reverse('api_grabacion_archivo')
        response = self.client.get(url, {'filename': filename})
        self.assertEqual(response.status_code, 302)
        mock_storage.get_file_url.assert_called_once()

    @patch('api_app.views.grabaciones.StorageService')
    def test_firma_artefactos_speech_analytics_ok(self, mock_storage_cls):
        mock_storage = MagicMock()
        mock_storage.get_file_url.return_value = 'https://example.test/signed'
        mock_storage_cls.return_value = mock_storage
        self.client.login(username=self.supervisor1.user, password=self.DEFAULT_PASSWORD)
        dia = fecha_local(self.llamada_log1.time).strftime('%Y-%m-%d')
        url = reverse('api_grabacion_archivo')
        for ext in ('json', 'txt'):
            mock_storage.reset_mock()
            filename = f'/{dia}/{self.llamada_log1.callid}.{ext}'
            response = self.client.get(url, {'filename': filename})
            self.assertEqual(response.status_code, 302, msg=ext)
            mock_storage.get_file_url.assert_called_once()

    def test_zip_de_otro_usuario_devuelve_404(self):
        self.client.login(username=self.supervisor1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_grabacion_archivo')
        response = self.client.get(
            url, {'filename': f'/zip/{self.supervisor2.user.username}-grabaciones.zip'})
        self.assertEqual(response.status_code, 404)

    def test_call_record_agente_propia_ok(self):
        self.client.login(username=self.agente1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_call_record_url', kwargs={'callid': self.llamada_log1.callid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'OK')

    def test_call_record_agente_ajena_404(self):
        self.client.login(username=self.agente1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_call_record_url', kwargs={'callid': self.llamada_log2_1.callid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_call_record_supervisor_campana_ajena_404(self):
        self.client.login(username=self.supervisor1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_call_record_url', kwargs={'callid': self.llamada_log2_1.callid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_descripcion_agente_ajena_indistinguible(self):
        self.client.login(username=self.agente1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('grabacion_descripcion', kwargs={'callid': self.llamada_log2_1.callid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['result'], 'No encontrada')

    def test_descripcion_supervisor_propia_ok(self):
        self.client.login(username=self.supervisor1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('grabacion_descripcion', kwargs={'callid': self.llamada_log2.callid})
        response = self.client.get(url)
        data = json.loads(response.content)
        self.assertEqual(data['result'], 'Descripción')

    def test_agente_no_exporta_grabacion_ajena(self):
        self.client.login(username=self.agente1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_grabacion_descarga_masiva')
        payload = {
            'files': json.dumps([{
                'archivo': self._filename_ajena().lstrip('/'),
                'fecha': '',
                'tipo_llamada': '',
                'telefono_cliente': '',
                'agente': '',
                'campana': '',
                'calificacion': '',
            }]),
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 404)

    def test_agente_sin_permiso_oml_descarga_masiva(self):
        from django.apps import apps as django_apps
        api_app = django_apps.get_app_config('api_app')
        roles_descarga = None
        for conf in api_app.configuraciones_de_permisos():
            if conf['nombre'] == 'api_grabacion_descarga_masiva':
                roles_descarga = conf['roles']
                break
        self.assertIsNotNone(roles_descarga)
        self.assertNotIn('Agente', roles_descarga)

        self.client.login(username=self.agente1.user, password=self.DEFAULT_PASSWORD)
        url = reverse('api_grabacion_descarga_masiva')
        payload = {
            'files': json.dumps([{
                'archivo': self._filename_propia_agente1().lstrip('/'),
                'fecha': '',
                'tipo_llamada': '',
                'telefono_cliente': '',
                'agente': '',
                'campana': '',
                'calificacion': '',
            }]),
        }
        with patch.object(User, 'tiene_permiso_oml', return_value=False):
            response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 403)


class StoragePresignedUrlTtlTests(TransactionTestCase):

    @override_settings(STORAGE_PRESIGNED_URL_TTL=120, SESSION_COOKIE_AGE=600)
    @patch('api_app.services.storage_service.boto3.client')
    def test_get_file_url_usa_ttl_de_settings(self, mock_boto_client):
        from api_app.services.storage_service import StorageService

        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = (
            'http://minio:9000/bucket/key?X-Amz-Signature=x'
        )
        mock_boto_client.return_value = mock_client

        with patch.dict(os.environ, {
            'BUCKET_ACCESS_KEY_ID': 'k',
            'BUCKET_SECRET_ACCESS_KEY': 's',
            'BUCKET_NAME': 'bucket',
            'BUCKET_ENDPOINT': 'http://public',
            'BUCKET_ENDPOINT_INTERNAL': 'http://minio:9000',
            'CALLREC_DEVICE': 's3',
        }):
            service = StorageService()
            service.get_file_url('/2024-01-01/abc.mp3')

        kwargs = mock_client.generate_presigned_url.call_args.kwargs
        self.assertEqual(kwargs['ExpiresIn'], 120)
