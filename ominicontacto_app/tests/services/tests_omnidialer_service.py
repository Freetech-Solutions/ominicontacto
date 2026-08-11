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

from django.test import SimpleTestCase
from mock import MagicMock, patch

from ominicontacto_app.services.dialer.omnidialer import (
    CAMP_CALLDATA_KEY,
    CAMP_CHANNELS_KEY,
    CAMP_PACING_KEY,
    CONECTADAS_NO_ATENDIDAS_FIELDS,
    FINALIZED_NOCONTACT,
    FINALIZED_SUCCESS,
    OmnidialerService,
    PENDING_ATTEMPTS,
)


class OmnidialerServiceEstadoCampanaTests(SimpleTestCase):

    def _configure_redis(self, mock_redis_factory, dialer_hgetall=None, dialer_get=None,
                         calldata_hmget=None):
        redis_dialer = MagicMock()
        redis_dialer.hgetall.return_value = dialer_hgetall if dialer_hgetall is not None else {}
        redis_dialer.get.return_value = dialer_get

        redis_calldata = MagicMock()
        if calldata_hmget is None:
            calldata_hmget = [None] * len(CONECTADAS_NO_ATENDIDAS_FIELDS)
        redis_calldata.hmget.return_value = calldata_hmget

        def side_effect(db=0):
            if db == 2:
                return redis_calldata
            return redis_dialer

        mock_redis_factory.side_effect = side_effect
        return redis_dialer, redis_calldata

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_contactos_llamados_es_suma_de_finalizados_y_reintentos(self, mock_redis_factory):
        redis_dialer, _ = self._configure_redis(
            mock_redis_factory,
            dialer_hgetall={
                'ATTEMPTED_CALLS': '56',
                FINALIZED_SUCCESS: '14',
                FINALIZED_NOCONTACT: '42',
                'PENDING_INITIAL_CONTACT_ATTEMPTS': '0',
                PENDING_ATTEMPTS: '3',
                'NOANSWER': '39',
            },
            dialer_get='5',
        )

        campana = MagicMock()
        campana.id = 18

        data = OmnidialerService().obtener_estado_campana(campana)

        self.assertEqual(data['efectuadas'], 56)
        self.assertEqual(data['terminadas_ok'], 14)
        self.assertEqual(data['terminadas_no'], 42)
        self.assertEqual(data['reintentos_abiertos'], 3)
        self.assertEqual(
            data['contactos_llamados'],
            data['terminadas_ok'] + data['terminadas_no'] + data['reintentos_abiertos'],
        )
        self.assertEqual(data['contactos_llamados'], 59)
        self.assertEqual(data['canales_abiertos_pstn'], 5)
        self.assertEqual(data['llamadas_conectadas'], 0)
        self.assertEqual(data['conectadas_no_atendidas'], 0)
        self.assertEqual(
            data['status'],
            [
                {'gbState': 'NOANSWER', 'gbStateLabel': 'No atiende', 'nCalls': 39},
            ],
        )
        redis_dialer.get.assert_called_once_with(CAMP_CHANNELS_KEY.format(18))

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_canales_abiertos_pstn_cero_si_clave_ausente(self, mock_redis_factory):
        self._configure_redis(mock_redis_factory, dialer_hgetall={}, dialer_get=None)

        campana = MagicMock()
        campana.id = 7

        data = OmnidialerService().obtener_estado_campana(campana)

        self.assertEqual(data['canales_abiertos_pstn'], 0)
        self.assertEqual(data['contactos_llamados'], 0)
        self.assertEqual(data['llamadas_conectadas'], 0)
        self.assertEqual(data['conectadas_no_atendidas'], 0)

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_404_not_found_tiene_label_telefono_no_existe(self, mock_redis_factory):
        self._configure_redis(
            mock_redis_factory,
            dialer_hgetall={'404_NOT_FOUND': '2'},
            dialer_get=None,
        )

        campana = MagicMock()
        campana.id = 9

        data = OmnidialerService().obtener_estado_campana(campana)

        self.assertEqual(data['status'][0]['gbState'], '404_NOT_FOUND')
        self.assertEqual(data['status'][0]['gbStateLabel'], 'Teléfono no existe')
        self.assertEqual(data['status'][0]['nCalls'], 2)

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_480_tiene_label_temporalmente_no_disponible(self, mock_redis_factory):
        self._configure_redis(
            mock_redis_factory,
            dialer_hgetall={'480_TEMPORARILY_UNAVAILABLE': '7'},
            dialer_get=None,
        )

        campana = MagicMock()
        campana.id = 10

        data = OmnidialerService().obtener_estado_campana(campana)

        self.assertEqual(data['status'][0]['gbState'], '480_TEMPORARILY_UNAVAILABLE')
        self.assertEqual(data['status'][0]['gbStateLabel'], 'Temporalmente no disponible')
        self.assertEqual(data['status'][0]['nCalls'], 7)

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_exit_shortcall_tiene_label_shortcall(self, mock_redis_factory):
        self._configure_redis(
            mock_redis_factory,
            dialer_hgetall={'EXIT_SHORTCALL': '4'},
            dialer_get=None,
        )

        campana = MagicMock()
        campana.id = 11

        data = OmnidialerService().obtener_estado_campana(campana)

        self.assertEqual(data['status'][0]['gbState'], 'EXIT_SHORTCALL')
        self.assertEqual(data['status'][0]['gbStateLabel'], 'shortcall')
        self.assertEqual(data['status'][0]['nCalls'], 4)

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_exit_abandon_tiene_label_abandonadas(self, mock_redis_factory):
        self._configure_redis(
            mock_redis_factory,
            dialer_hgetall={'EXIT_ABANDON': '9'},
            dialer_get=None,
        )

        campana = MagicMock()
        campana.id = 12

        data = OmnidialerService().obtener_estado_campana(campana)

        self.assertEqual(data['status'][0]['gbState'], 'EXIT_ABANDON')
        self.assertEqual(data['status'][0]['gbStateLabel'], 'Abandonadas')
        self.assertEqual(data['status'][0]['nCalls'], 9)

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_exit_timeout_tiene_label_timeout_de_cola(self, mock_redis_factory):
        self._configure_redis(
            mock_redis_factory,
            dialer_hgetall={'EXIT_TIMEOUT': '2'},
            dialer_get=None,
        )

        campana = MagicMock()
        campana.id = 13

        data = OmnidialerService().obtener_estado_campana(campana)

        self.assertEqual(data['status'][0]['gbState'], 'EXIT_TIMEOUT')
        self.assertEqual(data['status'][0]['gbStateLabel'], 'Timeout de cola')
        self.assertEqual(data['status'][0]['nCalls'], 2)

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_answered_agent_oculto_y_conectadas_no_atendidas_desde_calldata(
            self, mock_redis_factory):
        redis_dialer, redis_calldata = self._configure_redis(
            mock_redis_factory,
            dialer_hgetall={
                'ANSWERED_AGENT': '23',
                'ANSWERED_PSTN': '20',
            },
            dialer_get='0',
            calldata_hmget=['3', '5', '1', '2'],
        )

        campana = MagicMock()
        campana.id = 42

        data = OmnidialerService().obtener_estado_campana(campana)

        status_by_key = {item['gbState']: item for item in data['status']}
        self.assertNotIn('ANSWERED_AGENT', status_by_key)
        self.assertNotIn('ANSWERED_PSTN', status_by_key)
        self.assertNotIn('CONECTADAS_NO_ATENDIDAS', status_by_key)
        self.assertEqual(data['llamadas_conectadas'], 20)
        self.assertEqual(data['conectadas_no_atendidas'], 11)
        redis_calldata.hmget.assert_called_once_with(
            CAMP_CALLDATA_KEY.format(42),
            *CONECTADAS_NO_ATENDIDAS_FIELDS,
        )
        redis_dialer.hgetall.assert_called_once()


