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

from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase
from django.urls import reverse

from ominicontacto_app.models import User
from ominicontacto_app.tests.utiles import OMLBaseTest
from supervision_app.services.data_management import (
    DialerDataManager,
    InboundDataManager,
    get_event_subscription_key,
)
from supervision_app.services.events_management import SupervisionEventManager
from reportes_app.models import LlamadaLog
from supervision_app.views import (
    _dialer_campaign_aht,
    _dialer_campaign_p_hit,
    _get_campaign_call_metrics,
)


class DialerDataManagerGetInitialDataTests(TestCase):
    """Tests for DialerDataManager._get_initial_data with mixed Redis key formats."""

    @patch('supervision_app.services.data_management.wombat_habilitado')
    def test_get_initial_data_ignores_non_call_type_keys(self, mock_wombat):
        """Calldata hash can contain TOTAL_CALL_TIME, DIAL_IN, etc.; only CALL_TYPE:* keys are used."""
        mock_wombat.return_value = True
        redis_oml = MagicMock()
        redis_calldata = MagicMock()
        redis_calldata.hget.return_value = None

        manager = DialerDataManager(redis_oml, redis_calldata)
        campaign = MagicMock()
        campaign.id = 1
        campaign.estado = 1

        # Mix of CALL_TYPE:2:* keys and non-CALL_TYPE keys (as written by ACD logger)
        precomputations = {
            'calldata': {
                1: {
                    'TOTAL_CALL_TIME': '100.5',
                    'DIAL_IN': '0',
                    'CALL_TYPE:2:DIAL': '10',
                    'CALL_TYPE:2:EXIT_ANSWERED_HUMAN': '3',
                }
            },
            'channels': {1: '-'},
        }

        result = manager._get_initial_data(campaign, precomputations)

        self.assertNotIn('TOTAL_CALL_TIME', result)
        self.assertEqual(result['dialed'], '10')
        self.assertEqual(result['attended'], 3)
        self.assertEqual(result['shortcall'], 0)
        self.assertEqual(result['channels'], '-')


class DialerDataManagerUpdateOutboundFieldTests(TestCase):
    """DialerDataManager.update debe emitir outbound_field alineado al panel Outbound."""

    def setUp(self):
        with patch('supervision_app.services.data_management.wombat_habilitado', return_value=True):
            self.manager = DialerDataManager(MagicMock(), MagicMock())
        self.campaign_id = 99
        self.call_type = str(LlamadaLog.LLAMADA_DIALER)

    def _camp_event(self, event):
        return {
            'type': 'CAMP',
            'id': self.campaign_id,
            'call_type': self.call_type,
            'event': event,
        }

    @patch('supervision_app.services.data_management.wombat_habilitado', return_value=False)
    def test_dial_emite_discadas(self, _mock_wombat):
        result = self.manager.update(self._camp_event('DIAL'))
        self.assertEqual(result['field'], 'dialed')
        self.assertEqual(result['outbound_field'], 'discadas')
        self.assertEqual(result['campaign_id'], self.campaign_id)

    def test_answered_human_bot_mix(self):
        human = self.manager.update(self._camp_event('EXIT_ANSWERED_HUMAN'))
        self.assertEqual(human['field'], 'attended')
        self.assertEqual(human['outbound_field'], 'atendidas_human')

        bot = self.manager.update(self._camp_event('EXIT_ANSWERED_BOT'))
        self.assertEqual(bot['outbound_field'], 'atendidas_bot')

        mix = self.manager.update(self._camp_event('EXIT_ANSWERED_MIX'))
        self.assertEqual(mix['outbound_field'], 'atendidas_mix')

    def test_connect_sin_outbound_field(self):
        result = self.manager.update(self._camp_event('CONNECT'))
        self.assertEqual(result['field'], 'attended')
        self.assertNotIn('outbound_field', result)

    def test_busy_y_exit_busy(self):
        busy = self.manager.update(self._camp_event('BUSY'))
        self.assertEqual(busy['field'], 'not_attended')
        self.assertEqual(busy['outbound_field'], 'ocupado')

        exit_busy = self.manager.update(self._camp_event('EXIT_BUSY'))
        self.assertEqual(exit_busy['field'], 'not_attended')
        self.assertEqual(exit_busy['outbound_field'], 'ocupado')

    def test_exit_congestion_y_timeout(self):
        congestion = self.manager.update(self._camp_event('EXIT_CONGESTION'))
        self.assertEqual(congestion['outbound_field'], 'congestion')

        timeout = self.manager.update(self._camp_event('EXIT_TIMEOUT'))
        self.assertEqual(timeout['field'], 'connections_lost')
        self.assertEqual(timeout['outbound_field'], 'timeout')

    def test_extra_panel_events_en_call_events(self):
        self.assertIn('EXIT_BUSY', DialerDataManager.CALL_EVENTS)
        self.assertIn('EXIT_CONGESTION', DialerDataManager.CALL_EVENTS)


