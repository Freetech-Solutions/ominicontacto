# -*- coding: utf-8 -*-
# Copyright (C) 2026 Freetech Solutions

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

import json
import time

from django.test import SimpleTestCase, TestCase
from mock import MagicMock, patch

from ominicontacto_app.models import Campana
from ominicontacto_app.services.asterisk.agent_activity import AgentActivityAmiManager
from ominicontacto_app.services.dialer import acw_metrics
from ominicontacto_app.tests.factories import CampanaFactory


class AgentActivityAcwEmitTests(SimpleTestCase):
    """Emisión de EXIT_ACW al salir de PAUSE-ACW (mock Redis + submit)."""

    def _manager_with_redis(self, hmget_map):
        manager = AgentActivityAmiManager()
        redis_conn = MagicMock()

        def hmget(_family, *fields):
            return [hmget_map.get(f) for f in fields]

        redis_conn.hmget.side_effect = hmget
        redis_conn.hset.return_value = True
        manager.get_redis_connection = MagicMock(return_value=redis_conn)
        manager._get_family = MagicMock(return_value='OML:AGENT:1')
        return manager, redis_conn

    @patch('ominicontacto_app.services.asterisk.agent_activity.acw_metrics.submit_exit_acw')
    def test_unpause_from_acw_with_campaign_emits_sample(self, mock_submit):
        now = int(time.time())
        manager, redis_conn = self._manager_with_redis({
            'STATUS': 'PAUSE-ACW',
            'PAUSE_ID': '0',
            'TIMESTAMP': str(now - 12),
            'CAMPAIGN': '18',
        })
        agente = MagicMock()
        agente.id = 7
        agente.user.id = 70

        mock_submit.return_value = True
        queue_err, redis_err = manager.unpause_agent(agente, '0')

        self.assertFalse(queue_err)
        self.assertFalse(redis_err)
        mock_submit.assert_called_once()
        args, kwargs = mock_submit.call_args
        self.assertEqual(str(args[0]), '18')
        self.assertGreaterEqual(args[1], 11.0)
        self.assertLessEqual(args[1], 15.0)
        self.assertEqual(kwargs.get('agent_id'), 7)
        # READY se aplica después del sample
        self.assertTrue(redis_conn.hset.called)

    @patch('ominicontacto_app.services.asterisk.agent_activity.acw_metrics.submit_exit_acw')
    def test_unpause_without_campaign_skips_sample(self, mock_submit):
        now = int(time.time())
        manager, _ = self._manager_with_redis({
            'STATUS': 'PAUSE-ACW',
            'PAUSE_ID': '0',
            'TIMESTAMP': str(now - 5),
            'CAMPAIGN': '',
        })
        agente = MagicMock()
        agente.id = 1
        agente.user.id = 1

        manager.unpause_agent(agente, '0')
        mock_submit.assert_not_called()

    @patch('ominicontacto_app.services.asterisk.agent_activity.acw_metrics.submit_exit_acw')
    def test_unpause_not_in_acw_skips_sample(self, mock_submit):
        now = int(time.time())
        manager, _ = self._manager_with_redis({
            'STATUS': 'PAUSE-Break',
            'PAUSE_ID': '3',
            'TIMESTAMP': str(now - 5),
            'CAMPAIGN': '18',
        })
        agente = MagicMock()
        agente.id = 1
        agente.user.id = 1

        # unpause con pause_id de pausa normal intenta resolver Pausa en DB;
        # mockeamos para no tocar ORM.
        with patch(
            'ominicontacto_app.services.asterisk.agent_activity.Pausa.objects'
        ) as pausa_objects:
            pause = MagicMock()
            pause.id = 3
            pausa_objects.activa_by_pauseid.return_value = pause
            manager.unpause_agent(agente, '3')
        mock_submit.assert_not_called()

    @patch('ominicontacto_app.services.asterisk.agent_activity.acw_metrics.submit_exit_acw')
    def test_switch_from_acw_to_other_pause_emits_once(self, mock_submit):
        now = int(time.time())
        manager, _ = self._manager_with_redis({
            'STATUS': 'PAUSE-ACW',
            'PAUSE_ID': '0',
            'TIMESTAMP': str(now - 8),
            'CAMPAIGN': '22',
        })
        agente = MagicMock()
        agente.id = 9
        agente.user.id = 9
        mock_submit.return_value = True

        with patch(
            'ominicontacto_app.services.asterisk.agent_activity.Pausa.objects'
        ) as pausa_objects:
            pause = MagicMock()
            pause.nombre = 'Break'
            pausa_objects.activa_by_pauseid.return_value = pause
            manager.pause_agent(agente, '5')

        mock_submit.assert_called_once()
        self.assertEqual(str(mock_submit.call_args[0][0]), '22')

    @patch('ominicontacto_app.services.asterisk.agent_activity.acw_metrics.submit_exit_acw')
    def test_gearman_failure_does_not_block_unpause(self, mock_submit):
        now = int(time.time())
        manager, redis_conn = self._manager_with_redis({
            'STATUS': 'PAUSE-ACW',
            'PAUSE_ID': '0',
            'TIMESTAMP': str(now - 3),
            'CAMPAIGN': '18',
        })
        agente = MagicMock()
        agente.id = 1
        agente.user.id = 1
        mock_submit.side_effect = RuntimeError('gearman down')

        queue_err, redis_err = manager.unpause_agent(agente, '0')
        self.assertFalse(queue_err)
        self.assertFalse(redis_err)
        self.assertTrue(redis_conn.hset.called)