class OmnidialerServicePacingCampanaTests(SimpleTestCase):

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_obtener_pacing_campana_tipado(self, mock_redis_factory):
        redis_dialer = MagicMock()
        redis_dialer.hgetall.return_value = {
            'MODE': 'PREDICTIVE',
            'REASON': 'ok',
            'GAMMA': '1.0',
            'C_DIAL': '4',
            'P_HIT': '0.5',
            'DROP_RATE': '0.01',
            'A_FREE': '2',
            'A_EXPECTED': '1.4',
            'C_RINGING': '3',
            'THROTTLE_STREAK': '5',
            'THROTTLE_LATCHED': '1',
            'EVENT': 'THROTTLE_ENGAGED',
            'TS': '1710000000',
        }
        mock_redis_factory.return_value = redis_dialer

        campana = MagicMock()
        campana.id = 18
        data = OmnidialerService().obtener_pacing_campana(campana)

        self.assertEqual(data['MODE'], 'PREDICTIVE')
        self.assertEqual(data['REASON'], 'ok')
        self.assertEqual(data['GAMMA'], 1.0)
        self.assertEqual(data['C_DIAL'], 4)
        self.assertEqual(data['P_HIT'], 0.5)
        self.assertEqual(data['DROP_RATE'], 0.01)
        self.assertEqual(data['A_FREE'], 2.0)
        self.assertEqual(data['A_EXPECTED'], 1.4)
        self.assertEqual(data['C_RINGING'], 3)
        self.assertEqual(data['THROTTLE_STREAK'], 5)
        self.assertEqual(data['THROTTLE_LATCHED'], 1)
        self.assertEqual(data['EVENT'], 'THROTTLE_ENGAGED')
        self.assertEqual(data['TS'], 1710000000)
        redis_dialer.hgetall.assert_called_once_with(CAMP_PACING_KEY.format(18))
        mock_redis_factory.assert_called_once_with(db=3)

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_obtener_pacing_campana_none_si_vacio(self, mock_redis_factory):
        redis_dialer = MagicMock()
        redis_dialer.hgetall.return_value = {}
        mock_redis_factory.return_value = redis_dialer

        campana = MagicMock()
        campana.id = 7
        self.assertIsNone(OmnidialerService().obtener_pacing_campana(campana))

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_obtener_pacing_campana_campos_vacios_como_none(self, mock_redis_factory):
        redis_dialer = MagicMock()
        redis_dialer.hgetall.return_value = {
            'MODE': 'PREDICTIVE_WARMUP',
            'REASON': 'warmup',
            'GAMMA': '0.0',
            'C_DIAL': '0',
            'P_HIT': '',
            'DROP_RATE': '',
            'A_FREE': '1',
            'A_EXPECTED': '0.0',
            'C_RINGING': '0',
            'THROTTLE_STREAK': '',
            'THROTTLE_LATCHED': '',
            'EVENT': '',
            'TS': '1710000001',
        }
        mock_redis_factory.return_value = redis_dialer

        campana = MagicMock()
        campana.id = 9
        data = OmnidialerService().obtener_pacing_campana(campana)
        self.assertEqual(data['MODE'], 'PREDICTIVE_WARMUP')
        self.assertIsNone(data['P_HIT'])
        self.assertIsNone(data['DROP_RATE'])
        self.assertEqual(data['C_DIAL'], 0)
        self.assertEqual(data['GAMMA'], 0.0)
        self.assertIsNone(data['THROTTLE_STREAK'])
        self.assertIsNone(data['THROTTLE_LATCHED'])
        self.assertEqual(data['EVENT'], '')
