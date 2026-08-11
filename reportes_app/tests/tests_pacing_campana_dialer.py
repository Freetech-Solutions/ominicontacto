# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

# This file is part of OMniLeads

from __future__ import unicode_literals

from mock import MagicMock, patch

from django.urls import reverse

from ominicontacto_app.models import Campana
from ominicontacto_app.tests.factories import CampanaFactory, QueueFactory
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class PacingCampanaDialerViewTests(OMLBaseTest):

    def setUp(self):
        super(PacingCampanaDialerViewTests, self).setUp()
        self.usuario = self.crear_administrador()
        self.client.login(username=self.usuario.username, password=PASSWORD)
        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA, type=Campana.TYPE_DIALER)
        QueueFactory.create(campana=self.campana, initial_predictive_model=True)

    @patch('reportes_app.views_campanas_dialer_reportes.get_dialer_service')
    def test_pacing_json_presente(self, mock_get_dialer):
        pacing = {
            'MODE': 'PREDICTIVE',
            'REASON': 'ok',
            'GAMMA': 1.0,
            'C_DIAL': 4,
            'P_HIT': 0.5,
            'DROP_RATE': 0.01,
            'A_FREE': 2.0,
            'A_EXPECTED': 1.4,
            'C_RINGING': 3,
            'THROTTLE_STREAK': 0,
            'THROTTLE_LATCHED': 0,
            'EVENT': '',
            'TS': 1710000000,
        }
        dialer = MagicMock()
        dialer.obtener_pacing_campana.return_value = pacing
        mock_get_dialer.return_value = dialer

        url = reverse('campana_dialer_pacing')
        response = self.client.get(url, {'pk_campana': self.campana.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['pacing'], pacing)
        dialer.obtener_pacing_campana.assert_called_once_with(self.campana)

    @patch('reportes_app.views_campanas_dialer_reportes.get_dialer_service')
    def test_pacing_json_null_si_redis_vacio(self, mock_get_dialer):
        dialer = MagicMock()
        dialer.obtener_pacing_campana.return_value = None
        mock_get_dialer.return_value = dialer

        url = reverse('campana_dialer_pacing')
        response = self.client.get(url, {'pk_campana': self.campana.id})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['pacing'])

    @patch('reportes_app.views_campanas_dialer_reportes.get_dialer_service')
    def test_pacing_json_null_si_motor_sin_metodo(self, mock_get_dialer):
        dialer = MagicMock(spec=[])
        mock_get_dialer.return_value = dialer

        url = reverse('campana_dialer_pacing')
        response = self.client.get(url, {'pk_campana': self.campana.id})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['pacing'])

    @patch('reportes_app.views_campanas_dialer_reportes.get_dialer_service')
    def test_detalle_servicio_incluye_pacing_en_contexto(self, mock_get_dialer):
        pacing = {'MODE': 'PREDICTIVE', 'REASON': 'ok', 'GAMMA': 1.0, 'C_DIAL': 2,
                  'P_HIT': 0.4, 'DROP_RATE': 0.0, 'A_FREE': 1.0, 'A_EXPECTED': 0.5,
                  'C_RINGING': 1, 'THROTTLE_STREAK': 0, 'THROTTLE_LATCHED': 0,
                  'EVENT': '', 'TS': 1}
        dialer = MagicMock()
        dialer.obtener_estado_campana.return_value = {
            'contactos_llamados': 1,
            'canales_abiertos_pstn': 0,
            'efectuadas': 1,
            'terminadas': 0,
            'llamadas_conectadas': 0,
            'conectadas_no_atendidas': 0,
            'estimadas': 10,
            'reintentos_abiertos': 0,
            'status': [],
            'terminadas_ok': 0,
            'terminadas_no': 0,
            'estimadas_iniciales': 10,
        }
        dialer.obtener_pacing_campana.return_value = pacing
        mock_get_dialer.return_value = dialer

        url = reverse('campana_dialer_detalle_servicio')
        response = self.client.get(url, {'pk_campana': self.campana.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pacing'], pacing)
        self.assertTrue(response.context['show_pacing_section'])
        self.assertContains(response, 'id_PACING_MODE')
        self.assertContains(response, 'PREDICTIVE')
