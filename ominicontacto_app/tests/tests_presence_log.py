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
Tests for presence log: idempotency, debounce (cooldown), and UNPAUSEALL
normalization (pausa_id always NULL).
"""
from __future__ import unicode_literals

import time as time_module
from datetime import timedelta
from mock import MagicMock, patch
from django.contrib.sessions.models import Session
from django.utils import timezone

from ominicontacto_app.services.agent.presence import (
    AgentPresenceManager,
    AGENT_STATUS_KEY_TEMPLATE,
    DEBOUNCE_KEY_TEMPLATE,
)
from ominicontacto_app.tests.utiles import OMLBaseTest
from reportes_app.agent_activity_dual_write import SOURCE_SESSION_EXPIRED
from reportes_app.models import ActividadAgenteLog, AgentActivityEventV2


class PresenceLogTests(OMLBaseTest):

    def setUp(self):
        super(PresenceLogTests, self).setUp()
        self.agente = self.crear_agente_profile()
        self.manager = AgentPresenceManager()

    def _redis_mock(self, status=None, debounce_type=None, debounce_ts=None):
        """Returns a mock Redis that hget(key, field) returns status for agent key,
        and debounce_type/debounce_ts for debounce key."""
        def hget(key, field):
            if key == AGENT_STATUS_KEY_TEMPLATE.format(self.agente.id):
                if field == 'STATUS':
                    return status
                return None
            if key == DEBOUNCE_KEY_TEMPLATE.format(self.agente.id):
                if field == 'last_event_type':
                    return debounce_type
                if field == 'last_event_ts':
                    return debounce_ts
                return None
            return None
        conn = MagicMock()
        conn.hget = hget
        conn.hset = MagicMock()
        return conn

    @patch('ominicontacto_app.services.agent.presence.create_redis_connection')
    def test_login_normal_one_event(self, mock_redis):
        mock_redis.return_value = self._redis_mock(status='OFFLINE')
        count_before = AgentActivityEventV2.objects.count()
        self.manager.login(self.agente)
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.agente_id, self.agente.id)
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.SESSION_LOGIN)

    @patch('ominicontacto_app.services.agent.presence.create_redis_connection')
    def test_logout_normal_one_event(self, mock_redis):
        mock_redis.return_value = self._redis_mock(status='READY')
        count_before = AgentActivityEventV2.objects.count()
        self.manager.logout(self.agente)
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.agente_id, self.agente.id)
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.SESSION_LOGOUT)

    @patch('ominicontacto_app.services.agent.presence.create_redis_connection')
    def test_login_duplicate_no_new_event(self, mock_redis):
        mock_redis.return_value = self._redis_mock(status='READY')
        count_before = AgentActivityEventV2.objects.count()
        self.manager.login(self.agente)
        self.manager.login(self.agente)
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before)

    @patch('ominicontacto_app.services.agent.presence.create_redis_connection')
    def test_login_persisted_when_v2_closed_but_redis_ready(self, mock_redis):
        """Tras SESS_EXPIRED en V2, Redis puede quedar READY; LOGIN debe reabrir V2."""
        mock_redis.return_value = self._redis_mock(status='READY')
        AgentActivityEventV2.objects.create(
            agente_id=self.agente.id,
            ts=timezone.now(),
            event_type=AgentActivityEventV2.EventType.SESSION_LOGOUT,
            source=SOURCE_SESSION_EXPIRED,
            metadata={'reason': 'session_expired'},
        )
        count_before = AgentActivityEventV2.objects.count()
        self.manager.login(self.agente)
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.SESSION_LOGIN)
        self.assertFalse(self.manager.should_redirect_by_closed_presence(self.agente.id))

    def test_logout_duplicate_second_suppressed(self):
        # LOGOUT idempotency uses last event in V2; first logout persists, second is suppressed.
        count_before = AgentActivityEventV2.objects.count()
        self.manager.logout(self.agente)
        self.manager.logout(self.agente)
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.SESSION_LOGOUT)

    @patch('ominicontacto_app.services.agent.presence.create_redis_connection')
    def test_logout_then_login_within_cooldown_no_new_login(self, mock_redis):
        # After logout, debounce has SESSION_LOGOUT and recent ts; next login suppressed.
        recent_ts = str(int((time_module.time() - 0.2) * 1000))
        mock_redis.return_value = self._redis_mock(
            status='OFFLINE',
            debounce_type=ActividadAgenteLog.SESSION_LOGOUT,
            debounce_ts=recent_ts,
        )
        count_before = AgentActivityEventV2.objects.count()
        self.manager.login(self.agente)
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before)

    @patch('ominicontacto_app.services.agent.presence.create_redis_connection')
    def test_unpause_pausa_id_null(self, mock_redis):
        mock_redis.return_value = self._redis_mock(status='READY')
        count_before = AgentActivityEventV2.objects.count()
        self.manager.unpause(self.agente, '1')
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.STATE_READY)
        self.assertIsNone(last_event.pause_id)
        self.assertIsNone(last_event.aux_code)

    def test_pause_pausa_id_persisted(self):
        count_before = AgentActivityEventV2.objects.count()
        self.manager.pause(self.agente, '42')
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.STATE_PAUSED)
        self.assertEqual(last_event.agente_id, self.agente.id)
        # pausa_id '42' sin Pausa FK -> se persiste como aux_code
        self.assertIsNone(last_event.pause_id)
        self.assertEqual(last_event.aux_code, '42')

    def test_enforce_login_is_non_mutating(self):
        count_before = AgentActivityEventV2.objects.count()
        should_redirect = self.manager.enforce_login(self.agente)
        self.assertFalse(should_redirect)
        self.assertEqual(AgentActivityEventV2.objects.count(), count_before)

    def test_should_redirect_when_presence_closed_in_v2(self):
        AgentActivityEventV2.objects.create(
            agente_id=self.agente.id,
            ts=timezone.now(),
            event_type=AgentActivityEventV2.EventType.SESSION_LOGOUT,
            metadata={},
        )
        self.assertTrue(self.manager.should_redirect_by_closed_presence(self.agente.id))

    def test_fix_previous_open_session_logs_writes_v2_only(self):
        session_key = 'old-session-key'
        self.agente.user.last_session_key = session_key
        self.agente.user.save(update_fields=['last_session_key'])
        Session.objects.create(
            session_key=session_key,
            session_data='',
            expire_date=timezone.now() + timedelta(hours=1),
        )
        AgentActivityEventV2.objects.create(
            agente_id=self.agente.id,
            ts=timezone.now() - timedelta(minutes=5),
            event_type=AgentActivityEventV2.EventType.SESSION_LOGIN,
            metadata={},
        )
        legacy_count_before = ActividadAgenteLog.objects.count()
        v2_count_before = AgentActivityEventV2.objects.count()

        self.manager.fix_previous_open_session_logs(self.agente.user, self.agente)

        # No se escribe en ActividadAgenteLog (solo V2)
        self.assertEqual(ActividadAgenteLog.objects.count(), legacy_count_before)
        self.assertEqual(AgentActivityEventV2.objects.count(), v2_count_before + 1)
        last_event = AgentActivityEventV2.objects.order_by('-id').first()
        self.assertEqual(last_event.event_type, AgentActivityEventV2.EventType.SESSION_LOGOUT)
        self.assertEqual(last_event.source, SOURCE_SESSION_EXPIRED)
        self.assertEqual(last_event.metadata.get('reason'), 'session_expired')
