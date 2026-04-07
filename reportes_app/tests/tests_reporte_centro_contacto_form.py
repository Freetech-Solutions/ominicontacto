# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django.test import SimpleTestCase

from ominicontacto_app.models import Campana
from reportes_app.forms import ReporteCentroContactoForm


class DummyCampaign(object):

    def __init__(self, campaign_id, nombre, estado):
        self.id = campaign_id
        self.nombre = nombre
        self.estado = estado


class DummyGroup(object):

    def __init__(self, group_id, nombre):
        self.id = group_id
        self.nombre = nombre


class DummyUser(object):

    def __init__(self, full_name, username):
        self._full_name = full_name
        self.username = username

    def get_full_name(self):
        return self._full_name


class DummyAgent(object):

    def __init__(self, agent_id, full_name, username):
        self.id = agent_id
        self.user = DummyUser(full_name, username)


class ReporteCentroContactoFormTest(SimpleTestCase):

    def setUp(self):
        super(ReporteCentroContactoFormTest, self).setUp()
        self.campanas = [
            DummyCampaign(101, 'Campana activa', Campana.ESTADO_ACTIVA),
            DummyCampaign(102, 'Campana finalizada', Campana.ESTADO_FINALIZADA),
            DummyCampaign(103, 'Campana pausada', Campana.ESTADO_PAUSADA),
        ]
        self.grupos = [
            DummyGroup(201, 'Grupo ventas'),
            DummyGroup(202, 'Grupo cobranzas'),
        ]
        self.agentes = [
            DummyAgent(301, 'Agente Uno', 'agente_1'),
            DummyAgent(302, 'Agente Dos', 'agente_2'),
        ]
        self.fecha = '01/01/2025-01/01/2025'

    def _build_form(self, campanas=None, incluir_finalizadas=False, grupos=None, agentes=None,
                    contacto_id=None, address=None, fecha=None):
        data = {
            'fecha': fecha if fecha is not None else self.fecha,
            'campana': campanas or [],
        }
        if grupos is not None:
            data['grupo_agente'] = grupos
        if agentes is not None:
            data['agente'] = agentes
        if contacto_id is not None:
            data['contacto_id'] = contacto_id
        if address is not None:
            data['address'] = address
        if incluir_finalizadas:
            data['incluir_finalizadas'] = 'on'
        return ReporteCentroContactoForm(
            campanas_asignadas=self.campanas,
            grupos_agentes=self.grupos,
            agentes_asignados=self.agentes,
            data=data,
        )

    def test_all_campaigns_value_is_valid(self):
        form = self._build_form(
            campanas=[ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE]
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['campana'],
            [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
        )

    def test_multiple_specific_campaigns_are_valid(self):
        form = self._build_form(campanas=['101', '103'])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['campana'], ['101', '103'])

    def test_all_campaigns_value_is_exclusive(self):
        form = self._build_form(
            campanas=[ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE, '101']
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['campana'],
            [ReporteCentroContactoForm.TODAS_LAS_CAMPANAS_VALUE],
        )

    def test_finalized_campaign_is_rejected_when_checkbox_is_off(self):
        form = self._build_form(campanas=['102'])
        self.assertFalse(form.is_valid())
        self.assertIn('campana', form.errors)

    def test_finalized_campaign_is_valid_when_checkbox_is_on(self):
        form = self._build_form(campanas=['102'], incluir_finalizadas=True)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['campana'], ['102'])

    def test_all_groups_value_is_valid(self):
        form = self._build_form(
            grupos=[ReporteCentroContactoForm.TODOS_LOS_GRUPOS_VALUE]
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['grupo_agente'],
            [ReporteCentroContactoForm.TODOS_LOS_GRUPOS_VALUE],
        )

    def test_single_group_is_valid(self):
        form = self._build_form(grupos=['201'])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['grupo_agente'], ['201'])

    def test_multiple_groups_are_valid(self):
        form = self._build_form(grupos=['201', '202'])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['grupo_agente'], ['201', '202'])

    def test_all_groups_value_is_exclusive(self):
        form = self._build_form(
            grupos=[ReporteCentroContactoForm.TODOS_LOS_GRUPOS_VALUE, '201']
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['grupo_agente'],
            [ReporteCentroContactoForm.TODOS_LOS_GRUPOS_VALUE],
        )

    def test_groups_default_to_all_in_unbound_form(self):
        form = ReporteCentroContactoForm(
            campanas_asignadas=self.campanas,
            grupos_agentes=self.grupos,
        )
        self.assertEqual(
            form.fields['grupo_agente'].initial,
            [ReporteCentroContactoForm.TODOS_LOS_GRUPOS_VALUE],
        )

    def test_invalid_group_is_rejected(self):
        form = self._build_form(grupos=['999'])
        self.assertFalse(form.is_valid())
        self.assertIn('grupo_agente', form.errors)

    def test_all_agents_value_is_valid(self):
        form = self._build_form(
            agentes=[ReporteCentroContactoForm.TODOS_LOS_AGENTES_VALUE]
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['agente'],
            [ReporteCentroContactoForm.TODOS_LOS_AGENTES_VALUE],
        )

    def test_single_agent_is_valid(self):
        form = self._build_form(agentes=['301'])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['agente'], ['301'])

    def test_multiple_agents_are_valid(self):
        form = self._build_form(agentes=['301', '302'])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['agente'], ['301', '302'])

    def test_all_agents_value_is_exclusive(self):
        form = self._build_form(
            agentes=[ReporteCentroContactoForm.TODOS_LOS_AGENTES_VALUE, '301']
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['agente'],
            [ReporteCentroContactoForm.TODOS_LOS_AGENTES_VALUE],
        )

    def test_agents_default_to_all_in_unbound_form(self):
        form = ReporteCentroContactoForm(
            campanas_asignadas=self.campanas,
            grupos_agentes=self.grupos,
            agentes_asignados=self.agentes,
        )
        self.assertEqual(
            form.fields['agente'].initial,
            [ReporteCentroContactoForm.TODOS_LOS_AGENTES_VALUE],
        )

    def test_invalid_agent_is_rejected(self):
        form = self._build_form(agentes=['999'])
        self.assertFalse(form.is_valid())
        self.assertIn('agente', form.errors)

    def test_contact_id_is_valid_integer(self):
        form = self._build_form(contacto_id='12345')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['contacto_id'], 12345)

    def test_contact_id_must_be_numeric(self):
        form = self._build_form(contacto_id='abc')
        self.assertFalse(form.is_valid())
        self.assertIn('contacto_id', form.errors)

    def test_fecha_with_spaces_range_is_valid(self):
        form = self._build_form(fecha='01/01/2025 - 07/01/2025')
        self.assertTrue(form.is_valid(), form.errors)

    def test_address_phone_text_is_valid(self):
        form = self._build_form(address='5551234')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['address'], '5551234')

    def test_address_email_text_is_valid(self):
        form = self._build_form(address='user@example.com')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['address'], 'user@example.com')

    def test_address_is_trimmed(self):
        form = self._build_form(address='  ig_username  ')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['address'], 'ig_username')

    def test_address_empty_string_is_normalized_to_none(self):
        form = self._build_form(address=' ')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['address'])

    def test_address_missing_is_normalized_to_none(self):
        form = self._build_form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['address'])