class SupervisionEventManagerExitAbandonTests(TestCase):
    """EXIT_ABANDON de CALLEVENTS debe enlazar con suscripciones EXIT_ABANDON:{campana_id}."""

    @patch('supervision_app.services.events_management.create_redis_connection')
    def test_get_event_code_exit_abandon_matches_inbound_subscribe(self, mock_create_redis):
        mock_create_redis.return_value = MagicMock()
        mgr = SupervisionEventManager(MagicMock())
        campaign_id = 42
        event = {'type': 'EXIT_ABANDON', 'id': campaign_id, 'time': 15}
        code = mgr._get_event_code(event)
        # Misma convención que InboundDataManager.subscribe: f'EXIT_ABANDON:{campaign.id}'
        self.assertEqual(code, f'EXIT_ABANDON:{campaign_id}')
        self.assertEqual(
            get_event_subscription_key(code),
            f'OML:SUPERVISION:EVENT_SUBSCRIPTIONS:EXIT_ABANDON:{campaign_id}',
        )

    @patch('supervision_app.services.events_management.create_redis_connection')
    def test_manage_event_exit_abandon_sends_abandons_to_ws_payload(self, mock_create_redis):
        import asyncio

        mock_create_redis.return_value = MagicMock()
        calldata_redis = MagicMock()
        calldata_redis.smembers.return_value = {'IN:99'}
        mgr = SupervisionEventManager(calldata_redis)
        mgr.notifier.send_message = AsyncMock()

        async def run():
            await mgr.manage_event({'type': 'EXIT_ABANDON', 'id': 1, 'time': 8})

        asyncio.run(run())
        mgr.notifier.send_message.assert_awaited_once()
        call_args = mgr.notifier.send_message.call_args[0]
        self.assertEqual(call_args[0], 'update')
        self.assertEqual(call_args[1]['IN']['field'], 'abandons')
        self.assertEqual(call_args[1]['IN']['time'], 8)
        self.assertEqual(call_args[2], '99')


class InboundDataManagerExitAbandonTests(TestCase):
    def test_update_exit_abandon_returns_abandons_field(self):
        redis_oml = MagicMock()
        redis_calldata = MagicMock()
        mgr = InboundDataManager(redis_oml, redis_calldata)
        out = mgr.update({'type': 'EXIT_ABANDON', 'id': 5, 'time': 20})
        self.assertEqual(
            out,
            {'campaign_id': 5, 'field': 'abandons', 'time': 20},
        )


