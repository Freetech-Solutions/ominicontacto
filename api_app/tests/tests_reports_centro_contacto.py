# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from mock import MagicMock, Mock, patch
from django.db import connection
from django.utils import timezone
from django.db.models import Q
from django.test import SimpleTestCase
from django.urls import reverse

from ominicontacto_app.models import Campana, User
from reportes_app.models import InteractionsSummary, InteractionTransfers
from ominicontacto_app.tests.factories import (
    AgenteProfileFactory,
    CampanaFactory,
    GrupoFactory,
    QueueFactory,
    QueueMemberFactory,
)
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD
from api_app.views.reports_centro_contacto import (
    _campaign_answering_agent_id_from_segments,
    _format_duration_mmss,
    _interaction_transfer_to_dict,
    _parse_agent_segments,
    _parse_export_filters,
    _segment_duration_display_for_transfer,
    _segment_duration_seconds_for_transfer,
    get_omnichannel_share_data,
    obtener_llamadas_por_campana,
    obtener_llamadas_salientes_por_campana,
    obtener_llamadas_salientes_por_dia,
    obtener_llamadas_salientes_por_hora,
    obtener_llamadas_salientes_por_mes,
    obtener_kpis_centro_contacto,
    obtener_listado_llamadas_atendidas,
    obtener_listado_llamadas_no_atendidas,
    obtener_distribucion_status_llamadas_no_atendidas,
)
from reportes_app.forms import ReporteCentroContactoForm


MOCK_KPIS = {
    'contact_rate_pct': None,
    'conversion_rate_pct': None,
    'rpc_pct': None,
    'aht': None,
    'asa': None,
    'abandon_rate_pct': None,
    'expire_rate_pct': None,
    'transfer_rate_pct': None,
    'bot_containment_pct': None,
    'bot_hours': None,
    'totals': {
        'total': 0,
        'total_outbound': 0,
        'outbound_answered': 0,
        'total_inbound': 0,
        'inbound_answered': 0,
        'inbound_abandoned_gt5': 0,
        'inbound_timeout': 0,
        'attended_by_human': 0,
        'sales': 0,
        'answered_agent_gt10': 0,
        'transferred': 0,
        'bot_only': 0,
        'count_agent_gt0': 0,
        'count_asa': 0,
        'sum_agent_duration': 0,
        'sum_wait_conn_duration_asa': 0,
        'sum_bot_duration': 0,
    },
}


