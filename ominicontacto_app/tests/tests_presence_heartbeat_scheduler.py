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
Tests for presence_heartbeat_scheduler: timeout closure and HB recovery.
"""
from __future__ import unicode_literals

from mock import MagicMock, patch
from django.utils import timezone

from ominicontacto_app.management.commands.presence_heartbeat_scheduler import (
    sweep_presence_heartbeat_timeouts,
)
from ominicontacto_app.services.agent.presence import (
    AGENT_STATUS_KEY_TEMPLATE,
    AgentPresenceManager,
)
from ominicontacto_app.tests.utiles import OMLBaseTest
from reportes_app.agent_activity_dual_write import (
    SOURCE_HEARTBEAT_RECOVER,
    SOURCE_HEARTBEAT_TIMEOUT,
    SOURCE_SESSION_EXPIRED,
)
from reportes_app.models import AgentActivityEventV2


class SchedulerRedisMock(object):
    """Mock Redis mínimo para barridos del scheduler."""

    def __init__(self, agent_statuses=None, heartbeat_agent_ids=None, pause_ids=None):
        self.agent_statuses = agent_statuses or {}
        self.heartbeat_agent_ids = set(heartbeat_agent_ids or [])
        self.pause_ids = pause_ids or {}

    def ping(self):
        return True

    def scan(self, cursor=0, match=None, count=200):
        keys = []
        if match == 'OML:AGENT:*':
            keys = [
                AGENT_STATUS_KEY_TEMPLATE.format(agent_id)
                for agent_id in self.agent_statuses
            ]
        elif match == 'OML:PRESENCE:HB:*':
            keys = [
                'OML:PRESENCE:HB:{0}:browser-1'.format(agent_id)
                for agent_id in self.heartbeat_agent_ids
            ]
        return 0, keys

    def hget(self, key, field):
        for agent_id, status in self.agent_statuses.items():
            if key == AGENT_STATUS_KEY_TEMPLATE.format(agent_id):
                if field == 'STATUS':
                    return status
                if field == 'PAUSE_ID':
                    return self.pause_ids.get(agent_id)
                return None
        return None


class PresenceHeartbeatSchedulerTests(OMLBaseTest):

    def setUp(self):
        super(PresenceHeartbeatSchedulerTests, self).setUp()
        self.agente = self.crear_agente_profile()
        self.manager = AgentPresenceManager()

    def _open_presence_v2(self):
        AgentActivityEventV2.objects.create(
            agente_id=self.agente.id,
            ts=timezone.now(),
            event_type=AgentActivityEventV2.EventType.SESSION_LOGIN,
            metadata={},
        )

    def _create_hb_timeout_logout(self, status_before='READY', pause_id=None):
        metadata = {
            'reason': 'timeout',
            'status_before': status_before,
            'heartbeat_timeout_sec': 60,
        }
        if pause_id is not None:
            metadata['pause_id'] = pause_id
        return AgentActivityEventV2.objects.create(
            agente_id=self.agente.id,
            ts=timezone.now(),
            event_type=AgentActivityEventV2.EventType.SESSION_LOGOUT,
            source=SOURCE_HEARTBEAT_TIMEOUT,
            metadata=metadata,
        )

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_timeout_closes_v2_and_sets_unavailable(
        self, mock_redis_conn, mock_agent_activity_cls
    ):
        self._open_presence_v2()
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'READY'},
            heartbeat_agent_ids=[],
        )
        mock_activity = MagicMock()
        mock_agent_activity_cls.return_value = mock_activity

        count_before = AgentActivityEventV2.objects.count()
        sweep_presence_heartbeat_timeouts()

        self.assertEqual(AgentActivityEventV2.objects.count(), count_before + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.SESSION_LOGOUT)
        self.assertEqual(last_event.source, SOURCE_HEARTBEAT_TIMEOUT)
        mock_activity.set_agent_as_unavailable.assert_called_once()
        self.assertTrue(self.manager.should_redirect_by_closed_presence(self.agente.id))

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_timeout_idempotent(self, mock_redis_conn, mock_agent_activity_cls):
        self._create_hb_timeout_logout(status_before='READY')
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'UNAVAILABLE'},
            heartbeat_agent_ids=[],
        )
        mock_agent_activity_cls.return_value = MagicMock()

        count_before = AgentActivityEventV2.objects.count()
        sweep_presence_heartbeat_timeouts()
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before)

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_reconciliation_when_v2_closed_redis_still_ready(
        self, mock_redis_conn, mock_agent_activity_cls
    ):
        self._create_hb_timeout_logout(status_before='READY')
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'READY'},
            heartbeat_agent_ids=[],
        )
        mock_activity = MagicMock()
        mock_agent_activity_cls.return_value = mock_activity

        count_before = AgentActivityEventV2.objects.count()
        sweep_presence_heartbeat_timeouts()

        self.assertEqual(AgentActivityEventV2.objects.count(), count_before)
        mock_activity.set_agent_as_unavailable.assert_called_once()

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_recovery_reopens_v2_and_restores_ready(
        self, mock_redis_conn, mock_agent_activity_cls
    ):
        self._create_hb_timeout_logout(status_before='READY')
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'UNAVAILABLE'},
            heartbeat_agent_ids=[self.agente.id],
        )
        mock_activity = MagicMock()
        mock_agent_activity_cls.return_value = mock_activity

        count_before = AgentActivityEventV2.objects.count()
        sweep_presence_heartbeat_timeouts()

        self.assertEqual(AgentActivityEventV2.objects.count(), count_before + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.SESSION_LOGIN)
        self.assertEqual(last_event.source, SOURCE_HEARTBEAT_RECOVER)
        self.assertEqual(last_event.metadata.get('status_restored'), 'READY')
        mock_activity.set_agent_as_ready.assert_called_once()
        self.assertFalse(self.manager.should_redirect_by_closed_presence(self.agente.id))

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_recovery_restores_pause_status_from_metadata(
        self, mock_redis_conn, mock_agent_activity_cls
    ):
        self._create_hb_timeout_logout(status_before='PAUSE-ACW', pause_id='0')
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'UNAVAILABLE'},
            heartbeat_agent_ids=[self.agente.id],
        )
        mock_activity = MagicMock()
        mock_agent_activity_cls.return_value = mock_activity

        sweep_presence_heartbeat_timeouts()

        mock_activity.pause_agent.assert_called_once()
        args = mock_activity.pause_agent.call_args[0]
        self.assertEqual(args[0].id, self.agente.id)
        self.assertEqual(args[1], '0')

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_no_recovery_when_offline(self, mock_redis_conn, mock_agent_activity_cls):
        self._create_hb_timeout_logout(status_before='READY')
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'OFFLINE'},
            heartbeat_agent_ids=[self.agente.id],
        )
        mock_agent_activity_cls.return_value = MagicMock()

        count_before = AgentActivityEventV2.objects.count()
        sweep_presence_heartbeat_timeouts()

        self.assertEqual(AgentActivityEventV2.objects.count(), count_before)

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_no_recovery_without_heartbeat(self, mock_redis_conn, mock_agent_activity_cls):
        self._create_hb_timeout_logout(status_before='READY')
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'UNAVAILABLE'},
            heartbeat_agent_ids=[],
        )
        mock_agent_activity_cls.return_value = MagicMock()

        count_before = AgentActivityEventV2.objects.count()
        sweep_presence_heartbeat_timeouts()

        self.assertEqual(AgentActivityEventV2.objects.count(), count_before)

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_no_recovery_when_sess_expired_logout(
        self, mock_redis_conn, mock_agent_activity_cls
    ):
        AgentActivityEventV2.objects.create(
            agente_id=self.agente.id,
            ts=timezone.now(),
            event_type=AgentActivityEventV2.EventType.SESSION_LOGOUT,
            source=SOURCE_SESSION_EXPIRED,
            metadata={'reason': 'session_expired'},
        )
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'UNAVAILABLE'},
            heartbeat_agent_ids=[self.agente.id],
        )
        mock_agent_activity_cls.return_value = MagicMock()

        count_before = AgentActivityEventV2.objects.count()
        sweep_presence_heartbeat_timeouts()

        self.assertEqual(AgentActivityEventV2.objects.count(), count_before)

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_no_recovery_when_v2_open(self, mock_redis_conn, mock_agent_activity_cls):
        AgentActivityEventV2.objects.create(
            agente_id=self.agente.id,
            ts=timezone.now(),
            event_type=AgentActivityEventV2.EventType.SESSION_LOGIN,
            metadata={},
        )
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'UNAVAILABLE'},
            heartbeat_agent_ids=[self.agente.id],
        )
        mock_agent_activity_cls.return_value = MagicMock()

        count_before = AgentActivityEventV2.objects.count()
        sweep_presence_heartbeat_timeouts()

        self.assertEqual(AgentActivityEventV2.objects.count(), count_before)

    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.AgentActivityAmiManager'
    )
    @patch(
        'ominicontacto_app.management.commands.presence_heartbeat_scheduler'
        '.create_redis_connection'
    )
    def test_recovery_idempotent(self, mock_redis_conn, mock_agent_activity_cls):
        self._create_hb_timeout_logout(status_before='READY')
        mock_redis_conn.return_value = SchedulerRedisMock(
            agent_statuses={self.agente.id: 'UNAVAILABLE'},
            heartbeat_agent_ids=[self.agente.id],
        )
        mock_agent_activity_cls.return_value = MagicMock()

        sweep_presence_heartbeat_timeouts()
        count_after_first = AgentActivityEventV2.objects.count()

        sweep_presence_heartbeat_timeouts()
        self.assertEqual(AgentActivityEventV2.objects.count(), count_after_first)