class DashboardContactCenterStreamRegistrationTests(OMLBaseTest):
    """Panel-general debe registrar el stream de agentes y restringir campañas."""

    REQUEST_META = {
        'HTTP_HOST': 'testserver',
        'HTTP_X_FORWARDED_PORT': '443',
    }

    def setUp(self):
        super().setUp()
        self.admin = self.crear_administrador(username='cc_admin')
        self.supervisor = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.campana_asignada = self.crear_campana_entrante(user=self.supervisor.user)
        self.campana_asignada.supervisors.add(self.supervisor.user)
        self.otra_campana = self.crear_campana_entrante(user=self.admin)
        # admin es reported_by; el supervisor NO está asignado a otra_campana

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_general_registra_stream_supervisor(self, mock_gears_cls, mock_kamailio_cls):
        mock_gears = MagicMock()
        mock_gears_cls.return_value = mock_gears
        mock_kamailio = MagicMock()
        mock_kamailio.generar_sip_user.return_value = 'sipuser'
        mock_kamailio.generar_sip_password.return_value = 'sippass'
        mock_kamailio_cls.return_value = mock_kamailio

        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse('supervision_contact_center')
        response = self.client.get(url, **self.REQUEST_META)

        self.assertEqual(response.status_code, 200)
        mock_gears.registra_stream_supervisor.assert_called_once_with(self.supervisor.id)
        self.assertEqual(response.context['supervisor_id'], self.supervisor.id)
        self.assertContains(response, 'CONTACT_CENTER_AGENTES_STREAM_URL')
        self.assertContains(response, 'CONTACT_CENTER_CAMPAIGN_TYPES')
        self.assertContains(response, 'CONTACT_CENTER_TYPE_DIALER')
        self.assertContains(
            response,
            f'/consumers/stream/supervisor/{self.supervisor.id}/agentes',
        )

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_general_supervisor_solo_ve_campanas_asignadas(
            self, mock_gears_cls, mock_kamailio_cls):
        mock_gears_cls.return_value = MagicMock()
        mock_kamailio = MagicMock()
        mock_kamailio.generar_sip_user.return_value = 'sipuser'
        mock_kamailio.generar_sip_password.return_value = 'sippass'
        mock_kamailio_cls.return_value = mock_kamailio

        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        response = self.client.get(reverse('supervision_contact_center'), **self.REQUEST_META)

        self.assertEqual(response.status_code, 200)
        campana_ids = set(response.context['campanas'].values_list('id', flat=True))
        self.assertIn(self.campana_asignada.id, campana_ids)
        self.assertNotIn(self.otra_campana.id, campana_ids)
        self.assertContains(response, 'Desglose de disposiciones')

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_general_admin_ve_todas_las_campanas(self, mock_gears_cls, mock_kamailio_cls):
        mock_gears = MagicMock()
        mock_gears_cls.return_value = mock_gears
        mock_kamailio = MagicMock()
        mock_kamailio.generar_sip_user.return_value = 'sipuser'
        mock_kamailio.generar_sip_password.return_value = 'sippass'
        mock_kamailio_cls.return_value = mock_kamailio

        self.client.login(username=self.admin.username, password=self.DEFAULT_PASSWORD)
        response = self.client.get(reverse('supervision_contact_center'), **self.REQUEST_META)

        self.assertEqual(response.status_code, 200)
        campana_ids = set(response.context['campanas'].values_list('id', flat=True))
        self.assertIn(self.campana_asignada.id, campana_ids)
        self.assertIn(self.otra_campana.id, campana_ids)
        admin_sup = self.admin.get_supervisor_profile()
        mock_gears.registra_stream_supervisor.assert_called_once_with(admin_sup.id)

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_general_campaign_404_si_no_asignada(self, mock_gears_cls, mock_kamailio_cls):
        mock_gears_cls.return_value = MagicMock()
        mock_kamailio_cls.return_value = MagicMock()

        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse('supervision_contact_center_campaign', args=[self.otra_campana.id])
        response = self.client.get(url, **self.REQUEST_META)
        self.assertEqual(response.status_code, 404)

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_general_campaign_ok_si_asignada(self, mock_gears_cls, mock_kamailio_cls):
        mock_gears = MagicMock()
        mock_gears_cls.return_value = mock_gears
        mock_kamailio = MagicMock()
        mock_kamailio.generar_sip_user.return_value = 'sipuser'
        mock_kamailio.generar_sip_password.return_value = 'sippass'
        mock_kamailio_cls.return_value = mock_kamailio

        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse(
            'supervision_contact_center_campaign',
            args=[self.campana_asignada.id],
        )
        response = self.client.get(url, **self.REQUEST_META)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['initial_campaign_id'], self.campana_asignada.id)
        mock_gears.registra_stream_supervisor.assert_called_once_with(self.supervisor.id)

    def test_campanas_queryset_sin_supervisor_devuelve_vacio(self):
        from supervision_app.views import _campanas_panel_general_queryset

        user = MagicMock()
        user.get_is_administrador.return_value = False
        user.get_supervisor_profile.return_value = None
        qs = _campanas_panel_general_queryset(user)
        self.assertEqual(list(qs), [])

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_enrich_context_sin_supervisor_no_registra_stream(
            self, mock_gears_cls, mock_kamailio_cls):
        from supervision_app.views import _enrich_contact_center_supervisor_context

        mock_gears = MagicMock()
        mock_gears_cls.return_value = mock_gears
        user = MagicMock()
        user.get_supervisor_profile.return_value = None
        context = _enrich_contact_center_supervisor_context({}, user)
        self.assertIsNone(context['supervisor_id'])
        mock_gears.registra_stream_supervisor.assert_not_called()


