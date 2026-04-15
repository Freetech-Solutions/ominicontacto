# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from mock import MagicMock, patch
from django.test import RequestFactory, SimpleTestCase

from api_app.views.reports import CampaignStatsReportView


class CampaignStatsReportViewTest(SimpleTestCase):

    def setUp(self):
        self.factory = RequestFactory()

    @patch('api_app.views.reports.InteractionTransfers')
    @patch('api_app.views.reports.InteractionsSummary')
    def test_campaign_stats_include_transferred_interactions_in_answered_totals(
            self, mock_interactions_summary, mock_interaction_transfers):
        request = self.factory.get(
            '/api/reports/campaign-stats/',
            {'campaign_id': '4'},
        )

        transferidas_in_ids = ['int-1', 'int-2']
        mock_interaction_transfers.objects.filter.return_value.values_list.return_value = (
            transferidas_in_ids
        )

        qs = MagicMock()
        qs.aggregate.return_value = {
            'total': 7,
            'total_outbound': 0,
            'outbound_answered': 0,
            'answered_direct': 3,
            'answered_transferred': 2,
            'sales': 0,
            'answered_by_agent': 5,
            'answered_agent_gt_10s': 1,
            'sum_agent_duration_gt0': 15,
            'count_agent_duration_gt0': 5,
            'sum_wait_conn_duration_inbound_answered': 10,
            'count_inbound_answered': 5,
            'inbound_abandoned_gt5': 1,
            'total_inbound': 6,
            'transferred_count': 2,
            'bot_contained': 0,
            'sum_bot_duration': 0,
        }
        mock_interactions_summary.objects.filter.return_value = qs

        response = CampaignStatsReportView().get(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['totals']['answered_direct'], 3)
        self.assertEqual(response.data['totals']['answered_transferred'], 2)
        self.assertEqual(response.data['totals']['total_answered'], 5)

        campaign_filter = mock_interactions_summary.objects.filter.call_args[0][0]
        self.assertEqual(campaign_filter.connector, 'OR')
        self.assertEqual(campaign_filter.children[0], ('campaign_id', 4))
        self.assertEqual(
            campaign_filter.children[1],
            ('interaction_id__in', transferidas_in_ids),
        )
        mock_interaction_transfers.objects.filter.assert_called_once_with(
            destination_campaign_id=4
        )
