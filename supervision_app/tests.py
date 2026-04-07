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

from supervision_app.services.data_management import (
    DialerDataManager,
    InboundDataManager,
    get_event_subscription_key,
)
from supervision_app.services.events_management import SupervisionEventManager


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