class DashboardPanelDialerViewTests(OMLBaseTest):
    """Panel Dialer: solo campañas TYPE_DIALER y sin cards Inbound/Outbound."""

    REQUEST_META = {
        'HTTP_HOST': 'testserver',
        'HTTP_X_FORWARDED_PORT': '443',
    }

    def setUp(self):
        super().setUp()
        self.admin = self.crear_administrador(username='pd_admin')
        self.supervisor = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.campana_dialer = self.crear_campana_dialer(user=self.supervisor.user)
        self.campana_dialer.supervisors.add(self.supervisor.user)
        self.campana_entrante = self.crear_campana_entrante(user=self.supervisor.user)
        self.campana_entrante.supervisors.add(self.supervisor.user)
        self.otra_dialer = self.crear_campana_dialer(user=self.admin)

    def _mock_services(self, mock_gears_cls, mock_kamailio_cls):
        mock_gears_cls.return_value = MagicMock()
        mock_kamailio = MagicMock()
        mock_kamailio.generar_sip_user.return_value = 'sipuser'
        mock_kamailio.generar_sip_password.return_value = 'sippass'
        mock_kamailio_cls.return_value = mock_kamailio

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_dialer_200_sin_inbound_outbound(self, mock_gears_cls, mock_kamailio_cls):
        self._mock_services(mock_gears_cls, mock_kamailio_cls)
        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        response = self.client.get(reverse('supervision_panel_dialer'), **self.REQUEST_META)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Panel Dialer')
        self.assertContains(response, 'PANEL_DIALER_AGENTES_STREAM_URL')
        self.assertContains(response, 'PANEL_DIALER_ESTADO_URL')
        self.assertContains(response, 'panel_dialer.js')
        self.assertContains(response, 'Estado Discador')
        self.assertContains(response, 'Conectadas no atendidas')
        self.assertContains(response, 'Pacing predictivo')
        self.assertContains(response, 'Desglose de disposiciones')
        self.assertContains(response, 'T. Promedio (AHT)')
        self.assertContains(response, 'P_HIT (contactación)')
        self.assertContains(response, 'Llamadas efectuadas')
        self.assertContains(response, 'panel-dialer-estado')
        self.assertNotContains(response, 'Conectadas al agente')
        self.assertNotContains(response, 'Contactos llamados')
        self.assertNotContains(response, 'Llamadas Outbound')
        self.assertNotContains(response, 'Llamadas Inbound')
        self.assertNotContains(response, 'inboundChart')

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_dialer_solo_campanas_dialer(self, mock_gears_cls, mock_kamailio_cls):
        self._mock_services(mock_gears_cls, mock_kamailio_cls)
        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        response = self.client.get(reverse('supervision_panel_dialer'), **self.REQUEST_META)

        campana_ids = set(response.context['campanas'].values_list('id', flat=True))
        self.assertIn(self.campana_dialer.id, campana_ids)
        self.assertNotIn(self.campana_entrante.id, campana_ids)
        self.assertNotIn(self.otra_dialer.id, campana_ids)
        for campana in response.context['campanas']:
            self.assertEqual(campana.type, campana.TYPE_DIALER)

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_dialer_campaign_ok_si_dialer_asignada(self, mock_gears_cls, mock_kamailio_cls):
        self._mock_services(mock_gears_cls, mock_kamailio_cls)
        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse('supervision_panel_dialer_campaign', args=[self.campana_dialer.id])
        response = self.client.get(url, **self.REQUEST_META)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['initial_campaign_id'], self.campana_dialer.id)

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_dialer_campaign_404_si_entrante(self, mock_gears_cls, mock_kamailio_cls):
        self._mock_services(mock_gears_cls, mock_kamailio_cls)
        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse('supervision_panel_dialer_campaign', args=[self.campana_entrante.id])
        response = self.client.get(url, **self.REQUEST_META)
        self.assertEqual(response.status_code, 404)

    @patch('supervision_app.views.KamailioService')
    @patch('supervision_app.views.RedisGearsService')
    def test_panel_dialer_campaign_404_si_no_asignada(self, mock_gears_cls, mock_kamailio_cls):
        self._mock_services(mock_gears_cls, mock_kamailio_cls)
        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse('supervision_panel_dialer_campaign', args=[self.otra_dialer.id])
        response = self.client.get(url, **self.REQUEST_META)
        self.assertEqual(response.status_code, 404)

    @patch('supervision_app.views._panel_dialer_estado_payload')
    def test_panel_dialer_estado_200_payload_paridad(self, mock_payload):
        mock_payload.return_value = {
            'estado_discador': {
                'pending_initial': 1,
                'pending_retries': 2,
                'finalized_no_contact': 3,
                'contacted_successfully': 4,
                'attempted_calls': 10,
                'answered_pstn': 5,
                'answered_agent': 4,
                'conectadas_no_atendidas': 1,
                'estimadas': 3,
                'contactos_llamados': 7,
                'campana_nombre': self.campana_dialer.nombre,
                'campana_estado': 'Activa',
                'status': [{'gbState': 'BUSY', 'gbStateLabel': 'Teléfono ocupado', 'nCalls': 2}],
                'p_hit': 0.42,
                'p_hit_label': 'P_HIT (contactación)',
            },
            'llamadas_discando': 3,
            'pacing': {'MODE': 'NORMAL', 'P_HIT': 0.5},
            'show_pacing_section': True,
        }
        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse('supervision_panel_dialer_estado')
        response = self.client.get(
            url, {'campaign_id': self.campana_dialer.id}, **self.REQUEST_META)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('conectadas_no_atendidas', data['estado_discador'])
        self.assertEqual(data['estado_discador']['conectadas_no_atendidas'], 1)
        self.assertIn('status', data['estado_discador'])
        self.assertEqual(data['show_pacing_section'], True)
        self.assertEqual(data['llamadas_discando'], 3)
        self.assertEqual(data['estado_discador']['p_hit'], 0.42)
        self.assertEqual(data['estado_discador']['p_hit_label'], 'P_HIT (contactación)')
        mock_payload.assert_called_once()

    def test_panel_dialer_estado_404_si_entrante(self):
        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse('supervision_panel_dialer_estado')
        response = self.client.get(
            url, {'campaign_id': self.campana_entrante.id}, **self.REQUEST_META)
        self.assertEqual(response.status_code, 404)

    def test_panel_dialer_estado_404_si_no_asignada(self):
        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse('supervision_panel_dialer_estado')
        response = self.client.get(
            url, {'campaign_id': self.otra_dialer.id}, **self.REQUEST_META)
        self.assertEqual(response.status_code, 404)

    def test_panel_dialer_estado_400_sin_campaign_id(self):
        self.client.login(username=self.supervisor.user.username, password=self.DEFAULT_PASSWORD)
        url = reverse('supervision_panel_dialer_estado')
        response = self.client.get(url, **self.REQUEST_META)
        self.assertEqual(response.status_code, 400)


