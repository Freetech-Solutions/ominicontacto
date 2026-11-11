# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import time
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ominicontacto_app.services.dialer.omnidialer import OmnidialerService
from supervision_app.views import (
    PACING_STALL_AGE_SEC,
    _panel_dialer_dial_ratio_efectivo,
    _panel_dialer_estado_payload,
    _panel_dialer_pacing_health,
)


class FakeDialerRedis(object):
    """Redis DB3 mínimo: hgetall / hget / get / ping."""

    def __init__(self, hashes=None, strings=None):
        self.hashes = hashes or {}
        self.strings = strings or {}

    def ping(self):
        return True

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def get(self, key):
        return self.strings.get(key)

    def hmget(self, key, *fields):
        data = self.hashes.get(key, {})
        return [data.get(field) for field in fields]


class ObtenerPacingCampanaTests(SimpleTestCase):

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_devuelve_campos_nuevos_del_snapshot(self, mock_create_redis):
        now_ts = int(time.time())
        mock_create_redis.return_value = FakeDialerRedis(hashes={
            'CAMP:42:PACING': {
                'MODE': 'PREDICTIVE',
                'REASON': 'ok',
                'GAMMA': '1.2',
                'C_DIAL': '4',
                'P_HIT': '0.35',
                'DROP_RATE': '0.02',
                'DROP_RATE_CUM': '0.03',
                'HIT_COUNT': '50',
                'D_THROTTLE': '0.04',
                'A_FREE': '2',
                'A_EXPECTED': '0.5',
                'C_RINGING': '3',
                'C_WAITING': '1',
                'MAX_DIAL_RATIO': '5',
                'THROTTLE_STREAK': '0',
                'THROTTLE_OVER_SEC': '0',
                'THROTTLE_LATCHED': '0',
                'EVENT': '',
                'TS': str(now_ts),
            },
        })
        campana = MagicMock()
        campana.id = 42

        pacing = OmnidialerService().obtener_pacing_campana(campana)

        self.assertIsNotNone(pacing)
        self.assertEqual(pacing['C_WAITING'], 1)
        self.assertEqual(pacing['HIT_COUNT'], 50)
        self.assertEqual(pacing['MAX_DIAL_RATIO'], 5)
        self.assertEqual(pacing['THROTTLE_OVER_SEC'], 0)
        self.assertAlmostEqual(pacing['DROP_RATE_CUM'], 0.03)
        self.assertAlmostEqual(pacing['D_THROTTLE'], 0.04)
        self.assertIsNone(pacing['MAX_ABANDON_RATE'])

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_hash_vacio_retorna_none(self, mock_create_redis):
        mock_create_redis.return_value = FakeDialerRedis()
        campana = MagicMock()
        campana.id = 7
        self.assertIsNone(OmnidialerService().obtener_pacing_campana(campana))

    @patch('ominicontacto_app.services.dialer.omnidialer.create_redis_connection')
    def test_campo_ilegible_queda_none(self, mock_create_redis):
        mock_create_redis.return_value = FakeDialerRedis(hashes={
            'CAMP:7:PACING': {
                'MODE': 'PREDICTIVE',
                'C_WAITING': 'nope',
                'DROP_RATE_CUM': '',
                'TS': '100',
            },
        })
        campana = MagicMock()
        campana.id = 7
        pacing = OmnidialerService().obtener_pacing_campana(campana)
        self.assertIsNone(pacing['C_WAITING'])
        self.assertIsNone(pacing['DROP_RATE_CUM'])


class PanelDialerPacingHealthTests(SimpleTestCase):

    def test_sin_pacing_es_stall(self):
        age, up = _panel_dialer_pacing_health(None)
        self.assertIsNone(age)
        self.assertEqual(up, 0)

    def test_ts_reciente_esta_up(self):
        now = 1_700_000_000
        age, up = _panel_dialer_pacing_health({'TS': now - 3}, now_ts=now)
        self.assertEqual(age, 3)
        self.assertEqual(up, 1)

    def test_ts_viejo_es_stall(self):
        now = 1_700_000_000
        age, up = _panel_dialer_pacing_health(
            {'TS': now - (PACING_STALL_AGE_SEC + 5)}, now_ts=now)
        self.assertEqual(age, PACING_STALL_AGE_SEC + 5)
        self.assertEqual(up, 0)