class ReporteCentroContactoFormViewTest(OMLBaseTest):

    def setUp(self):
        super(ReporteCentroContactoFormViewTest, self).setUp()
        self.fecha = '01/01/2025-01/01/2025'
        self.url = reverse('reporte_centro_de_contacto')
        self.admin_user = self.crear_administrador(username='admin_cc_report')

        self.supervisor_profile = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.supervisor_user = self.supervisor_profile.user

        self.campana_activa = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            nombre='Activa reporte centro contacto',
        )
        self.campana_pausada = CampanaFactory.create(
            estado=Campana.ESTADO_PAUSADA,
            nombre='Pausada reporte centro contacto',
        )
        self.campana_finalizada = CampanaFactory.create(
            estado=Campana.ESTADO_FINALIZADA,
            nombre='Finalizada reporte centro contacto',
        )
        self.campana_no_asignada = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            nombre='No asignada supervisor reporte centro contacto',
        )

        self.campana_activa.supervisors.add(self.supervisor_user)
        self.campana_finalizada.supervisors.add(self.supervisor_user)

        self.queue_activa = QueueFactory.create(campana=self.campana_activa)
        self.queue_pausada = QueueFactory.create(campana=self.campana_pausada)
        self.queue_no_asignada = QueueFactory.create(campana=self.campana_no_asignada)

        self.grupo_ventas = GrupoFactory.create(nombre='grp_cc_ventas')
        self.grupo_soporte = GrupoFactory.create(nombre='grp_cc_soporte')
        self.grupo_oculto = GrupoFactory.create(nombre='grp_cc_oculto')

        self.agente_ventas_activa = AgenteProfileFactory.create(grupo=self.grupo_ventas)
        self.agente_ventas_pausada = AgenteProfileFactory.create(grupo=self.grupo_ventas)
        self.agente_soporte_activa = AgenteProfileFactory.create(grupo=self.grupo_soporte)
        self.agente_oculto = AgenteProfileFactory.create(grupo=self.grupo_oculto)

        QueueMemberFactory.create(member=self.agente_ventas_activa, queue_name=self.queue_activa)
        QueueMemberFactory.create(member=self.agente_ventas_pausada, queue_name=self.queue_pausada)
        QueueMemberFactory.create(member=self.agente_soporte_activa, queue_name=self.queue_activa)
        QueueMemberFactory.create(member=self.agente_oculto, queue_name=self.queue_no_asignada)

    def _post_form(self, username, data):
        self.client.login(username=username, password=PASSWORD)
        return self.client.post(self.url, data)

    def test_filters_render_collapsible_container(self):
        self.client.login(username=self.admin_user.username, password=PASSWORD)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="wrapper-search"')
        self.assertContains(response, 'id="btnCollapse"')
        self.assertContains(response, 'data-target="#wrapperSearchForm"')
        self.assertContains(response, 'id="wrapperSearchForm"')
        self.assertContains(response, 'id="wrapperSearchForm" class="collapse show"')

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_fecha_with_spaces_is_processed(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': '01/01/2025 - 01/01/2025',
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(mock_kpis.call_args[1]['start_date'])
        self.assertIsNotNone(mock_kpis.call_args[1]['end_date'])

    @patch('api_app.views.reports_centro_contacto.obtener_llamadas_por_campana')
    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_ingresos_voz_por_campana_renderiza_transfer_in_out(
            self, mock_kpis, mock_llamadas_por_campana):
        mock_kpis.return_value = MOCK_KPIS
        mock_llamadas_por_campana.side_effect = [
            [],
            [
                {
                    'campaign_id': self.campana_activa.id,
                    'campaign_name': self.campana_activa.nombre,
                    'received': 10,
                    'answered': 8,
                    'unanswered': 2,
                    'expired': 1,
                    'abandoned': 1,
                    'transferred': 3,
                    'avg_wait_seconds': 12.0,
                    'avg_talk_seconds': 45.0,
                    'pct_answered': 80.0,
                    'pct_unanswered': 20.0,
                    'pct_expired': 10.0,
                    'pct_abandoned': 10.0,
                    'pct_transferred': 30.0,
                    'transfer_in_count': 2,
                    'transfer_out_count': 3,
                },
            ],
        ]

        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
            },
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        section_start = content.index('Llamadas de voz por campaña')
        table_start = content.index('<table', section_start)
        table_end = content.index('</table>', table_start)
        table_html = content[table_start:table_end]

        self.assertIn('Transfer (In/Out)', table_html)
        self.assertNotIn('Transferidas', table_html)
        self.assertIn('fa-arrow-down', table_html)
        self.assertIn('fa-arrow-up', table_html)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_form_submit_passes_duracion_bot_min_to_kpis(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'duracion_bot_min': '60',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_kpis.call_args[1].get('duracion_bot_min'), 60)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_all_campaigns_without_finalizadas_excludes_finalized(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
            },
        )
        self.assertEqual(response.status_code, 200)
        allowed_campaigns = mock_kpis.call_args[1]['allowed_campaigns']
        self.assertIn(self.campana_activa.id, allowed_campaigns)
        self.assertIn(self.campana_pausada.id, allowed_campaigns)
        self.assertNotIn(self.campana_finalizada.id, allowed_campaigns)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_all_campaigns_with_finalizadas_includes_finalized(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'incluir_finalizadas': 'on',
            },
        )
        self.assertEqual(response.status_code, 200)
        allowed_campaigns = mock_kpis.call_args[1]['allowed_campaigns']
        self.assertIn(self.campana_finalizada.id, allowed_campaigns)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_single_campaign_selection_uses_only_that_campaign(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [str(self.campana_activa.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        allowed_campaigns = mock_kpis.call_args[1]['allowed_campaigns']
        self.assertEqual(allowed_campaigns, [self.campana_activa.id])

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_multiple_campaign_selection_uses_selected_campaigns(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [str(self.campana_activa.id), str(self.campana_pausada.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        allowed_campaigns = mock_kpis.call_args[1]['allowed_campaigns']
        self.assertEqual(set(allowed_campaigns), {self.campana_activa.id, self.campana_pausada.id})

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_supervisor_all_campaigns_are_limited_to_assigned_campaigns(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.supervisor_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'incluir_finalizadas': 'on',
            },
        )
        self.assertEqual(response.status_code, 200)
        allowed_campaigns = set(mock_kpis.call_args[1]['allowed_campaigns'])
        expected_campaigns = set(
            self.supervisor_profile.campanas_asignadas_actuales().values_list('id', flat=True)
        )
        self.assertEqual(allowed_campaigns, expected_campaigns)
        self.assertNotIn(self.campana_no_asignada.id, allowed_campaigns)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_all_groups_sets_allowed_agent_ids_none(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'grupo_agente': [ReporteCentroContactoForm.TODOS_LOS_GRUPOS_VALUE],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(mock_kpis.call_args[1]['allowed_agent_ids'])

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_single_group_selection_limits_allowed_agents(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'grupo_agente': [str(self.grupo_ventas.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        allowed_agent_ids = set(mock_kpis.call_args[1]['allowed_agent_ids'])
        self.assertEqual(
            allowed_agent_ids,
            {self.agente_ventas_activa.id, self.agente_ventas_pausada.id},
        )

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_multiple_group_selection_uses_agent_union(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'grupo_agente': [str(self.grupo_ventas.id), str(self.grupo_soporte.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        allowed_agent_ids = set(mock_kpis.call_args[1]['allowed_agent_ids'])
        self.assertEqual(
            allowed_agent_ids,
            {
                self.agente_ventas_activa.id,
                self.agente_ventas_pausada.id,
                self.agente_soporte_activa.id,
            },
        )

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_group_filter_intersects_with_selected_campaigns(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [str(self.campana_activa.id)],
                'grupo_agente': [str(self.grupo_ventas.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mock_kpis.call_args[1]['allowed_campaigns'],
            [self.campana_activa.id],
        )
        self.assertEqual(
            set(mock_kpis.call_args[1]['allowed_agent_ids']),
            {self.agente_ventas_activa.id},
        )

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_supervisor_cannot_filter_by_group_outside_visible_scope(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.supervisor_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'grupo_agente': [str(self.grupo_oculto.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_valid())
        self.assertIn('grupo_agente', response.context['form'].errors)
        self.assertFalse(mock_kpis.called)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_all_agents_sets_allowed_agent_ids_none_when_groups_all(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'agente': [ReporteCentroContactoForm.TODOS_LOS_AGENTES_VALUE],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(mock_kpis.call_args[1]['allowed_agent_ids'])

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_single_agent_selection_limits_allowed_agents(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'agente': [str(self.agente_ventas_activa.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mock_kpis.call_args[1]['allowed_agent_ids'],
            [self.agente_ventas_activa.id],
        )

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_multiple_agent_selection_limits_allowed_agents(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'agente': [str(self.agente_ventas_activa.id), str(self.agente_soporte_activa.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(mock_kpis.call_args[1]['allowed_agent_ids']),
            {self.agente_ventas_activa.id, self.agente_soporte_activa.id},
        )

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_agent_and_group_filters_are_intersected(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'grupo_agente': [str(self.grupo_ventas.id)],
                'agente': [str(self.agente_ventas_activa.id), str(self.agente_soporte_activa.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(mock_kpis.call_args[1]['allowed_agent_ids']),
            {self.agente_ventas_activa.id},
        )

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_supervisor_cannot_filter_by_agent_outside_visible_scope(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.supervisor_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'agente': [str(self.agente_oculto.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_valid())
        self.assertIn('agente', response.context['form'].errors)
        self.assertFalse(mock_kpis.called)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_campana_id_is_forwarded_to_kpis(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'campana_id': str(self.campana_activa.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_kpis.call_args[1]['campaign_id'], self.campana_activa.id)
        self.assertEqual(mock_kpis.call_args[1]['allowed_campaigns'], [self.campana_activa.id])

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_campana_id_invalid_shows_error_and_does_not_call_kpis(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'campana_id': 'abc',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_valid())
        self.assertIn('campana_id', response.context['form'].errors)
        self.assertFalse(mock_kpis.called)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_campana_id_out_of_scope_shows_error(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'campana_id': '999999',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_valid())
        self.assertIn('campana_id', response.context['form'].errors)
        self.assertFalse(mock_kpis.called)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_contact_id_is_forwarded_to_kpis(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'contacto_id': '555',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_kpis.call_args[1]['customer_id'], 555)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_contact_id_invalid_shows_error_and_does_not_call_kpis(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'contacto_id': 'abc',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_valid())
        self.assertIn('contacto_id', response.context['form'].errors)
        self.assertFalse(mock_kpis.called)

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_address_query_is_forwarded_to_kpis(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'address': '555',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_kpis.call_args[1]['address_query'], '555')

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_empty_address_query_sets_none(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'address': '',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(mock_kpis.call_args[1]['address_query'])

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_callid_is_forwarded_to_kpis(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'callid': '1234567890.123',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_kpis.call_args[1]['callid'], '1234567890.123')

    @patch('api_app.views.reports_centro_contacto.obtener_kpis_centro_contacto')
    def test_empty_callid_sets_none(self, mock_kpis):
        mock_kpis.return_value = MOCK_KPIS
        response = self._post_form(
            self.admin_user.username,
            {
                'fecha': self.fecha,
                'campana': [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
                'callid': '',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(mock_kpis.call_args[1]['callid'])


class ObtenerKpisCentroContactoTest(SimpleTestCase):

    def _empty_aggregate(self):
        return {
            'total': 0,
            'total_outbound': 0,
            'outbound_answered': 0,
            'total_inbound': 0,
            'inbound_answered': 0,
            'inbound_abandoned_gt5': 0,
            'inbound_timeout': 0,
            'attended_by_human': 0,
            'sales': 0,
            'answered_agent_gt10': 0,
            'transferred': 0,
            'bot_only': 0,
            'count_agent_gt0': 0,
            'count_asa': 0,
            'sum_agent_duration': 0,
            'sum_wait_conn_duration_asa': 0,
            'sum_bot_duration': 0,
        }

    def _q_contains_lookup(self, q_object, lookup, value):
        for child in q_object.children:
            if isinstance(child, tuple):
                if child[0] == lookup and child[1] == value:
                    return True
            elif isinstance(child, Q):
                if self._q_contains_lookup(child, lookup, value):
                    return True
        return False

    def _q_contains_lookup_key(self, q_object, lookup):
        for child in q_object.children:
            if isinstance(child, tuple):
                if child[0] == lookup:
                    return True
            elif isinstance(child, Q):
                if self._q_contains_lookup_key(child, lookup):
                    return True
        return False

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    def test_allowed_agent_filter_includes_null_and_minus_one(self, mock_interactions_summary):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.aggregate.return_value = self._empty_aggregate()
        mock_interactions_summary.objects.all.return_value = queryset

        allowed_ids = [11, 22]
        obtener_kpis_centro_contacto(
            start_date=None,
            end_date=None,
            allowed_campaigns=[1],
            allowed_agent_ids=allowed_ids,
        )

        q_filters = [
            args[0]
            for args, _ in queryset.filter.call_args_list
            if args and isinstance(args[0], Q)
        ]
        matching_filter = None
        for q_filter in q_filters:
            if (
                self._q_contains_lookup(q_filter, 'agent_id__in', allowed_ids) and
                self._q_contains_lookup(q_filter, 'agent_id__isnull', True) and
                self._q_contains_lookup(q_filter, 'agent_id', -1)
            ):
                matching_filter = q_filter
                break

        self.assertIsNotNone(
            matching_filter,
            'Debe aplicar filtro por agentes permitidos e incluir agent_id nulo y -1.',
        )

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    def test_customer_id_filter_is_applied_when_provided(self, mock_interactions_summary):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.aggregate.return_value = self._empty_aggregate()
        mock_interactions_summary.objects.all.return_value = queryset

        obtener_kpis_centro_contacto(
            start_date=None,
            end_date=None,
            allowed_campaigns=[1],
            customer_id=999,
        )

        self.assertTrue(
            any(kwargs.get('customer_id') == 999 for _, kwargs in queryset.filter.call_args_list),
            'Debe aplicar queryset.filter(customer_id=999) cuando se informa contacto_id.',
        )

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    def test_address_filter_is_applied_when_provided(self, mock_interactions_summary):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.aggregate.return_value = self._empty_aggregate()
        mock_interactions_summary.objects.all.return_value = queryset

        address_query = 'abc'
        obtener_kpis_centro_contacto(
            start_date=None,
            end_date=None,
            allowed_campaigns=[1],
            address_query=address_query,
        )

        q_filters = [
            args[0]
            for args, _ in queryset.filter.call_args_list
            if args and isinstance(args[0], Q)
        ]
        matching_filter = None
        for q_filter in q_filters:
            if (
                self._q_contains_lookup(q_filter, 'source_address__icontains', address_query) and
                self._q_contains_lookup(q_filter, 'destination_address__icontains', address_query)
            ):
                matching_filter = q_filter
                break

        self.assertIsNotNone(
            matching_filter,
            'Debe aplicar filtro por source_address/destination_address cuando se informa address.',
        )

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    def test_address_filter_is_not_applied_when_query_is_none(self, mock_interactions_summary):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.aggregate.return_value = self._empty_aggregate()
        mock_interactions_summary.objects.all.return_value = queryset

        obtener_kpis_centro_contacto(
            start_date=None,
            end_date=None,
            allowed_campaigns=[1],
            address_query=None,
        )

        q_filters = [
            args[0]
            for args, _ in queryset.filter.call_args_list
            if args and isinstance(args[0], Q)
        ]
        has_address_filter = any(
            self._q_contains_lookup_key(q_filter, 'source_address__icontains') or
            self._q_contains_lookup_key(q_filter, 'destination_address__icontains')
            for q_filter in q_filters
        )
        self.assertFalse(
            has_address_filter,
            'No debe aplicar filtro por source_address/destination_address cuando address_query es None.',
        )

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    def test_callid_filter_is_applied_when_provided(self, mock_interactions_summary):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.aggregate.return_value = self._empty_aggregate()
        mock_interactions_summary.objects.all.return_value = queryset

        obtener_kpis_centro_contacto(
            start_date=None,
            end_date=None,
            allowed_campaigns=[1],
            callid='abc-123',
        )

        self.assertTrue(
            any(kwargs.get('interaction_id') == 'abc-123' for _, kwargs in queryset.filter.call_args_list),
            'Debe aplicar queryset.filter(interaction_id=callid) cuando se informa callid.',
        )

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    def test_callid_filter_is_not_applied_when_none(self, mock_interactions_summary):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.aggregate.return_value = self._empty_aggregate()
        mock_interactions_summary.objects.all.return_value = queryset

        obtener_kpis_centro_contacto(
            start_date=None,
            end_date=None,
            allowed_campaigns=[1],
            callid=None,
        )

        self.assertFalse(
            any(
                kwargs.get('interaction_id') is not None
                for _, kwargs in queryset.filter.call_args_list
                if kwargs
            ),
            'No debe aplicar filtro por interaction_id cuando callid es None.',
        )

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    def test_duracion_bot_min_filter_is_applied_when_provided(self, mock_interactions_summary):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.aggregate.return_value = self._empty_aggregate()
        mock_interactions_summary.objects.all.return_value = queryset

        obtener_kpis_centro_contacto(
            start_date=None,
            end_date=None,
            allowed_campaigns=[1],
            duracion_bot_min=30,
        )

        filter_calls = queryset.filter.call_args_list
        self.assertTrue(
            any(
                kwargs.get('bot_duration__gte') == 30
                for _, kwargs in filter_calls
                if kwargs
            ),
            'Debe aplicar queryset.filter(bot_duration__gte=30) cuando se informa duracion_bot_min=30.',
        )


class GetOmnichannelShareDataTest(SimpleTestCase):

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    @patch('api_app.views.reports_centro_contacto.ConversacionWhatsapp')
    def test_returns_structure_with_all_keys(self, mock_wa, mock_is):
        mock_is.objects.filter.return_value.count.return_value = 0
        qs_wa = Mock()
        qs_wa.count.return_value = 0
        mock_wa.objects.conversaciones_entrantes.return_value = qs_wa

        result = get_omnichannel_share_data(start_date=None, end_date=None)

        self.assertIn('total_volume', result)
        self.assertIn('chart_data', result)
        self.assertIn('shares', result)
        self.assertEqual(result['total_volume'], 0)
        self.assertEqual(result['chart_data']['labels'], ['Voz', 'WhatsApp', 'Facebook', 'Email'])
        self.assertEqual(len(result['chart_data']['datasets']), 1)
        self.assertEqual(
            result['chart_data']['datasets'][0]['backgroundColor'],
            ['#3B82F6', '#22C55E', '#8B5CF6', '#F97316'],
        )
        self.assertEqual(
            list(result['shares'].keys()),
            ['voz', 'whatsapp', 'facebook', 'email'],
        )
        for pct in result['shares'].values():
            self.assertTrue(pct.endswith('%'))

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    @patch('api_app.views.reports_centro_contacto.ConversacionWhatsapp')
    def test_calculates_shares_and_total_volume(self, mock_wa, mock_is):
        # Voz=300, WhatsApp=800, Facebook=200, Email=200 -> total 1500
        mock_is.objects.filter.return_value.count.side_effect = [300, 200, 200]
        qs_wa = Mock()
        qs_wa.count.return_value = 800
        mock_wa.objects.conversaciones_entrantes.return_value = qs_wa

        result = get_omnichannel_share_data(start_date=None, end_date=None)

        self.assertEqual(result['total_volume'], 1500)
        self.assertEqual(result['chart_data']['datasets'][0]['data'], [300, 800, 200, 200])
        self.assertEqual(result['shares']['voz'], '20.0%')
        self.assertEqual(result['shares']['whatsapp'], '53.3%')
        self.assertEqual(result['shares']['facebook'], '13.3%')
        self.assertEqual(result['shares']['email'], '13.3%')


class ObtenerLlamadasPorCampanaTransferenciasTest(SimpleTestCase):

    @patch('api_app.views.reports_centro_contacto.Campana')
    @patch('api_app.views.reports_centro_contacto.InteractionTransfers')
    @patch('api_app.views.reports_centro_contacto.InteractionsSummary')
    def test_desdobla_transferencias_in_out_y_agrega_metricas_a_campana_destino(
            self, mock_interactions_summary, mock_interaction_transfers, mock_campana):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.annotate.return_value = queryset
        values_qs = Mock()
        annotate_qs = Mock()
        annotate_qs.order_by.return_value = [
            {
                'campaign_id': 1,
                'received': 5,
                'answered': 4,
                'unanswered': 1,
                'expired': 0,
                'abandoned': 1,
                'transferred': 1,
                'avg_wait': Decimal('8.0'),
                'avg_talk': Decimal('30.0'),
            },
        ]
        values_qs.annotate.return_value = annotate_qs
        queryset.values.return_value = values_qs
        def values_list_side_effect(*fields):
            if len(fields) >= 4:
                return [
                    ('call-1', 1, 'EXIT_ANSWERED', {}),
                    ('call-2', 3, 'EXIT_TIMEOUT', {}),
                ]
            return [('call-1', 1), ('call-2', 3)]

        queryset.values_list.side_effect = values_list_side_effect
        mock_interactions_summary.objects.all.return_value = queryset

        transfer_queryset = Mock()
        transfer_queryset.filter.return_value = transfer_queryset
        transfer_created_at = timezone.now()

        def transfer_values_list_side_effect(*fields):
            if fields == (
                'interaction_id', 'destination_campaign_id', 'created_at', 'talk_time_after',
            ):
                return [
                    ('call-1', 2, transfer_created_at, None),
                    ('call-2', 2, transfer_created_at, None),
                ]
            return [('call-1', 2), ('call-2', 2)]

        transfer_queryset.values_list.side_effect = transfer_values_list_side_effect
        mock_interaction_transfers.objects.filter.return_value = transfer_queryset

        campana_qs = Mock()
        campana_qs.values_list.return_value = [
            (1, 'Campaña Uno'),
            (2, 'Campaña Dos'),
        ]
        mock_campana.objects.filter.return_value = campana_qs

        rows = obtener_llamadas_por_campana(
            start_date=None,
            end_date=None,
            allowed_campaigns=[1, 2],
            visible_campaigns=[1, 2, 3],
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )

        rows_by_campaign = {row['campaign_id']: row for row in rows}
        self.assertEqual(rows_by_campaign[1]['transfer_in_count'], 0)
        self.assertEqual(rows_by_campaign[1]['transfer_out_count'], 1)
        self.assertEqual(rows_by_campaign[2]['received'], 0)
        self.assertEqual(rows_by_campaign[2]['effective_received'], 2)
        self.assertEqual(rows_by_campaign[2]['answered'], 0)
        self.assertEqual(rows_by_campaign[2]['expired'], 1)
        self.assertEqual(rows_by_campaign[2]['unanswered'], 1)
        self.assertEqual(rows_by_campaign[2]['pct_answered'], 0.0)
        self.assertEqual(rows_by_campaign[2]['pct_expired'], 50.0)
        self.assertEqual(rows_by_campaign[2]['transfer_in_count'], 2)
        self.assertEqual(rows_by_campaign[2]['transfer_out_count'], 0)

        transfer_kwargs = mock_interaction_transfers.objects.filter.call_args[1]
        self.assertIn('interaction_id__in', transfer_kwargs)
        from reportes_app.models import q_interaction_transfers_campaign_blind_consult
        expected_q = q_interaction_transfers_campaign_blind_consult()
        q_filter_calls = [
            call_args[0][0]
            for call_args in transfer_queryset.filter.call_args_list
            if call_args[0]
        ]
        self.assertIn(expected_q, q_filter_calls)


class GetOmnichannelShareDataViewTest(OMLBaseTest):

    def setUp(self):
        super(GetOmnichannelShareDataViewTest, self).setUp()
        self.admin_user = self.crear_administrador(username='admin_omni_share')
        self.url = reverse('api_reporte_omnichannel_share')

    def test_get_returns_200_and_json_structure(self):
        self.client.login(username=self.admin_user.username, password=PASSWORD)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('total_volume', data)
        self.assertIn('chart_data', data)
        self.assertIn('shares', data)
        self.assertIn('labels', data['chart_data'])
        self.assertIn('datasets', data['chart_data'])
        self.assertEqual(data['chart_data']['labels'], ['Voz', 'WhatsApp', 'Facebook', 'Email'])
        self.assertIn('voz', data['shares'])
        self.assertIn('whatsapp', data['shares'])
        self.assertIn('facebook', data['shares'])
        self.assertIn('email', data['shares'])

    def test_get_with_start_date_and_end_date_returns_200(self):
        self.client.login(username=self.admin_user.username, password=PASSWORD)
        response = self.client.get(
            self.url,
            {'start_date': '2025-02-28T00:00:00', 'end_date': '2025-02-28T23:59:59'},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data['total_volume'], int)
        self.assertEqual(len(data['chart_data']['datasets'][0]['data']), 4)


class AgentSegmentsTransferDurationTest(SimpleTestCase):
    """Correlación agent_segments (channel_data) con filas de transferencia."""

    def test_format_duration_mmss(self):
        self.assertEqual(_format_duration_mmss(8), '00:08')
        self.assertEqual(_format_duration_mmss(65), '01:05')
        self.assertEqual(_format_duration_mmss(3661), '1:01:01')
        self.assertEqual(_format_duration_mmss(None), '—')

    def test_correlacion_dos_transferencias_distinto_agente_destino(self):
        channel = {
            'agent_segments': [
                {'agent_id': 2, 'start_ts': '2026-04-09T10:54:45', 'talk_duration': 8.029},
                {'agent_id': 1, 'start_ts': '2026-04-09T10:54:53', 'talk_duration': 5.448},
            ],
        }
        segments = _parse_agent_segments(channel)
        t1 = MagicMock()
        t1.id = 10
        t1.destination_agent_id = 2
        t2 = MagicMock()
        t2.id = 20
        t2.destination_agent_id = 1
        transfers = [t1, t2]
        self.assertEqual(round(_segment_duration_seconds_for_transfer(t1, transfers, segments)), 8)
        self.assertEqual(round(_segment_duration_seconds_for_transfer(t2, transfers, segments)), 5)
        self.assertEqual(
            _segment_duration_display_for_transfer(t1, transfers, segments),
            '00:08',
        )
        self.assertEqual(
            _segment_duration_display_for_transfer(t2, transfers, segments),
            '00:05',
        )

    def test_primera_fila_campaign_sin_agente_destino_usa_segmento_cronologico(self):
        """Transferencia a CAMPAIGN sin destination_agent_id: duración por índice 0."""
        channel = {
            'agent_segments': [
                {'agent_id': 2, 'start_ts': '2026-04-09T10:54:45', 'talk_duration': 8.029},
                {'agent_id': 1, 'start_ts': '2026-04-09T10:54:53', 'talk_duration': 5.448},
            ],
        }
        segments = _parse_agent_segments(channel)
        t_campaign = MagicMock()
        t_campaign.id = 5
        t_campaign.destination_agent_id = None
        t_agent = MagicMock()
        t_agent.id = 99
        t_agent.destination_agent_id = 1
        transfers = [t_campaign, t_agent]
        self.assertEqual(
            round(_segment_duration_seconds_for_transfer(t_campaign, transfers, segments)),
            8,
        )
        self.assertEqual(
            round(_segment_duration_seconds_for_transfer(t_agent, transfers, segments)),
            5,
        )
        self.assertEqual(
            _segment_duration_display_for_transfer(t_campaign, transfers, segments),
            '00:08',
        )
        self.assertEqual(
            _segment_duration_display_for_transfer(t_agent, transfers, segments),
            '00:05',
        )

    def test_fallback_talk_time_after_sin_segmento(self):
        t1 = MagicMock()
        t1.id = 1
        t1.destination_agent_id = None
        t1.talk_time_after = Decimal('30')
        segments = []
        self.assertEqual(
            _segment_duration_display_for_transfer(t1, [t1], segments),
            '00:30',
        )


class CampaignAnsweringAgentFromSegmentsTest(SimpleTestCase):
    """Inferencia de agente que atiende transferencia a CAMPAIGN desde agent_segments."""

    def _channel_two_segments(self):
        return {
            'agent_segments': [
                {'agent_id': 2, 'start_ts': '2026-04-09T10:54:45', 'talk_duration': 8.029},
                {'agent_id': 1, 'start_ts': '2026-04-09T10:54:53', 'talk_duration': 5.448},
            ],
        }

    def test_campaign_ok_sin_destino_usa_segmento_siguiente(self):
        segments = _parse_agent_segments(self._channel_two_segments())
        t = MagicMock()
        t.id = 5
        t.destination_type = 'CAMPAIGN'
        t.destination_agent_id = None
        t.status = 'OK'
        transfers = [t]
        self.assertEqual(
            _campaign_answering_agent_id_from_segments(t, transfers, segments),
            1,
        )

    def test_un_solo_segmento_devuelve_none(self):
        channel = {
            'agent_segments': [
                {'agent_id': 2, 'start_ts': '2026-04-09T10:54:45', 'talk_duration': 8.029},
            ],
        }
        segments = _parse_agent_segments(channel)
        t = MagicMock()
        t.id = 5
        t.destination_type = 'CAMPAIGN'
        t.destination_agent_id = None
        t.status = 'OK'
        transfers = [t]
        self.assertIsNone(
            _campaign_answering_agent_id_from_segments(t, transfers, segments),
        )

    def test_no_campaign_no_infere(self):
        segments = _parse_agent_segments(self._channel_two_segments())
        t = MagicMock()
        t.id = 5
        t.destination_type = 'QUEUE'
        t.destination_agent_id = None
        t.status = 'OK'
        transfers = [t]
        self.assertIsNone(
            _campaign_answering_agent_id_from_segments(t, transfers, segments),
        )

    def test_status_no_ok_no_infere(self):
        segments = _parse_agent_segments(self._channel_two_segments())
        t = MagicMock()
        t.id = 5
        t.destination_type = 'CAMPAIGN'
        t.destination_agent_id = None
        t.status = 'BUSY'
        transfers = [t]
        self.assertIsNone(
            _campaign_answering_agent_id_from_segments(t, transfers, segments),
        )

    def test_con_destination_agent_id_no_infere(self):
        segments = _parse_agent_segments(self._channel_two_segments())
        t = MagicMock()
        t.id = 5
        t.destination_type = 'CAMPAIGN'
        t.destination_agent_id = 99
        t.status = 'OK'
        transfers = [t]
        self.assertIsNone(
            _campaign_answering_agent_id_from_segments(t, transfers, segments),
        )

    def test_interaction_transfer_to_dict_enriquece_etiqueta(self):
        t = MagicMock()
        t.id = 10
        t.destination_id = '3'
        t.destination_type = 'CAMPAIGN'
        t.transfer_type = 'BLIND'
        t.status = 'OK'
        t.source_agent_id = 8
        t.destination_agent_id = None
        t.destination_campaign_id = 3
        t.destination_external_endpoint = None
        t.source_channel = 'VOICE'
        t.created_at = None
        t.completed_at = None
        t.talk_time_after = None
        t.fail_reason = None
        agent_labels = {8: 'Origen', 1: 'Quien atendió campaña'}
        campaign_labels = {3: 'inbound-3'}
        row = _interaction_transfer_to_dict(
            t,
            agent_labels,
            campaign_labels,
            segment_duration_display='00:05',
            campaign_answered_agent_id=1,
        )
        self.assertIsNone(row['destination_agent_id'])
        self.assertEqual(row['destination_agent_label'], 'Quien atendió campaña')


class InteractionTransfersPorLlamadaAPIViewTest(OMLBaseTest):
    """Tests para GET api_interaction_transfers_centro_contacto."""

    def setUp(self):
        super(InteractionTransfersPorLlamadaAPIViewTest, self).setUp()
        self.admin_user = self.crear_administrador(username='admin_xfer_llamada')
        self.supervisor_profile = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.supervisor_user = self.supervisor_profile.user
        self.url = reverse('api_interaction_transfers_centro_contacto')

    def test_get_sin_interaction_id_devuelve_400(self):
        self.client.login(username=self.admin_user.username, password=PASSWORD)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)

    @patch('api_app.views.reports_centro_contacto.Campana.objects')
    @patch('api_app.views.reports_centro_contacto.AgenteProfile.objects')
    @patch('api_app.views.reports_centro_contacto.InteractionTransfers.objects')
    @patch('api_app.views.reports_centro_contacto.InteractionsSummary.objects')
    def test_get_admin_devuelve_200_y_lista(
            self, mock_summary_mgr, mock_transfer_mgr, mock_agent_mgr, mock_campana_mgr):
        summary = MagicMock()
        summary.campaign_id = 1
        summary.channel_data = {
            'agent_segments': [
                {'agent_id': 2, 'start_ts': '2026-04-09T10:54:45', 'talk_duration': 90},
            ],
        }
        qs_sum = MagicMock()
        qs_sum.first.return_value = summary
        mock_summary_mgr.filter.return_value = qs_sum

        t1 = MagicMock()
        t1.id = 10
        t1.destination_id = 'cola-a'
        t1.destination_type = 'QUEUE'
        t1.transfer_type = 'BLIND'
        t1.status = 'COMPLETED'
        t1.source_agent_id = 1
        t1.destination_agent_id = 2
        t1.destination_campaign_id = 3
        t1.destination_external_endpoint = None
        t1.source_channel = 'VOICE'
        t1.created_at = None
        t1.completed_at = None
        t1.talk_time_after = None
        t1.fail_reason = None

        qs_tr = MagicMock()
        qs_tr.order_by.return_value = [t1]
        mock_transfer_mgr.filter.return_value = qs_tr

        ap1 = MagicMock()
        ap1.id = 1
        ap1.user = MagicMock()
        ap1.user.get_full_name.return_value = 'Agente Origen'
        ap1.user.username = 'a1'
        ap2 = MagicMock()
        ap2.id = 2
        ap2.user = MagicMock()
        ap2.user.get_full_name.return_value = ''
        ap2.user.username = 'agente_dest'
        agent_qs = MagicMock()
        agent_qs.select_related.return_value = [ap1, ap2]
        mock_agent_mgr.filter.return_value = agent_qs

        camp_qs = MagicMock()
        camp_qs.values_list.return_value = [(3, 'Campaña destino test')]
        mock_campana_mgr.filter.return_value = camp_qs

        self.client.login(username=self.admin_user.username, password=PASSWORD)
        response = self.client.get(self.url, {'interaction_id': 'call-test-1'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['transfers']), 1)
        row = data['transfers'][0]
        self.assertEqual(row['destination_id'], 'cola-a')
        self.assertEqual(row['source_agent_label'], 'Agente Origen')
        self.assertEqual(row['destination_agent_label'], 'agente_dest')
        self.assertEqual(row['destination_campaign_label'], 'Campaña destino test')
        self.assertEqual(row['segment_duration'], '01:30')

    @patch('api_app.views.reports_centro_contacto.Campana.objects')
    @patch('api_app.views.reports_centro_contacto.AgenteProfile.objects')
    @patch('api_app.views.reports_centro_contacto.InteractionTransfers.objects')
    @patch('api_app.views.reports_centro_contacto.InteractionsSummary.objects')
    def test_get_admin_campaign_sin_agente_destino_etiqueta_desde_segmento(
            self, mock_summary_mgr, mock_transfer_mgr, mock_agent_mgr, mock_campana_mgr):
        summary = MagicMock()
        summary.campaign_id = 1
        summary.channel_data = {
            'agent_segments': [
                {'agent_id': 8, 'start_ts': '2026-04-09T10:54:45', 'talk_duration': 8.0},
                {'agent_id': 1, 'start_ts': '2026-04-09T10:54:53', 'talk_duration': 5.0},
            ],
        }
        qs_sum = MagicMock()
        qs_sum.first.return_value = summary
        mock_summary_mgr.filter.return_value = qs_sum

        t1 = MagicMock()
        t1.id = 10
        t1.destination_id = '3'
        t1.destination_type = 'CAMPAIGN'
        t1.transfer_type = 'BLIND'
        t1.status = 'OK'
        t1.source_agent_id = 8
        t1.destination_agent_id = None
        t1.destination_campaign_id = 3
        t1.destination_external_endpoint = None
        t1.source_channel = 'VOICE'
        t1.created_at = None
        t1.completed_at = None
        t1.talk_time_after = None
        t1.fail_reason = None

        qs_tr = MagicMock()
        qs_tr.order_by.return_value = [t1]
        mock_transfer_mgr.filter.return_value = qs_tr

        ap8 = MagicMock()
        ap8.id = 8
        ap8.user = MagicMock()
        ap8.user.get_full_name.return_value = 'Andrew Reid'
        ap8.user.username = 'a8'
        ap1 = MagicMock()
        ap1.id = 1
        ap1.user = MagicMock()
        ap1.user.get_full_name.return_value = 'Agente campaña'
        ap1.user.username = 'a1'
        agent_qs = MagicMock()
        agent_qs.select_related.return_value = [ap8, ap1]
        mock_agent_mgr.filter.return_value = agent_qs

        camp_qs = MagicMock()
        camp_qs.values_list.return_value = [(3, 'inbound-3')]
        mock_campana_mgr.filter.return_value = camp_qs

        self.client.login(username=self.admin_user.username, password=PASSWORD)
        response = self.client.get(self.url, {'interaction_id': 'call-campaign-1'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        row = data['transfers'][0]
        self.assertIsNone(row['destination_agent_id'])
        self.assertEqual(row['destination_agent_label'], 'Agente campaña')
        self.assertEqual(row['destination_campaign_label'], 'inbound-3')
        self.assertEqual(row['segment_duration'], '00:08')

    @patch('api_app.views.reports_centro_contacto.Campana.objects')
    @patch('api_app.views.reports_centro_contacto.AgenteProfile.objects')
    @patch('api_app.views.reports_centro_contacto.InteractionTransfers.objects')
    @patch('api_app.views.reports_centro_contacto.InteractionsSummary.objects')
    def test_get_supervisor_solo_grabacion_buscar_devuelve_200(
            self, mock_summary_mgr, mock_transfer_mgr, mock_agent_mgr, mock_campana_mgr):
        """Acceso desde búsqueda de grabaciones sin permiso del reporte CC."""
        summary = MagicMock()
        summary.campaign_id = 1
        summary.channel_data = {'agent_segments': []}
        qs_sum = MagicMock()
        qs_sum.first.return_value = summary
        mock_summary_mgr.filter.return_value = qs_sum

        t1 = MagicMock()
        t1.id = 11
        t1.destination_id = '5'
        t1.destination_type = 'AGENT'
        t1.transfer_type = 'BLIND'
        t1.status = 'OK'
        t1.source_agent_id = 1
        t1.destination_agent_id = 2
        t1.destination_campaign_id = None
        t1.destination_external_endpoint = None
        t1.source_channel = 'VOICE'
        t1.created_at = None
        t1.completed_at = None
        t1.talk_time_after = None
        t1.fail_reason = None

        qs_tr = MagicMock()
        qs_tr.order_by.return_value = [t1]
        mock_transfer_mgr.filter.return_value = qs_tr

        ap1 = MagicMock()
        ap1.id = 1
        ap1.user = MagicMock()
        ap1.user.get_full_name.return_value = 'A'
        ap1.user.username = 'a1'
        ap2 = MagicMock()
        ap2.id = 2
        ap2.user = MagicMock()
        ap2.user.get_full_name.return_value = 'B'
        ap2.user.username = 'b1'
        agent_qs = MagicMock()
        agent_qs.select_related.return_value = [ap1, ap2]
        mock_agent_mgr.filter.return_value = agent_qs

        camp_qs = MagicMock()
        camp_qs.values_list.return_value = []
        mock_campana_mgr.filter.return_value = camp_qs

        supervisor = MagicMock()
        campanas_qs = MagicMock()
        campanas_qs.values_list.return_value = [1, 2]
        supervisor.campanas_asignadas_actuales.return_value = campanas_qs

        def _solo_grabacion_buscar(user_self, nombre_permiso):
            return nombre_permiso == 'grabacion_buscar'

        self.client.login(username=self.supervisor_user.username, password=PASSWORD)
        with patch.object(User, 'tiene_permiso_oml', _solo_grabacion_buscar):
            with patch.object(User, 'get_is_administrador', return_value=False):
                with patch.object(User, 'get_supervisor_profile', return_value=supervisor):
                    response = self.client.get(self.url, {'interaction_id': 'call-grab-1'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['transfers']), 1)
        self.assertEqual(data['transfers'][0]['destination_id'], '5')

    @patch('api_app.views.reports_centro_contacto.InteractionsSummary.objects')
    def test_get_interaccion_inexistente_devuelve_404(self, mock_summary_mgr):
        qs = MagicMock()
        qs.first.return_value = None
        mock_summary_mgr.filter.return_value = qs
        self.client.login(username=self.admin_user.username, password=PASSWORD)
        response = self.client.get(self.url, {'interaction_id': 'no-existe'})
        self.assertEqual(response.status_code, 404)

    @patch('api_app.views.reports_centro_contacto.InteractionTransfers.objects')
    @patch('api_app.views.reports_centro_contacto.InteractionsSummary.objects')
    def test_get_supervisor_campana_no_permitida_devuelve_403(
            self, mock_summary_mgr, mock_transfer_mgr):
        summary = MagicMock()
        summary.campaign_id = 99999
        qs_sum = MagicMock()
        qs_sum.first.return_value = summary
        mock_summary_mgr.filter.return_value = qs_sum

        qs_tr = MagicMock()
        qs_tr.order_by.return_value = []
        mock_transfer_mgr.filter.return_value = qs_tr

        supervisor = MagicMock()
        campanas_qs = MagicMock()
        campanas_qs.values_list.return_value = [1, 2]
        supervisor.campanas_asignadas_actuales.return_value = campanas_qs

        self.client.login(username=self.supervisor_user.username, password=PASSWORD)
        with patch.object(
            User,
            'get_supervisor_profile',
            return_value=supervisor,
        ):
            with patch.object(User, 'get_is_administrador', return_value=False):
                response = self.client.get(self.url, {'interaction_id': 'call-x'})
        self.assertEqual(response.status_code, 403)


def _interactions_summary_table_exists():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'interactions_summary'
            """
        )
        return cursor.fetchone() is not None


def _interaction_transfers_table_exists():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'interaction_transfers'
            """
        )
        return cursor.fetchone() is not None


@unittest.skipUnless(
    _interactions_summary_table_exists() and _interaction_transfers_table_exists(),
    'Requiere tablas interactions_summary e interaction_transfers',
)
class ObtenerLlamadasPorCampanaTransferOutIntegrationTest(OMLBaseTest):
    """Transferencia a otra campaña: expirada/abandonada en origen excluidas si hay xfer out;
    EXIT_ANSWERED con xfer out cuenta como respondida en origen; en destino solo answered
    si hay evidencia de atención post-transfer (p. ej. talk_time_after o segmentos)."""

    def setUp(self):
        super(ObtenerLlamadasPorCampanaTransferOutIntegrationTest, self).setUp()
        self.crear_administrador()
        self.hoy = timezone.now()
        self.desde = self.hoy.replace(hour=0, minute=0, second=0, microsecond=0)
        self.hasta = self.desde + timedelta(days=1) - timedelta(microseconds=1)
        self.campana_origen = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
            nombre='CC xfer origen',
        )
        self.campana_destino = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
            nombre='CC xfer destino',
        )

    def test_transfer_out_timeout_origen_sin_expirada_destino_con_expirada(self):
        """Timeout final con xfer a otra campaña e is_transferred: respondida en origen; expirada en destino."""
        iid = 'cc-xfer-out-%s' % self.campana_origen.pk
        InteractionsSummary.objects.create(
            interaction_id=iid,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_TIMEOUT',
            hangup_cause='OTHER',
            start_time=self.desde + timedelta(hours=10),
            end_time=self.desde + timedelta(hours=10, seconds=30),
            wait_conn_duration=Decimal('7'),
            agent_duration=Decimal('0'),
            is_transferred=True,
        )
        InteractionTransfers.objects.create(
            interaction_id=iid,
            destination_id=str(self.campana_destino.pk),
            destination_type='CAMPAIGN',
            destination_campaign_id=self.campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
        )

        allowed = [self.campana_origen.pk, self.campana_destino.pk]
        rows = obtener_llamadas_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=allowed,
            visible_campaigns=allowed,
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )
        by_id = {r['campaign_id']: r for r in rows}
        origen = by_id[self.campana_origen.pk]
        destino = by_id[self.campana_destino.pk]

        self.assertEqual(origen['received'], 1)
        self.assertEqual(origen['answered'], 1)
        self.assertEqual(origen['expired'], 0)
        self.assertEqual(origen['abandoned'], 0)
        self.assertEqual(origen['unanswered'], 0)
        self.assertEqual(origen['pct_answered'], 100.0)
        self.assertGreaterEqual(origen.get('transfer_out_count', 0), 1)
        self.assertEqual(origen['transferred'], 1)
        self.assertEqual(origen['pct_transferred'], 100.0)

        self.assertEqual(destino['received'], 0)
        self.assertEqual(destino['effective_received'], 1)
        self.assertEqual(destino['answered'], 0)
        self.assertEqual(destino['expired'], 1)
        self.assertEqual(destino.get('transfer_in_count', 0), 1)
        self.assertEqual(destino['transferred'], 1)

    def test_transfer_out_timeout_cero_agent_duration_cuenta_respondida_si_is_transferred(self):
        """Caso real: EXIT_TIMEOUT, agent_duration 0, is_transferred y xfer a campaña -> respondida en origen."""
        iid = 'cc-xfer-out-no-agent-%s' % self.campana_origen.pk
        InteractionsSummary.objects.create(
            interaction_id=iid,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_TIMEOUT',
            hangup_cause='OTHER',
            start_time=self.desde + timedelta(hours=10, minutes=30),
            end_time=self.desde + timedelta(hours=10, minutes=31),
            wait_conn_duration=Decimal('20'),
            agent_duration=Decimal('0'),
            is_transferred=True,
        )
        InteractionTransfers.objects.create(
            interaction_id=iid,
            destination_id=str(self.campana_destino.pk),
            destination_type='CAMPAIGN',
            destination_campaign_id=self.campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
        )
        allowed = [self.campana_origen.pk, self.campana_destino.pk]
        rows = obtener_llamadas_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=allowed,
            visible_campaigns=allowed,
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )
        origen = next(r for r in rows if r['campaign_id'] == self.campana_origen.pk)
        self.assertEqual(origen['answered'], 1)

    def test_transfer_out_timeout_is_transferred_false_no_cuenta_respondida(self):
        """Xfer a otra campaña con is_transferred=False: no sumar answered en origen (sin EXIT_ANSWERED)."""
        iid = 'cc-xfer-out-not-flagged-%s' % self.campana_origen.pk
        InteractionsSummary.objects.create(
            interaction_id=iid,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_TIMEOUT',
            hangup_cause='OTHER',
            start_time=self.desde + timedelta(hours=10, minutes=45),
            end_time=self.desde + timedelta(hours=10, minutes=46),
            wait_conn_duration=Decimal('20'),
            agent_duration=Decimal('0'),
            is_transferred=False,
        )
        InteractionTransfers.objects.create(
            interaction_id=iid,
            destination_id=str(self.campana_destino.pk),
            destination_type='CAMPAIGN',
            destination_campaign_id=self.campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
        )
        allowed = [self.campana_origen.pk, self.campana_destino.pk]
        rows = obtener_llamadas_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=allowed,
            visible_campaigns=allowed,
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )
        origen = next(r for r in rows if r['campaign_id'] == self.campana_origen.pk)
        self.assertEqual(origen['answered'], 0)

    def test_transfer_out_answered_origen_respondida_destino_no_duplica_answered(self):
        """EXIT_ANSWERED con transfer a otra campaña: respondida en origen, no en destino."""
        iid = 'cc-xfer-out-answered-%s' % self.campana_origen.pk
        InteractionsSummary.objects.create(
            interaction_id=iid,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ANSWERED',
            hangup_cause='AGENT',
            start_time=self.desde + timedelta(hours=12),
            end_time=self.desde + timedelta(hours=12, minutes=2),
            wait_conn_duration=Decimal('4'),
            agent_duration=Decimal('120'),
            is_transferred=True,
        )
        InteractionTransfers.objects.create(
            interaction_id=iid,
            destination_id=str(self.campana_destino.pk),
            destination_type='CAMPAIGN',
            destination_campaign_id=self.campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
        )

        allowed = [self.campana_origen.pk, self.campana_destino.pk]
        rows = obtener_llamadas_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=allowed,
            visible_campaigns=allowed,
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )
        by_id = {r['campaign_id']: r for r in rows}
        origen = by_id[self.campana_origen.pk]
        destino = by_id[self.campana_destino.pk]

        self.assertEqual(origen['received'], 1)
        self.assertEqual(origen['answered'], 1)
        self.assertEqual(origen['pct_answered'], 100.0)

        self.assertEqual(destino['received'], 0)
        self.assertEqual(destino['effective_received'], 1)
        self.assertEqual(destino['answered'], 0)
        self.assertEqual(destino['expired'], 0)
        self.assertEqual(destino['abandoned'], 0)

    def test_transfer_out_abandon_wel_destino_cuenta_abandonada(self):
        """EXIT_ABANDON_WEL con xfer a campaña: destino debe sumar abandoned."""
        iid = 'cc-xfer-out-abandon-wel-%s' % self.campana_origen.pk
        InteractionsSummary.objects.create(
            interaction_id=iid,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ABANDON_WEL',
            hangup_cause='EXIT_ABANDON_WEL',
            start_time=self.desde + timedelta(hours=12, minutes=30),
            end_time=self.desde + timedelta(hours=12, minutes=31),
            wait_conn_duration=Decimal('5'),
            agent_duration=Decimal('0'),
            is_transferred=True,
        )
        InteractionTransfers.objects.create(
            interaction_id=iid,
            destination_id=str(self.campana_destino.pk),
            destination_type='CAMPAIGN',
            destination_campaign_id=self.campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
        )

        allowed = [self.campana_origen.pk, self.campana_destino.pk]
        rows = obtener_llamadas_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=allowed,
            visible_campaigns=allowed,
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )
        by_id = {r['campaign_id']: r for r in rows}
        origen = by_id[self.campana_origen.pk]
        destino = by_id[self.campana_destino.pk]

        self.assertEqual(origen['abandoned'], 0)
        self.assertEqual(destino['effective_received'], 1)
        self.assertEqual(destino['abandoned'], 1)

    def test_transfer_out_exit_answered_con_corte_en_cola_destino_suma_abandonada(self):
        """
        EXIT_ANSWERED global con transferencia a campaña destino y talk_time_after=0
        (sin segmento de agente posterior al transfer): destino debe sumar abandoned.
        """
        iid = 'cc-xfer-out-answered-abandon-dest-%s' % self.campana_origen.pk
        transfer_ts = self.desde + timedelta(hours=11, minutes=1, seconds=42)
        InteractionsSummary.objects.create(
            interaction_id=iid,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ANSWERED',
            hangup_cause='AGENT',
            start_time=self.desde + timedelta(hours=11, minutes=1, seconds=35),
            end_time=self.desde + timedelta(hours=11, minutes=1, seconds=48),
            wait_conn_duration=Decimal('3.343'),
            agent_duration=Decimal('6.342'),
            is_transferred=True,
            channel_data={
                'agent_segments': [
                    {
                        'agent_id': 1,
                        'start_ts': (self.desde + timedelta(hours=11, minutes=1, seconds=38)).isoformat(),
                        'end_ts': (self.desde + timedelta(hours=11, minutes=1, seconds=42)).isoformat(),
                        'talk_duration': 3.967,
                    },
                ],
            },
        )
        InteractionTransfers.objects.create(
            interaction_id=iid,
            source_agent_id=1,
            destination_id=str(self.campana_destino.pk),
            destination_type='CAMPAIGN',
            destination_campaign_id=self.campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
            created_at=transfer_ts,
            completed_at=transfer_ts,
            talk_time_after=Decimal('0.000'),
        )
        allowed = [self.campana_origen.pk, self.campana_destino.pk]
        rows = obtener_llamadas_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=allowed,
            visible_campaigns=allowed,
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )
        by_id = {r['campaign_id']: r for r in rows}
        origen = by_id[self.campana_origen.pk]
        destino = by_id[self.campana_destino.pk]

        self.assertEqual(origen['answered'], 1)
        self.assertEqual(origen['abandoned'], 0)
        self.assertEqual(destino['effective_received'], 1)
        self.assertEqual(destino['answered'], 0)
        self.assertEqual(destino['expired'], 0)
        self.assertEqual(destino['unanswered'], 1)
        self.assertEqual(destino['abandoned'], 1)

    def test_transfer_out_exit_answered_con_talk_post_transfer_no_suma_abandonada(self):
        """
        No-regresión: si hay conversación efectiva post-transfer (talk_time_after>0),
        no debe inferirse abandono en campaña destino.
        """
        iid = 'cc-xfer-out-answered-talk-post-%s' % self.campana_origen.pk
        transfer_ts = self.desde + timedelta(hours=12, minutes=15, seconds=10)
        InteractionsSummary.objects.create(
            interaction_id=iid,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ANSWERED',
            hangup_cause='AGENT',
            start_time=self.desde + timedelta(hours=12, minutes=15),
            end_time=self.desde + timedelta(hours=12, minutes=16),
            wait_conn_duration=Decimal('2'),
            agent_duration=Decimal('20'),
            is_transferred=True,
            channel_data={
                'agent_segments': [
                    {
                        'agent_id': 1,
                        'start_ts': (self.desde + timedelta(hours=12, minutes=15, seconds=3)).isoformat(),
                        'end_ts': (self.desde + timedelta(hours=12, minutes=15, seconds=9)).isoformat(),
                        'talk_duration': 6.0,
                    },
                    {
                        'agent_id': 2,
                        'start_ts': (self.desde + timedelta(hours=12, minutes=15, seconds=12)).isoformat(),
                        'end_ts': (self.desde + timedelta(hours=12, minutes=15, seconds=30)).isoformat(),
                        'talk_duration': 18.0,
                    },
                ],
            },
        )
        InteractionTransfers.objects.create(
            interaction_id=iid,
            source_agent_id=1,
            destination_id=str(self.campana_destino.pk),
            destination_type='CAMPAIGN',
            destination_campaign_id=self.campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
            created_at=transfer_ts,
            completed_at=transfer_ts,
            talk_time_after=Decimal('18.000'),
        )
        allowed = [self.campana_origen.pk, self.campana_destino.pk]
        rows = obtener_llamadas_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=allowed,
            visible_campaigns=allowed,
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )
        by_id = {r['campaign_id']: r for r in rows}
        destino = by_id[self.campana_destino.pk]

        self.assertEqual(destino['effective_received'], 1)
        self.assertEqual(destino['answered'], 1)
        self.assertEqual(destino['unanswered'], 0)
        self.assertEqual(destino['abandoned'], 0)

    def test_transfer_out_exit_answered_segment_start_antes_transfer_cuenta_atendida_destino(self):
        """
        start_ts del agente destino puede ir unos ms antes que created_at de la transferencia;
        debe contar como atendida en destino y no como abandonada (ACD no modificado).
        """
        iid = 'cc-xfer-out-skew-%s' % self.campana_origen.pk
        transfer_ts = self.desde + timedelta(hours=13, minutes=5, seconds=10, microseconds=15637)
        seg2_start = transfer_ts - timedelta(microseconds=2599)
        InteractionsSummary.objects.create(
            interaction_id=iid,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ANSWERED',
            hangup_cause='AGENT',
            start_time=self.desde + timedelta(hours=13, minutes=5),
            end_time=self.desde + timedelta(hours=13, minutes=6),
            wait_conn_duration=Decimal('3'),
            agent_duration=Decimal('26'),
            is_transferred=True,
            channel_data={
                'agent_segments': [
                    {
                        'agent_id': 1,
                        'start_ts': (self.desde + timedelta(hours=13, minutes=5, seconds=2)).isoformat(),
                        'end_ts': (self.desde + timedelta(hours=13, minutes=5, seconds=10)).isoformat(),
                        'talk_duration': 8.0,
                    },
                    {
                        'agent_id': 5,
                        'start_ts': seg2_start.isoformat(),
                        'end_ts': (self.desde + timedelta(hours=13, minutes=5, seconds=40)).isoformat(),
                        'talk_duration': 17.072,
                    },
                ],
            },
        )
        InteractionTransfers.objects.create(
            interaction_id=iid,
            source_agent_id=1,
            destination_id=str(self.campana_destino.pk),
            destination_type='CAMPAIGN',
            destination_campaign_id=self.campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
            created_at=transfer_ts,
            completed_at=transfer_ts,
            talk_time_after=Decimal('0.000'),
        )
        allowed = [self.campana_origen.pk, self.campana_destino.pk]
        rows = obtener_llamadas_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=allowed,
            visible_campaigns=allowed,
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )
        by_id = {r['campaign_id']: r for r in rows}
        destino = by_id[self.campana_destino.pk]

        self.assertEqual(destino['effective_received'], 1)
        self.assertEqual(destino['answered'], 1)
        self.assertEqual(destino['unanswered'], 0)
        self.assertEqual(destino['abandoned'], 0)
        self.assertEqual(destino['expired'], 0)

    def test_transfer_agent_attended_no_suma_transferred_ni_transfer_columns(self):
        """Transfer a agente (ATTENDED): is_transferred no debe inflar transferred ni Transfer In/Out."""
        iid = 'cc-xfer-agent-%s' % self.campana_origen.pk
        InteractionsSummary.objects.create(
            interaction_id=iid,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ANSWERED',
            hangup_cause='AGENT',
            start_time=self.desde + timedelta(hours=11),
            end_time=self.desde + timedelta(hours=11, minutes=1),
            wait_conn_duration=Decimal('3'),
            agent_duration=Decimal('10'),
            is_transferred=True,
        )
        InteractionTransfers.objects.create(
            interaction_id=iid,
            destination_id='1',
            destination_type='AGENT',
            destination_agent_id=1,
            transfer_type='ATTENDED',
            status='OK',
        )
        allowed = [self.campana_origen.pk]
        rows = obtener_llamadas_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=allowed,
            visible_campaigns=allowed,
            direction_filter='INBOUND',
            channel_filter='VOICE',
        )
        row = next(r for r in rows if r['campaign_id'] == self.campana_origen.pk)
        self.assertEqual(row['answered'], 1)
        self.assertEqual(row['transferred'], 0)
        self.assertEqual(row.get('transfer_in_count', 0), 0)
        self.assertEqual(row.get('transfer_out_count', 0), 0)
        self.assertEqual(row['pct_transferred'], 0.0)


@unittest.skipUnless(
    _interactions_summary_table_exists(),
    'Requiere tabla interactions_summary',
)
class ObtenerLlamadasSalientesPorCampanaTest(OMLBaseTest):
    """Métricas de egresos voz por campaña: contactadas PSTN, % Ag, % No Conectadas, % Transferencias."""

    def setUp(self):
        super(ObtenerLlamadasSalientesPorCampanaTest, self).setUp()
        self.crear_administrador()
        self.hoy = timezone.now()
        self.desde = self.hoy.replace(hour=0, minute=0, second=0, microsecond=0)
        self.hasta = self.desde + timedelta(days=1) - timedelta(microseconds=1)
        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_DIALER,
            nombre='CC outbound metrics',
        )
        self._seq = 0

    def _create_outbound(self, status, agent_id=1, is_transferred=False,
                         agent_duration=Decimal('10'), total_duration=Decimal('15')):
        self._seq += 1
        return InteractionsSummary.objects.create(
            interaction_id='ob-camp-%s-%s' % (self.campana.pk, self._seq),
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana.pk,
            channel_type='VOICE',
            direction='OUTBOUND',
            status=status,
            hangup_cause='OTHER',
            start_time=self.desde + timedelta(hours=10, minutes=self._seq),
            end_time=self.desde + timedelta(hours=10, minutes=self._seq, seconds=30),
            wait_conn_duration=Decimal('3'),
            agent_duration=agent_duration,
            total_duration=total_duration,
            bot_duration=Decimal('0'),
            agent_id=agent_id,
            is_transferred=is_transferred,
        )

    def test_metricas_contactadas_pstn_y_porcentajes(self):
        # 7 contactadas PSTN (1 de cada status) + 3 no contactadas
        self._create_outbound('EXIT_ANSWERED', is_transferred=True)
        self._create_outbound('EXIT_AMD', agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_SHORTCALL', agent_duration=Decimal('2'))
        self._create_outbound('EXIT_ABANDON', agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_TIMEOUT', agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_HANDOFF_ABANDON', agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_HANDOFF_TIMEOUT', agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('NOANSWER', agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))
        self._create_outbound('BUSY', agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))
        self._create_outbound('CANCEL', agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))

        rows = obtener_llamadas_salientes_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]

        self.assertEqual(row['sent'], 10)
        self.assertEqual(row['conectadas'], 1)
        self.assertEqual(row['contactadas_pstn'], 7)
        self.assertEqual(row['transferred'], 1)
        self.assertEqual(row['pct_conectadas_pstn'], 70.0)
        self.assertEqual(row['pct_conectadas_ag'], round(100.0 * 1 / 7, 2))
        self.assertEqual(row['pct_contestador'], round(100.0 * 1 / 7, 2))
        self.assertEqual(row['pct_shortcall'], round(100.0 * 1 / 7, 2))
        self.assertEqual(row['pct_no_conectadas'], 30.0)
        self.assertEqual(row['pct_transferencias'], 100.0)
        # Claves legacy conservadas para gráfico / tarjetas resumen
        self.assertEqual(row['pct_conectadas'], 10.0)
        self.assertIn('canceladas', row)
        self.assertIn('contestador', row)

        self.assertEqual(row['abandonadas_espera'], 2)
        self.assertEqual(row['timeout_espera'], 2)
        self.assertEqual(row['error_contactacion'], 1)
        self.assertEqual(row['pct_dist_conectadas_ag'], 10.0)
        self.assertEqual(row['pct_dist_abandonadas_espera'], 20.0)
        self.assertEqual(row['pct_dist_timeout_espera'], 20.0)
        self.assertEqual(row['pct_dist_shortcall'], 10.0)
        self.assertEqual(row['pct_dist_contestador'], 10.0)
        self.assertEqual(row['pct_dist_ocupado'], 10.0)
        self.assertEqual(row['pct_dist_cancel'], 10.0)
        self.assertEqual(row['pct_dist_error_contactacion'], 10.0)
        suma_categorias = (
            row['conectadas'] + row['abandonadas_espera'] + row['timeout_espera']
            + row['shortcall'] + row['contestador'] + row['ocupado'] + row['canceladas']
            + row['error_contactacion']
        )
        self.assertEqual(suma_categorias, row['sent'])

    def test_division_por_cero_sin_contactadas_pstn(self):
        self._create_outbound('NOANSWER', agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))
        self._create_outbound('BUSY', agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))

        rows = obtener_llamadas_salientes_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
        )
        row = rows[0]
        self.assertEqual(row['sent'], 2)
        self.assertEqual(row['contactadas_pstn'], 0)
        self.assertEqual(row['conectadas'], 0)
        self.assertEqual(row['pct_conectadas_pstn'], 0.0)
        self.assertEqual(row['pct_conectadas_ag'], 0.0)
        self.assertEqual(row['pct_contestador'], 0.0)
        self.assertEqual(row['pct_shortcall'], 0.0)
        self.assertEqual(row['pct_no_conectadas'], 100.0)
        self.assertEqual(row['pct_transferencias'], 0.0)

    def test_pct_transferencias_cero_si_no_hay_exit_answered(self):
        self._create_outbound('EXIT_AMD', agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_ABANDON', agent_id=-1, agent_duration=Decimal('0'))

        rows = obtener_llamadas_salientes_por_campana(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
        )
        row = rows[0]
        self.assertEqual(row['conectadas'], 0)
        self.assertEqual(row['contactadas_pstn'], 2)
        self.assertEqual(row['pct_conectadas_ag'], 0.0)
        self.assertEqual(row['pct_contestador'], 50.0)
        self.assertEqual(row['pct_shortcall'], 0.0)
        self.assertEqual(row['pct_transferencias'], 0.0)
        self.assertEqual(row['pct_conectadas_pstn'], 100.0)
        self.assertEqual(row['pct_no_conectadas'], 0.0)


@unittest.skipUnless(
    _interactions_summary_table_exists(),
    'Requiere tabla interactions_summary',
)
class ObtenerLlamadasSalientesPorHoraTest(OMLBaseTest):
    """Métricas de egresos voz por hora: contactadas PSTN y porcentajes."""

    def setUp(self):
        super(ObtenerLlamadasSalientesPorHoraTest, self).setUp()
        self.crear_administrador()
        self.hoy = timezone.now()
        self.desde = self.hoy.replace(hour=0, minute=0, second=0, microsecond=0)
        self.hasta = self.desde + timedelta(days=1) - timedelta(microseconds=1)
        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_DIALER,
            nombre='CC outbound hora',
        )
        self._seq = 0

    def _create_outbound(self, status, hour, agent_id=1, is_transferred=False,
                         agent_duration=Decimal('10'), total_duration=Decimal('15')):
        self._seq += 1
        start = self.desde.replace(hour=hour, minute=self._seq % 59, second=0, microsecond=0)
        return InteractionsSummary.objects.create(
            interaction_id='ob-hora-%s-%s' % (self.campana.pk, self._seq),
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana.pk,
            channel_type='VOICE',
            direction='OUTBOUND',
            status=status,
            hangup_cause='OTHER',
            start_time=start,
            end_time=start + timedelta(seconds=30),
            wait_conn_duration=Decimal('3'),
            agent_duration=agent_duration,
            total_duration=total_duration,
            bot_duration=Decimal('0'),
            agent_id=agent_id,
            is_transferred=is_transferred,
        )

    def test_metricas_por_hora(self):
        self._create_outbound('EXIT_ANSWERED', hour=10, is_transferred=True)
        self._create_outbound('EXIT_AMD', hour=10, agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_SHORTCALL', hour=10, agent_duration=Decimal('2'))
        self._create_outbound('EXIT_ABANDON', hour=10, agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_TIMEOUT', hour=10, agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('NOANSWER', hour=10, agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))
        self._create_outbound('BUSY', hour=11, agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))
        self._create_outbound('CANCEL', hour=11, agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))

        rows = obtener_llamadas_salientes_por_hora(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
        )
        self.assertEqual(len(rows), 24)
        by_hour = {r['hour']: r for r in rows}

        h10 = by_hour[10]
        self.assertEqual(h10['sent'], 6)
        self.assertEqual(h10['conectadas'], 1)
        self.assertEqual(h10['contactadas_pstn'], 5)
        self.assertEqual(h10['pct_conectadas_pstn'], round(100.0 * 5 / 6, 2))
        self.assertEqual(h10['pct_conectadas_ag'], round(100.0 * 1 / 5, 2))
        self.assertEqual(h10['pct_contestador'], round(100.0 * 1 / 5, 2))
        self.assertEqual(h10['pct_shortcall'], round(100.0 * 1 / 5, 2))
        self.assertEqual(h10['pct_no_conectadas'], round(100.0 * 1 / 6, 2))
        self.assertEqual(h10['pct_transferencias'], 100.0)
        self.assertEqual(h10['abandonadas_espera'], 1)
        self.assertEqual(h10['timeout_espera'], 1)
        self.assertEqual(h10['error_contactacion'], 1)
        self.assertEqual(h10['pct_dist_conectadas_ag'], round(100.0 * 1 / 6, 2))
        self.assertEqual(h10['pct_dist_abandonadas_espera'], round(100.0 * 1 / 6, 2))
        self.assertEqual(h10['pct_dist_timeout_espera'], round(100.0 * 1 / 6, 2))
        self.assertEqual(h10['pct_dist_shortcall'], round(100.0 * 1 / 6, 2))
        self.assertEqual(h10['pct_dist_contestador'], round(100.0 * 1 / 6, 2))
        self.assertEqual(h10['pct_dist_error_contactacion'], round(100.0 * 1 / 6, 2))
        suma_h10 = (
            h10['conectadas'] + h10['abandonadas_espera'] + h10['timeout_espera']
            + h10['shortcall'] + h10['contestador'] + h10['ocupado'] + h10['canceladas']
            + h10['error_contactacion']
        )
        self.assertEqual(suma_h10, h10['sent'])

        h11 = by_hour[11]
        self.assertEqual(h11['sent'], 2)
        self.assertEqual(h11['contactadas_pstn'], 0)
        self.assertEqual(h11['pct_conectadas_pstn'], 0.0)
        self.assertEqual(h11['pct_contestador'], 0.0)
        self.assertEqual(h11['pct_shortcall'], 0.0)
        self.assertEqual(h11['pct_no_conectadas'], 100.0)
        self.assertEqual(h11['pct_dist_ocupado'], 50.0)
        self.assertEqual(h11['pct_dist_cancel'], 50.0)
        self.assertEqual(h11['pct_dist_error_contactacion'], 0.0)

        h0 = by_hour[0]
        self.assertEqual(h0['sent'], 0)
        self.assertEqual(h0['pct_conectadas_pstn'], 0.0)
        self.assertEqual(h0['pct_transferencias'], 0.0)
        self.assertEqual(h0['pct_dist_conectadas_ag'], 0.0)
        self.assertEqual(h0['pct_dist_error_contactacion'], 0.0)


@unittest.skipUnless(
    _interactions_summary_table_exists(),
    'Requiere tabla interactions_summary',
)
class ObtenerLlamadasSalientesPorDiaTest(OMLBaseTest):
    """Métricas de egresos voz por día: contactadas PSTN y porcentajes."""

    def setUp(self):
        super(ObtenerLlamadasSalientesPorDiaTest, self).setUp()
        self.crear_administrador()
        self.hoy = timezone.now()
        self.desde = self.hoy.replace(hour=0, minute=0, second=0, microsecond=0)
        self.hasta = self.desde + timedelta(days=2, hours=23, minutes=59, seconds=59)
        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_DIALER,
            nombre='CC outbound dia',
        )
        self._seq = 0

    def _create_outbound(self, status, day_offset, agent_id=1, is_transferred=False,
                         agent_duration=Decimal('10'), total_duration=Decimal('15')):
        self._seq += 1
        start = self.desde + timedelta(days=day_offset, minutes=self._seq % 59)
        return InteractionsSummary.objects.create(
            interaction_id='ob-dia-%s-%s' % (self.campana.pk, self._seq),
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana.pk,
            channel_type='VOICE',
            direction='OUTBOUND',
            status=status,
            hangup_cause='OTHER',
            start_time=start,
            end_time=start + timedelta(seconds=30),
            wait_conn_duration=Decimal('3'),
            agent_duration=agent_duration,
            total_duration=total_duration,
            bot_duration=Decimal('0'),
            agent_id=agent_id,
            is_transferred=is_transferred,
        )

    def test_metricas_por_dia(self):
        self._create_outbound('EXIT_ANSWERED', day_offset=1, is_transferred=True)
        self._create_outbound('EXIT_AMD', day_offset=1, agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_SHORTCALL', day_offset=1, agent_duration=Decimal('2'))
        self._create_outbound('EXIT_ABANDON', day_offset=1, agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_TIMEOUT', day_offset=1, agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('NOANSWER', day_offset=1, agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))
        self._create_outbound('BUSY', day_offset=2, agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))
        self._create_outbound('CANCEL', day_offset=2, agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'))

        rows = obtener_llamadas_salientes_por_dia(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
        )
        self.assertEqual(len(rows), 3)
        by_date = {r['date']: r for r in rows}

        dia0 = self.desde.date()
        dia1 = dia0 + timedelta(days=1)
        dia2 = dia0 + timedelta(days=2)

        d0 = by_date[dia0]
        self.assertEqual(d0['sent'], 0)
        self.assertEqual(d0['contactadas_pstn'], 0)
        self.assertEqual(d0['pct_conectadas_pstn'], 0.0)
        self.assertEqual(d0['pct_dist_conectadas_ag'], 0.0)
        self.assertEqual(d0['pct_dist_error_contactacion'], 0.0)

        d1 = by_date[dia1]
        self.assertEqual(d1['sent'], 6)
        self.assertEqual(d1['conectadas'], 1)
        self.assertEqual(d1['contactadas_pstn'], 5)
        self.assertEqual(d1['pct_conectadas_pstn'], round(100.0 * 5 / 6, 2))
        self.assertEqual(d1['pct_conectadas_ag'], round(100.0 * 1 / 5, 2))
        self.assertEqual(d1['pct_contestador'], round(100.0 * 1 / 5, 2))
        self.assertEqual(d1['pct_shortcall'], round(100.0 * 1 / 5, 2))
        self.assertEqual(d1['pct_no_conectadas'], round(100.0 * 1 / 6, 2))
        self.assertEqual(d1['pct_transferencias'], 100.0)
        self.assertEqual(d1['abandonadas_espera'], 1)
        self.assertEqual(d1['timeout_espera'], 1)
        self.assertEqual(d1['error_contactacion'], 1)
        self.assertEqual(d1['pct_dist_conectadas_ag'], round(100.0 * 1 / 6, 2))
        self.assertEqual(d1['pct_dist_abandonadas_espera'], round(100.0 * 1 / 6, 2))
        self.assertEqual(d1['pct_dist_timeout_espera'], round(100.0 * 1 / 6, 2))
        self.assertEqual(d1['pct_dist_shortcall'], round(100.0 * 1 / 6, 2))
        self.assertEqual(d1['pct_dist_contestador'], round(100.0 * 1 / 6, 2))
        self.assertEqual(d1['pct_dist_error_contactacion'], round(100.0 * 1 / 6, 2))
        suma_d1 = (
            d1['conectadas'] + d1['abandonadas_espera'] + d1['timeout_espera']
            + d1['shortcall'] + d1['contestador'] + d1['ocupado'] + d1['canceladas']
            + d1['error_contactacion']
        )
        self.assertEqual(suma_d1, d1['sent'])

        d2 = by_date[dia2]
        self.assertEqual(d2['sent'], 2)
        self.assertEqual(d2['contactadas_pstn'], 0)
        self.assertEqual(d2['pct_contestador'], 0.0)
        self.assertEqual(d2['pct_shortcall'], 0.0)
        self.assertEqual(d2['pct_no_conectadas'], 100.0)
        self.assertEqual(d2['pct_dist_ocupado'], 50.0)
        self.assertEqual(d2['pct_dist_cancel'], 50.0)
        self.assertEqual(d2['pct_dist_error_contactacion'], 0.0)


@unittest.skipUnless(
    _interactions_summary_table_exists(),
    'Requiere tabla interactions_summary',
)
class ObtenerLlamadasSalientesPorMesTest(OMLBaseTest):
    """Métricas de egresos voz por mes: contactadas PSTN y porcentajes."""

    def setUp(self):
        super(ObtenerLlamadasSalientesPorMesTest, self).setUp()
        self.crear_administrador()
        self.desde = timezone.make_aware(datetime(2025, 1, 15, 0, 0, 0))
        self.hasta = timezone.make_aware(datetime(2025, 3, 15, 23, 59, 59))
        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_DIALER,
            nombre='CC outbound mes',
        )
        self._seq = 0

    def _create_outbound(self, status, year, month, day, agent_id=1, is_transferred=False,
                         agent_duration=Decimal('10'), total_duration=Decimal('15')):
        self._seq += 1
        start = timezone.make_aware(
            datetime(year, month, day, 10, self._seq % 59, 0)
        )
        return InteractionsSummary.objects.create(
            interaction_id='ob-mes-%s-%s' % (self.campana.pk, self._seq),
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana.pk,
            channel_type='VOICE',
            direction='OUTBOUND',
            status=status,
            hangup_cause='OTHER',
            start_time=start,
            end_time=start + timedelta(seconds=30),
            wait_conn_duration=Decimal('3'),
            agent_duration=agent_duration,
            total_duration=total_duration,
            bot_duration=Decimal('0'),
            agent_id=agent_id,
            is_transferred=is_transferred,
        )

    def test_metricas_por_mes(self):
        self._create_outbound('EXIT_ANSWERED', 2025, 2, 10, is_transferred=True)
        self._create_outbound('EXIT_AMD', 2025, 2, 11, agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_SHORTCALL', 2025, 2, 12, agent_duration=Decimal('2'))
        self._create_outbound('EXIT_ABANDON', 2025, 2, 13, agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound('EXIT_TIMEOUT', 2025, 2, 14, agent_id=-1, agent_duration=Decimal('0'))
        self._create_outbound(
            'NOANSWER', 2025, 2, 15, agent_id=-1,
            agent_duration=Decimal('0'), total_duration=Decimal('0'),
        )
        self._create_outbound(
            'BUSY', 2025, 3, 5, agent_id=-1,
            agent_duration=Decimal('0'), total_duration=Decimal('0'),
        )
        self._create_outbound(
            'CANCEL', 2025, 3, 6, agent_id=-1,
            agent_duration=Decimal('0'), total_duration=Decimal('0'),
        )

        rows = obtener_llamadas_salientes_por_mes(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
        )
        self.assertEqual(len(rows), 3)
        by_month = {r['month']: r for r in rows}

        mes_enero = datetime(2025, 1, 1).date()
        mes_febrero = datetime(2025, 2, 1).date()
        mes_marzo = datetime(2025, 3, 1).date()

        m0 = by_month[mes_enero]
        self.assertEqual(m0['sent'], 0)
        self.assertEqual(m0['contactadas_pstn'], 0)
        self.assertEqual(m0['pct_conectadas_pstn'], 0.0)
        self.assertEqual(m0['pct_dist_conectadas_ag'], 0.0)
        self.assertEqual(m0['pct_dist_error_contactacion'], 0.0)

        m1 = by_month[mes_febrero]
        self.assertEqual(m1['sent'], 6)
        self.assertEqual(m1['conectadas'], 1)
        self.assertEqual(m1['contactadas_pstn'], 5)
        self.assertEqual(m1['pct_conectadas_pstn'], round(100.0 * 5 / 6, 2))
        self.assertEqual(m1['pct_conectadas_ag'], round(100.0 * 1 / 5, 2))
        self.assertEqual(m1['pct_contestador'], round(100.0 * 1 / 5, 2))
        self.assertEqual(m1['pct_shortcall'], round(100.0 * 1 / 5, 2))
        self.assertEqual(m1['pct_no_conectadas'], round(100.0 * 1 / 6, 2))
        self.assertEqual(m1['pct_transferencias'], 100.0)
        self.assertEqual(m1['abandonadas_espera'], 1)
        self.assertEqual(m1['timeout_espera'], 1)
        self.assertEqual(m1['error_contactacion'], 1)
        self.assertEqual(m1['pct_dist_conectadas_ag'], round(100.0 * 1 / 6, 2))
        self.assertEqual(m1['pct_dist_abandonadas_espera'], round(100.0 * 1 / 6, 2))
        self.assertEqual(m1['pct_dist_timeout_espera'], round(100.0 * 1 / 6, 2))
        self.assertEqual(m1['pct_dist_shortcall'], round(100.0 * 1 / 6, 2))
        self.assertEqual(m1['pct_dist_contestador'], round(100.0 * 1 / 6, 2))
        self.assertEqual(m1['pct_dist_error_contactacion'], round(100.0 * 1 / 6, 2))
        suma_m1 = (
            m1['conectadas'] + m1['abandonadas_espera'] + m1['timeout_espera']
            + m1['shortcall'] + m1['contestador'] + m1['ocupado'] + m1['canceladas']
            + m1['error_contactacion']
        )
        self.assertEqual(suma_m1, m1['sent'])

        m2 = by_month[mes_marzo]
        self.assertEqual(m2['sent'], 2)
        self.assertEqual(m2['contactadas_pstn'], 0)
        self.assertEqual(m2['pct_contestador'], 0.0)
        self.assertEqual(m2['pct_shortcall'], 0.0)
        self.assertEqual(m2['pct_no_conectadas'], 100.0)
        self.assertEqual(m2['pct_dist_ocupado'], 50.0)
        self.assertEqual(m2['pct_dist_cancel'], 50.0)
        self.assertEqual(m2['pct_dist_error_contactacion'], 0.0)


@unittest.skipUnless(
    _interactions_summary_table_exists(),
    'Requiere tabla interactions_summary',
)
class ListadoLlamadasEgresosClasificacionTest(OMLBaseTest):
    """EXIT_AMD y EXIT_SHORTCALL en egresos van a no atendidas, no a atendidas."""

    def setUp(self):
        super(ListadoLlamadasEgresosClasificacionTest, self).setUp()
        self.crear_administrador()
        self.hoy = timezone.now()
        self.desde = self.hoy.replace(hour=0, minute=0, second=0, microsecond=0)
        self.hasta = self.desde + timedelta(days=1) - timedelta(microseconds=1)
        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_DIALER,
            nombre='CC listado egresos',
        )
        self._seq = 0

    def _create_voice(self, status, direction='OUTBOUND', agent_id=1,
                      agent_duration=Decimal('10'), total_duration=Decimal('15')):
        self._seq += 1
        start = self.desde + timedelta(minutes=self._seq)
        return InteractionsSummary.objects.create(
            interaction_id='list-eg-%s-%s' % (direction.lower(), self._seq),
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana.pk,
            channel_type='VOICE',
            direction=direction,
            status=status,
            hangup_cause='OTHER',
            start_time=start,
            end_time=start + timedelta(seconds=30),
            wait_conn_duration=Decimal('3'),
            agent_duration=agent_duration,
            total_duration=total_duration,
            bot_duration=Decimal('0'),
            agent_id=agent_id,
            is_transferred=False,
        )

    def _count_in_listado(self, fn, interaction_id, direction_filter):
        page = fn(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
            direction_filter=direction_filter,
            callid=interaction_id,
            page_size=100,
        )
        return len(page.object_list)

    def test_amd_y_shortcall_en_no_atendidas_egresos(self):
        amd = self._create_voice('EXIT_AMD', agent_id=-1, agent_duration=Decimal('0'))
        shortcall = self._create_voice('EXIT_SHORTCALL', agent_duration=Decimal('2'))
        noanswer = self._create_voice(
            'NOANSWER', agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'),
        )

        self.assertEqual(
            self._count_in_listado(
                obtener_listado_llamadas_atendidas, amd.interaction_id, 'OUTBOUND',
            ),
            0,
        )
        self.assertEqual(
            self._count_in_listado(
                obtener_listado_llamadas_atendidas, shortcall.interaction_id, 'OUTBOUND',
            ),
            0,
        )
        self.assertEqual(
            self._count_in_listado(
                obtener_listado_llamadas_no_atendidas, amd.interaction_id, 'OUTBOUND',
            ),
            1,
        )
        amd_page = obtener_listado_llamadas_no_atendidas(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
            direction_filter='OUTBOUND',
            callid=amd.interaction_id,
            page_size=100,
        )
        self.assertEqual(amd_page.object_list[0]['status'], 'EXIT_AMD')
        self.assertEqual(
            self._count_in_listado(
                obtener_listado_llamadas_no_atendidas, shortcall.interaction_id, 'OUTBOUND',
            ),
            1,
        )
        self.assertEqual(
            self._count_in_listado(
                obtener_listado_llamadas_no_atendidas, noanswer.interaction_id, 'OUTBOUND',
            ),
            1,
        )
        self.assertEqual(
            self._count_in_listado(
                obtener_listado_llamadas_atendidas, noanswer.interaction_id, 'OUTBOUND',
            ),
            0,
        )

    def test_listados_incluyen_interaction_id(self):
        answered = self._create_voice('EXIT_ANSWERED')
        noanswer = self._create_voice(
            'NOANSWER', agent_id=-1, agent_duration=Decimal('0'), total_duration=Decimal('0'),
        )

        atendidas = obtener_listado_llamadas_atendidas(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
            direction_filter='OUTBOUND',
            callid=answered.interaction_id,
            page_size=100,
        )
        self.assertEqual(len(atendidas.object_list), 1)
        self.assertEqual(atendidas.object_list[0]['interaction_id'], answered.interaction_id)

        no_atendidas = obtener_listado_llamadas_no_atendidas(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
            direction_filter='OUTBOUND',
            callid=noanswer.interaction_id,
            page_size=100,
        )
        self.assertEqual(len(no_atendidas.object_list), 1)
        self.assertEqual(no_atendidas.object_list[0]['interaction_id'], noanswer.interaction_id)

    def test_amd_inbound_sigue_en_no_atendidas(self):
        amd_in = self._create_voice(
            'EXIT_AMD', direction='INBOUND', agent_id=-1, agent_duration=Decimal('0'),
        )

        self.assertEqual(
            self._count_in_listado(
                obtener_listado_llamadas_atendidas, amd_in.interaction_id, 'INBOUND',
            ),
            0,
        )
        self.assertEqual(
            self._count_in_listado(
                obtener_listado_llamadas_no_atendidas, amd_in.interaction_id, 'INBOUND',
            ),
            1,
        )


@unittest.skipUnless(
    _interactions_summary_table_exists(),
    'Requiere tabla interactions_summary',
)
class DistribucionStatusLlamadasNoAtendidasEgresosTest(OMLBaseTest):
    """Gráfico de torta: distribución por status en llamadas no atendidas (egresos voz)."""

    def setUp(self):
        super(DistribucionStatusLlamadasNoAtendidasEgresosTest, self).setUp()
        self.crear_administrador()
        self.hoy = timezone.now()
        self.desde = self.hoy.replace(hour=0, minute=0, second=0, microsecond=0)
        self.hasta = self.desde + timedelta(days=1) - timedelta(microseconds=1)
        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_DIALER,
            nombre='CC status pie egresos',
        )
        self._seq = 0

    def _create_voice(self, status, direction='OUTBOUND', agent_id=-1,
                      agent_duration=Decimal('0'), total_duration=Decimal('0')):
        self._seq += 1
        start = self.desde + timedelta(minutes=self._seq)
        return InteractionsSummary.objects.create(
            interaction_id='status-pie-eg-%s' % self._seq,
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana.pk,
            channel_type='VOICE',
            direction=direction,
            status=status,
            hangup_cause='OTHER',
            start_time=start,
            end_time=start + timedelta(seconds=30),
            wait_conn_duration=Decimal('3'),
            agent_duration=agent_duration,
            total_duration=total_duration,
            bot_duration=Decimal('0'),
            agent_id=agent_id,
            is_transferred=False,
        )

    def _get_chart(self):
        return obtener_distribucion_status_llamadas_no_atendidas(
            start_date=self.desde,
            end_date=self.hasta,
            allowed_campaigns=[self.campana.pk],
            direction_filter='OUTBOUND',
        )

    def test_distribucion_status_con_porcentajes(self):
        self._create_voice('NOANSWER')
        self._create_voice('NOANSWER')
        self._create_voice('BUSY')
        self._create_voice('EXIT_AMD')
        self._create_voice('EXIT_ANSWERED', agent_id=1, agent_duration=Decimal('10'),
                           total_duration=Decimal('15'))

        result = self._get_chart()
        self.assertEqual(result['total'], 4)
        self.assertEqual(result['chart_data']['labels'], ['NOANSWER', 'BUSY', 'EXIT_AMD'])
        self.assertEqual(result['chart_data']['datasets'][0]['data'], [2, 1, 1])

        shares_by_status = {s['status']: s for s in result['shares']}
        self.assertEqual(shares_by_status['NOANSWER']['count'], 2)
        self.assertEqual(shares_by_status['NOANSWER']['pct'], 50.0)
        self.assertEqual(shares_by_status['BUSY']['count'], 1)
        self.assertEqual(shares_by_status['BUSY']['pct'], 25.0)
        self.assertEqual(shares_by_status['EXIT_AMD']['count'], 1)
        self.assertEqual(shares_by_status['EXIT_AMD']['pct'], 25.0)

    def test_distribucion_vacia_sin_llamadas_no_atendidas(self):
        self._create_voice('EXIT_ANSWERED', agent_id=1, agent_duration=Decimal('10'),
                           total_duration=Decimal('15'))

        result = self._get_chart()
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['chart_data']['labels'], [])
        self.assertEqual(result['chart_data']['datasets'][0]['data'], [])
        self.assertEqual(result['shares'], [])


class ParseExportFiltersTest(OMLBaseTest):
    """Regresión: _parse_export_filters debe asignar allowed_campaigns con campaña específica."""

    def setUp(self):
        super(ParseExportFiltersTest, self).setUp()
        self.crear_administrador()
        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_DIALER,
            nombre='CSV export filters',
        )
        hoy = timezone.now().date()
        self.desde_str = hoy.strftime('%d/%m/%Y')
        self.hasta_str = self.desde_str

    def _make_request(self, campana_ids):
        request = Mock()
        request.user = self.administrador
        request.data = {
            'task_id': 'test-export-task',
            'desde': self.desde_str,
            'hasta': self.hasta_str,
            'campana': [str(cid) for cid in campana_ids],
        }
        return request

    @patch('api_app.views.reports_centro_contacto._get_campanas_visibles')
    def test_campana_especifica_asigna_allowed_campaigns(self, mock_visible):
        mock_visible.return_value = Campana.objects.filter(pk=self.campana.pk)
        parsed, err = _parse_export_filters(self._make_request([self.campana.pk]))
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        allowed_campaigns = parsed[3]
        self.assertEqual(allowed_campaigns, [self.campana.pk])

    @patch('api_app.views.reports_centro_contacto._get_campanas_visibles')
    def test_campana_invalida_retorna_400(self, mock_visible):
        mock_visible.return_value = Campana.objects.filter(pk=self.campana.pk)
        parsed, err = _parse_export_filters(self._make_request([999999]))
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        self.assertEqual(err.status_code, 400)