class DialerCampaignAhtTests(TestCase):
    """AHT del Panel Dialer desde Redis DB3 (pacing), no EXIT_ANSWERED genérico."""

    def test_lee_hash_aht(self):
        redis_dialer = MagicMock()
        redis_dialer.hget.return_value = '95.5'
        self.assertEqual(_dialer_campaign_aht(redis_dialer, 7), 95.5)
        redis_dialer.hget.assert_called_once_with('CAMP:7:AHT', 'AHT')

    def test_fallback_att_mas_acw(self):
        redis_dialer = MagicMock()

        def _hget(key, field):
            return {'ATT': '40', 'ACW': '15'}.get(field)

        redis_dialer.hget.side_effect = _hget
        self.assertEqual(_dialer_campaign_aht(redis_dialer, 7), 55.0)

    def test_call_metrics_prefiere_aht_dialer(self):
        redis_calldata = MagicMock()
        redis_calldata.hgetall.return_value = {
            'TOTAL_CALL_TIME': '300',
            'CALL_TYPE:2:EXIT_ANSWERED_HUMAN': '3',
        }
        redis_calldata.hget.return_value = None
        redis_calldata.get.return_value = None
        redis_dialer = MagicMock()
        redis_dialer.get.return_value = '0'
        redis_dialer.hget.return_value = '80'

        metrics = _get_campaign_call_metrics(
            redis_calldata, 12, redis_dialer_connection=redis_dialer)
        self.assertEqual(metrics['call_times']['aht'], 80.0)

    def test_call_metrics_sin_dialer_usa_human_bot_no_exit_generico(self):
        redis_calldata = MagicMock()
        redis_calldata.hgetall.return_value = {
            'TOTAL_CALL_TIME': '300',
            'CALL_TYPE:2:EXIT_ANSWERED_HUMAN': '3',
        }
        redis_calldata.hget.return_value = None
        redis_calldata.get.return_value = None

        metrics = _get_campaign_call_metrics(redis_calldata, 12)
        self.assertEqual(metrics['call_times']['aht'], 100.0)