class AcwMetricsSubmitTests(TestCase):
    """submit_exit_acw: solo campañas dialer; Gearman best-effort."""

    def setUp(self):
        self.campana_dialer = CampanaFactory(type=Campana.TYPE_DIALER, estado=Campana.ESTADO_ACTIVA)
        self.campana_manual = CampanaFactory(type=Campana.TYPE_MANUAL, estado=Campana.ESTADO_ACTIVA)

    @patch('ominicontacto_app.services.dialer.acw_metrics._gearman_client')
    def test_submit_exit_acw_for_dialer_campaign(self, mock_client_factory):
        client = MagicMock()
        mock_client_factory.return_value = client

        ok = acw_metrics.submit_exit_acw(self.campana_dialer.id, 12.5, agent_id=3)
        self.assertTrue(ok)
        self.assertEqual(client.submit_job.call_count, 1)
        job_name = client.submit_job.call_args[0][0]
        payload = json.loads(client.submit_job.call_args[0][1].decode('utf-8'))
        self.assertEqual(job_name, 'process-event')
        self.assertEqual(payload['dialstatus'], 'EXIT_ACW')
        self.assertEqual(payload['id_campaign'], str(self.campana_dialer.id))
        self.assertEqual(payload['acw_duration'], 12.5)
        self.assertEqual(payload['contact_id'], '0')

    @patch('ominicontacto_app.services.dialer.acw_metrics._gearman_client')
    def test_submit_exit_acw_skips_non_dialer(self, mock_client_factory):
        client = MagicMock()
        mock_client_factory.return_value = client
        ok = acw_metrics.submit_exit_acw(self.campana_manual.id, 5.0, agent_id=1)
        self.assertFalse(ok)
        client.submit_job.assert_not_called()

    @patch('ominicontacto_app.services.dialer.acw_metrics._gearman_client')
    def test_submit_exit_acw_gearman_error_returns_false(self, mock_client_factory):
        client = MagicMock()
        client.submit_job.side_effect = Exception('boom')
        mock_client_factory.return_value = client
        ok = acw_metrics.submit_exit_acw(self.campana_dialer.id, 1.0)
        self.assertFalse(ok)

    @patch('ominicontacto_app.services.dialer.acw_metrics._gearman_client')
    def test_submit_exit_acw_no_client_returns_false(self, mock_client_factory):
        mock_client_factory.return_value = None
        ok = acw_metrics.submit_exit_acw(self.campana_dialer.id, 1.0)
        self.assertFalse(ok)