class PanelDialerDialRatioTests(SimpleTestCase):

    def test_ratio_con_agentes_libres(self):
        self.assertAlmostEqual(
            _panel_dialer_dial_ratio_efectivo({'C_DIAL': 4, 'A_FREE': 2}), 2.0)

    def test_ratio_sin_agentes_libres_es_none(self):
        self.assertIsNone(
            _panel_dialer_dial_ratio_efectivo({'C_DIAL': 4, 'A_FREE': 0}))


class PanelDialerEstadoPayloadPacingTests(SimpleTestCase):

    def _campana(self, campana_id=19):
        campana = MagicMock()
        campana.id = campana_id
        campana.nombre = 'Predictiva soak'
        campana.get_estado_display.return_value = 'Activa'
        return campana

    def _dialer_service(self, canales=7):
        service = MagicMock()
        service.obtener_estado_campana.return_value = {
            'canales_abiertos_pstn': canales,
            'efectuadas': 100,
            'terminadas_ok': 40,
            'terminadas_no': 20,
            'estimadas': 10,
            'estimadas_iniciales': 8,
            'reintentos_abiertos': 2,
            'llamadas_conectadas': 50,
            'conectadas_no_atendidas': 3,
            'contactos_llamados': 62,
            'status': [{'gbState': 'BUSY', 'gbStateLabel': 'Ocupado', 'nCalls': 5}],
        }
        return service

    @patch('supervision_app.views._campana_es_predictiva', return_value=True)
    @patch('supervision_app.views._obtener_pacing_contexto')
    @patch('supervision_app.views.create_redis_connection')
    @patch('supervision_app.views.get_dialer_service')
    def test_payload_pacing_vivo_channels_metrics(
            self, mock_get_dialer, mock_create_redis, mock_pacing_ctx, _pred):
        now_ts = int(time.time())
        pacing = {
            'MODE': 'PREDICTIVE',
            'REASON': 'ok',
            'GAMMA': 1.1,
            'C_DIAL': 4,
            'P_HIT': 0.4,
            'DROP_RATE': 0.02,
            'DROP_RATE_CUM': 0.025,
            'HIT_COUNT': 40,
            'D_THROTTLE': 0.03,
            'A_FREE': 2.0,
            'A_EXPECTED': 0.8,
            'C_RINGING': 3,
            'C_WAITING': 1,
            'MAX_DIAL_RATIO': 5,
            'MAX_ABANDON_RATE': None,
            'THROTTLE_STREAK': 0,
            'THROTTLE_OVER_SEC': 2,
            'THROTTLE_LATCHED': 0,
            'EVENT': '',
            'TS': now_ts,
        }
        mock_pacing_ctx.return_value = {
            'pacing': pacing,
            'show_pacing_section': True,
        }
        mock_get_dialer.return_value = self._dialer_service(canales=7)
        mock_create_redis.return_value = FakeDialerRedis(
            hashes={
                'CAMP:19:COUNTER': {
                    'ANSWERED_AGENT': '12',
                    'AMD': '4',
                    'ATTEMPTED_CALLS': '100',
                    'ANSWERED_PSTN': '50',
                },
                'CAMP:19:CHANNELS': {
                    'RINGING': '3',
                    'WAITING_AGENT': '2',
                    'ONCALL': '2',
                },
                'CAMP:19:METRICS': {
                    'HIT_COUNT': '55',
                    'ABANDON_COUNT': '3',
                    'FAIL_COUNT': '40',
                    'TECH_FAIL_COUNT': '1',
                    'DROP_RATE_EWMA': '0.021',
                    'P_HIT_RATIO': '0.55',
                    'AMD_TIME': '2.5',
                    'P_HIT': '0.4',
                },
            },
            strings={'OML:CALLS:19:DIALER': '7'},
        )

        payload = _panel_dialer_estado_payload(self._campana(19))

        self.assertEqual(payload['pacing_up'], 1)
        self.assertIsNotNone(payload['pacing_age_seconds'])
        self.assertLessEqual(payload['pacing_age_seconds'], PACING_STALL_AGE_SEC)
        self.assertEqual(payload['channels']['waiting_agent'], 2)
        self.assertEqual(payload['channels']['oncall'], 2)
        self.assertEqual(payload['channels']['ringing'], 3)
        self.assertEqual(payload['channels']['calls'], 7)
        self.assertEqual(payload['metrics']['hit_count'], 55)
        self.assertEqual(payload['metrics']['abandon_count'], 3)
        self.assertAlmostEqual(payload['metrics']['drop_rate_ewma'], 0.021)
        self.assertAlmostEqual(payload['metrics']['p_hit_ratio'], 0.55)
        self.assertAlmostEqual(payload['metrics']['amd_time'], 2.5)
        self.assertEqual(payload['estado_discador']['answered_agent'], 12)
        self.assertEqual(payload['estado_discador']['amd'], 4)
        self.assertAlmostEqual(payload['estado_discador']['p_hit_ratio'], 0.55)
        self.assertAlmostEqual(payload['dial_ratio_efectivo'], 2.0)
        self.assertEqual(payload['pacing']['THROTTLE_OVER_SEC'], 2)

    @patch('supervision_app.views._campana_es_predictiva', return_value=True)
    @patch('supervision_app.views._obtener_pacing_contexto')
    @patch('supervision_app.views.create_redis_connection')
    @patch('supervision_app.views.get_dialer_service')
    def test_payload_sin_pacing_muestra_stall(
            self, mock_get_dialer, mock_create_redis, mock_pacing_ctx, _pred):
        mock_pacing_ctx.return_value = {
            'pacing': None,
            'show_pacing_section': True,
        }
        mock_get_dialer.return_value = self._dialer_service()
        mock_create_redis.return_value = FakeDialerRedis(hashes={
            'CAMP:19:COUNTER': {
                'ANSWERED_AGENT': '8',
                'AMD': '1',
            },
        })

        payload = _panel_dialer_estado_payload(self._campana(19))

        self.assertIsNone(payload['pacing'])
        self.assertEqual(payload['pacing_up'], 0)
        self.assertIsNone(payload['pacing_age_seconds'])
        self.assertTrue(payload['show_pacing_section'])
        self.assertEqual(payload['estado_discador']['answered_agent'], 8)
        self.assertEqual(payload['estado_discador']['amd'], 1)
        self.assertIsNone(payload['dial_ratio_efectivo'])

    @patch('supervision_app.views._campana_es_predictiva', return_value=True)
    @patch('supervision_app.views._obtener_pacing_contexto')
    @patch('supervision_app.views.create_redis_connection')
    @patch('supervision_app.views.get_dialer_service')
    def test_payload_pacing_ts_viejo_stall_con_snapshot(
            self, mock_get_dialer, mock_create_redis, mock_pacing_ctx, _pred):
        stale_ts = int(time.time()) - (PACING_STALL_AGE_SEC + 20)
        mock_pacing_ctx.return_value = {
            'pacing': {
                'MODE': 'PREDICTIVE',
                'C_DIAL': 1,
                'A_FREE': 1.0,
                'TS': stale_ts,
            },
            'show_pacing_section': True,
        }
        mock_get_dialer.return_value = self._dialer_service()
        mock_create_redis.return_value = FakeDialerRedis()

        payload = _panel_dialer_estado_payload(self._campana(19))

        self.assertIsNotNone(payload['pacing'])
        self.assertEqual(payload['pacing_up'], 0)
        self.assertGreater(payload['pacing_age_seconds'], PACING_STALL_AGE_SEC)

    @patch('supervision_app.views._campana_es_predictiva', return_value=True)
    @patch('supervision_app.views._obtener_pacing_contexto')
    @patch('supervision_app.views.create_redis_connection')
    @patch('supervision_app.views.get_dialer_service')
    def test_waiting_fallback_desde_pacing_si_channels_sin_clave(
            self, mock_get_dialer, mock_create_redis, mock_pacing_ctx, _pred):
        mock_pacing_ctx.return_value = {
            'pacing': {
                'MODE': 'PREDICTIVE',
                'C_WAITING': 9,
                'C_DIAL': 2,
                'A_FREE': 1.0,
                'TS': int(time.time()),
            },
            'show_pacing_section': True,
        }
        mock_get_dialer.return_value = self._dialer_service()
        mock_create_redis.return_value = FakeDialerRedis(hashes={
            'CAMP:19:CHANNELS': {
                'RINGING': '1',
                'ONCALL': '0',
            },
        })

        payload = _panel_dialer_estado_payload(self._campana(19))
        self.assertEqual(payload['channels']['waiting_agent'], 9)
        self.assertEqual(payload['channels']['ringing'], 1)
        self.assertIsNone(payload['metrics']['abandon_count'])
