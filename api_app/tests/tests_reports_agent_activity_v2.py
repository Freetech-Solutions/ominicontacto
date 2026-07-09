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
from __future__ import unicode_literals

import json

from django.urls import reverse

from mock import patch

from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class ReportsAgentActivityV2Test(OMLBaseTest):
    def setUp(self):
        super(ReportsAgentActivityV2Test, self).setUp()
        user = self.crear_administrador(username='admin_agents_activity_v2')
        self.client.login(username=user.username, password=PASSWORD)
        self.url = reverse('api_reportes_agents_activity_v2')
        self.default_params = {
            'date_start': '2025-02-01',
            'date_end': '2025-02-01',
        }

    def _json(self, response):
        return json.loads(response.content.decode('utf-8'))

    @patch('api_app.views.reports_agent_activity_v2._compute_allowed_agent_ids', return_value=(None, None))
    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2._get_agent_whatsapp_act_avg')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_transfer_counts')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_interactions_kpis')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_activity_kpis_v2')
    def test_transfer_pct_normal_calculation(
        self,
        mock_activity,
        mock_interactions,
        mock_transfers,
        mock_act_avg,
        _mock_permission,
        _mock_allowed_agents,
    ):
        mock_activity.return_value = {
            'agents': [{
                'agente_id': 101,
                'session_seconds': 3600,
                'ready_seconds': 1800,
                'pause_seconds': 900,
                'acw_seconds': 900,
                'ready_ratio': 0.5,
                'pause_ratio': 0.25,
                'acw_ratio': 0.25,
            }]
        }
        mock_interactions.return_value = [{
            'agent_id': 101,
            'interactions_total': 20,
            'interactions_inbound': 12,
            'interactions_outbound': 8,
            'talk_seconds': 600.0,
            'avg_talk_seconds_answered': 30.0,
            'wait_conn_duration': 80.0,
            'avg_wait_conn_duration': 4.0,
        }]
        mock_transfers.return_value = [{
            'agent_id': 101,
            'transfer_count': 5,
        }]
        mock_act_avg.return_value = [{
            'agent_id': 101,
            'act_avg': 75.0,
        }]

        response = self.client.get(self.url, self.default_params)
        self.assertEqual(response.status_code, 200)
        data = self._json(response)
        self.assertEqual(len(data['data']), 1)
        row = data['data'][0]
        self.assertEqual(row['transfer_count'], 5)
        self.assertEqual(row['transfer_pct'], 25.0)
        self.assertEqual(row['act_avg'], 75.0)

    @patch('api_app.views.reports_agent_activity_v2._compute_allowed_agent_ids', return_value=(None, None))
    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2._get_agent_whatsapp_act_avg')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_transfer_counts')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_interactions_kpis')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_activity_kpis_v2')
    def test_transfer_pct_division_by_zero_returns_zero(
        self,
        mock_activity,
        mock_interactions,
        mock_transfers,
        mock_act_avg,
        _mock_permission,
        _mock_allowed_agents,
    ):
        mock_activity.return_value = {'agents': [{'agente_id': 102}]}
        mock_interactions.return_value = [{
            'agent_id': 102,
            'interactions_total': 0,
            'interactions_inbound': 0,
            'interactions_outbound': 0,
            'talk_seconds': 0.0,
            'avg_talk_seconds_answered': 0.0,
            'wait_conn_duration': 0.0,
            'avg_wait_conn_duration': 0.0,
        }]
        mock_transfers.return_value = [{
            'agent_id': 102,
            'transfer_count': 3,
        }]
        mock_act_avg.return_value = []

        response = self.client.get(self.url, self.default_params)
        self.assertEqual(response.status_code, 200)
        data = self._json(response)
        self.assertEqual(len(data['data']), 1)
        row = data['data'][0]
        self.assertEqual(row['transfer_count'], 3)
        self.assertEqual(row['transfer_pct'], 0.0)
        self.assertEqual(row['act_avg'], 0)

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2._get_agent_whatsapp_act_avg')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_transfer_counts')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_interactions_kpis')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_activity_kpis_v2')
    def test_transfer_service_called_with_ok_status_filter(
        self,
        mock_activity,
        mock_interactions,
        mock_transfers,
        mock_act_avg,
        _mock_permission,
    ):
        mock_activity.return_value = {'agents': [{'agente_id': 103}]}
        mock_interactions.return_value = [{
            'agent_id': 103,
            'interactions_total': 10,
            'interactions_inbound': 5,
            'interactions_outbound': 5,
            'talk_seconds': 100.0,
            'avg_talk_seconds_answered': 10.0,
            'wait_conn_duration': 20.0,
            'avg_wait_conn_duration': 2.0,
        }]
        mock_transfers.return_value = []
        mock_act_avg.return_value = []

        response = self.client.get(self.url, self.default_params)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_transfers.called)
        _, kwargs = mock_transfers.call_args
        self.assertEqual(kwargs.get('status_filter'), 'OK')
        self.assertTrue(mock_interactions.called)
        _, interactions_kwargs = mock_interactions.call_args
        self.assertTrue(interactions_kwargs.get('include_whatsapp_in_out'))

    @patch('api_app.views.reports_agent_activity_v2._compute_allowed_agent_ids', return_value=(None, None))
    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2._get_agent_whatsapp_act_avg')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_transfer_counts')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_interactions_kpis')
    @patch('api_app.views.reports_agent_activity_v2.get_agent_activity_kpis_v2')
    def test_response_contract_includes_transfer_fields(
        self,
        mock_activity,
        mock_interactions,
        mock_transfers,
        mock_act_avg,
        _mock_permission,
        _mock_allowed_agents,
    ):
        mock_activity.return_value = {'agents': [{'agente_id': 104}]}
        mock_interactions.return_value = [{
            'agent_id': 104,
            'interactions_total': 7,
            'interactions_inbound': 3,
            'interactions_outbound': 4,
            'talk_seconds': 70.0,
            'avg_talk_seconds_answered': 10.0,
            'wait_conn_duration': 14.0,
            'avg_wait_conn_duration': 2.0,
        }]
        mock_transfers.return_value = []
        mock_act_avg.return_value = []

        response = self.client.get(self.url, self.default_params)
        self.assertEqual(response.status_code, 200)
        data = self._json(response)
        self.assertEqual(len(data['data']), 1)
        row = data['data'][0]
        self.assertIn('transfer_count', row)
        self.assertIn('transfer_pct', row)
        self.assertIn('act_avg', row)

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2.get_agents_activity_v2_flat_rows')
    def test_response_includes_pagination_metadata(self, mock_flat_rows, _mock_permission):
        mock_flat_rows.return_value = [{'agent_id': 1, 'agent_name': 'A'}]
        params = dict(self.default_params, page=1, page_size=10)
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        data = self._json(response)
        self.assertIn('total_count', data)
        self.assertIn('page', data)
        self.assertIn('page_size', data)
        self.assertIn('num_pages', data)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['page_size'], 10)
        self.assertEqual(data['total_count'], 1)
        self.assertEqual(data['num_pages'], 1)

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2.get_agents_activity_v2_flat_rows')
    def test_pagination_page_size_respected(self, mock_flat_rows, _mock_permission):
        mock_flat_rows.return_value = [
            {'agent_id': i, 'agent_name': 'Agente %s' % i}
            for i in range(25)
        ]
        params = dict(self.default_params, page=1, page_size=10)
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        data = self._json(response)
        self.assertEqual(len(data['data']), 10)
        self.assertEqual(data['total_count'], 25)
        self.assertEqual(data['page_size'], 10)
        self.assertEqual(data['num_pages'], 3)

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2.get_agents_activity_v2_flat_rows')
    def test_pagination_second_page(self, mock_flat_rows, _mock_permission):
        rows = [
            {'agent_id': i, 'agent_name': 'Agente %s' % i}
            for i in range(25)
        ]
        mock_flat_rows.return_value = rows
        params = dict(self.default_params, page=2, page_size=10)
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        data = self._json(response)
        self.assertEqual(len(data['data']), 10)
        self.assertEqual(data['page'], 2)
        self.assertEqual(data['data'][0]['agent_id'], rows[10]['agent_id'])

    @patch('api_app.views.permissions.TienePermisoOML.has_permission', return_value=True)
    @patch('api_app.views.reports_agent_activity_v2.get_agents_activity_v2_flat_rows')
    def test_pagination_invalid_page_size_defaults_to_10(self, mock_flat_rows, _mock_permission):
        mock_flat_rows.return_value = [{'agent_id': 1, 'agent_name': 'A'}]
        params = dict(self.default_params, page_size=99)
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        data = self._json(response)
        self.assertEqual(data['page_size'], 10)