class DialerCampaignPHitTests(TestCase):
    """P_HIT persistente en CAMP:{id}:METRICS (no depende del snapshot PACING)."""

    def test_lee_p_hit_ewma(self):
        redis_dialer = MagicMock()
        redis_dialer.hget.return_value = '0.37'
        self.assertEqual(_dialer_campaign_p_hit(redis_dialer, 7, predictive=True), 0.37)
        redis_dialer.hget.assert_called_once_with('CAMP:7:METRICS', 'P_HIT')

    def test_fallback_p_hit_ratio_si_predictivo_sin_ewma(self):
        redis_dialer = MagicMock()
        redis_dialer.hget.side_effect = [None, '0.25']
        self.assertEqual(_dialer_campaign_p_hit(redis_dialer, 7, predictive=True), 0.25)

    def test_progresiva_usa_p_hit_ratio(self):
        redis_dialer = MagicMock()
        redis_dialer.hget.return_value = '0.31'
        self.assertEqual(_dialer_campaign_p_hit(redis_dialer, 7, predictive=False), 0.31)
        redis_dialer.hget.assert_called_once_with('CAMP:7:METRICS', 'P_HIT_RATIO')

    def test_none_si_sin_muestra(self):
        redis_dialer = MagicMock()
        redis_dialer.hget.return_value = None
        self.assertIsNone(_dialer_campaign_p_hit(redis_dialer, 7, predictive=True))
