# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from mock import Mock, patch
from django.db.models import Q
from django.test import SimpleTestCase
from django.urls import reverse

from ominicontacto_app.models import Campana, User
from ominicontacto_app.tests.factories import (
    AgenteProfileFactory,
    CampanaFactory,
    GrupoFactory,
    QueueFactory,
    QueueMemberFactory,
)
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD
from api_app.views.reports_centro_contacto import (
    get_omnichannel_share_data,
    obtener_kpis_centro_contacto,
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
