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

"""Tests para EstadisticasServiceV2 (estadísticas de campaña basadas en InteractionsSummary)."""

from __future__ import unicode_literals

import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import connection, connections
from django.utils.translation import gettext as _
from django.utils import timezone

from ominicontacto_app.models import CalificacionCliente, Campana, OpcionCalificacion
from ominicontacto_app.services.estadisticas_campana_v2 import (
    EstadisticasServiceV2,
    _NO_ATENDIDO_LABELS,
)
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD
from ominicontacto_app.tests.factories import (
    AgenteProfileFactory,
    CalificacionClienteFactory,
    CampanaFactory,
    ContactoFactory,
    NombreCalificacionFactory,
    OpcionCalificacionFactory,
    QueueFactory,
    QueueMemberFactory,
)
from reportes_app.models import InteractionsSummary, InteractionTransfers
from whatsapp_app.tests.factories import ConversacionFactory


def _interactions_summary_table_exists():
    """Comprueba si la tabla interactions_summary existe en la BD."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'interactions_summary'
            """
        )
        return cursor.fetchone() is not None


def _interaction_transfers_table_exists():
    """Comprueba si la tabla interaction_transfers existe en la BD."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'interaction_transfers'
            """
        )
        return cursor.fetchone() is not None


@unittest.skipUnless(
    _interactions_summary_table_exists(),
    "Tabla interactions_summary no existe (migración 0012 o esquema externo)",
)
class EstadisticasCampanaV2Test(OMLBaseTest):

    def setUp(self):
        super(EstadisticasCampanaV2Test, self).setUp()
        self.crear_administrador()
        self.agente = self.crear_agente_profile()
        self.nombre_gestion = NombreCalificacionFactory.create(nombre='Gestion')
        self.nombre_no_accion = NombreCalificacionFactory.create(nombre='NoAccion')
        self.campana = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_DIALER,
        )
        self.opcion_gestion = OpcionCalificacionFactory.create(
            campana=self.campana,
            nombre=self.nombre_gestion.nombre,
            tipo=OpcionCalificacion.GESTION,
        )
        self.opcion_no_accion = OpcionCalificacionFactory.create(
            campana=self.campana,
            nombre=self.nombre_no_accion.nombre,
            tipo=OpcionCalificacion.NO_ACCION,
        )
        self.hoy = timezone.now()
        self.fecha_desde = self.hoy.replace(hour=0, minute=0, second=0, microsecond=0)
        self.fecha_hasta = self.fecha_desde + timedelta(days=1) - timedelta(microseconds=1)
        self._patch_replica()

    def _patch_replica(self):
        if not hasattr(connections['replica'], '_orig_cursor'):
            connections['replica']._orig_cursor = connections['replica'].cursor
        connections['replica'].cursor = connections['default'].cursor

    def tearDown(self):
        if hasattr(connections['replica'], '_orig_cursor'):
            connections['replica'].cursor = connections['replica']._orig_cursor
        super(EstadisticasCampanaV2Test, self).tearDown()

    def _create_interaction(
        self,
        interaction_id,
        direction='OUTBOUND',
        status='EXIT_ANSWERED',
        channel_type='VOICE',
        campaign_id=None,
        agent_id=None,
        qualification_id=None,
        is_sale=False,
        start_time=None,
        wait_conn_duration=0,
        agent_duration=0,
    ):
        campaign_id = campaign_id or self.campana.pk
        start_time = start_time or self.fecha_desde
        return InteractionsSummary.objects.using('replica').create(
            interaction_id=interaction_id,
            tenant_id='test-tenant',
            node_id='node-1',
            campaign_id=campaign_id,
            channel_type=channel_type,
            direction=direction,
            status=status,
            hangup_cause=None,
            source_address='',
            destination_address='',
            start_time=start_time,
            end_time=start_time + timedelta(seconds=60),
            total_duration=Decimal('60'),
            bot_duration=Decimal('0'),
            wait_conn_duration=Decimal(str(wait_conn_duration)),
            agent_duration=Decimal(str(agent_duration)),
            agent_id=agent_id,
            qualification_id=qualification_id,
            is_sale=is_sale,
        )

    def test_estadisticas_v2_contract_keys(self):
        """Comprueba que _calcular_estadisticas devuelve todas las keys del contrato."""
        self._create_interaction('int-1', direction='OUTBOUND', status='EXIT_ANSWERED')
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        service.calcular_estadisticas_totales()
        estadisticas = service._calcular_estadisticas(
            self.campana, self.fecha_desde, self.fecha_hasta
        )
        required_keys = [
            'agentes_venta', 'total_asignados', 'total_ventas',
            'calificaciones_nombre', 'calificaciones_cantidad', 'total_calificados',
            'resultado_nombre', 'resultado_cantidad', 'total_no_atendidos',
            'llamadas_pendientes', 'llamadas_realizadas', 'llamadas_recibidas',
            'tiempo_promedio_espera', 'tiempo_promedio_abandono',
            'whatsapp_recibidos',
            'calificaciones', 'cantidad_llamadas',
            'estadisticas_llamadas_por_agente',
            'total_llamadas_ofrecidas', 'total_llamadas_atendidas', 'total_llamadas_no_atendidas',
        ]
        for key in required_keys:
            self.assertIn(key, estadisticas, msg='Falta key: %s' % key)
        self.assertEqual(
            len(estadisticas['cantidad_llamadas']), 2,
            msg='cantidad_llamadas debe ser (headers, values)',
        )
        self.assertEqual(
            len(estadisticas['cantidad_llamadas'][0]),
            len(estadisticas['cantidad_llamadas'][1]),
        )

    def test_estadisticas_v2_general_campana_keys(self):
        """Comprueba que general_campana() devuelve las keys esperadas por el template."""
        self._create_interaction('int-g1', direction='OUTBOUND', status='EXIT_ANSWERED')
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        result = service.general_campana()
        template_keys = [
            'estadisticas', 'barra_campana_calificacion', 'dict_campana_counter',
            'total_asignados', 'agentes_venta', 'total_calificados', 'total_ventas',
            'barra_campana_no_atendido', 'dict_no_atendido_counter', 'total_no_atendidos',
            'calificaciones', 'barra_campana_llamadas', 'dict_llamadas_counter',
            'estadisticas_llamadas_por_agente',
            'total_llamadas_ofrecidas', 'total_llamadas_atendidas', 'total_llamadas_no_atendidas',
            'barra_agent_vs_bot', 'dict_agent_vs_bot_counter', 'dict_wa_agent_vs_bot_counter',
            'barra_wa_agent_vs_bot',
            'interacciones_por_agente',
            'performance_agentes',
        ]
        for key in template_keys:
            self.assertIn(key, result, msg='Falta key en general_campana: %s' % key)

    def test_estadisticas_v2_llamadas_realizadas_outbound(self):
        """OUTBOUND cuenta como llamadas realizadas."""
        self._create_interaction('int-o1', direction='OUTBOUND', status='EXIT_ANSWERED')
        self._create_interaction('int-o2', direction='OUTBOUND', status='EXIT_TIMEOUT')
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        service.calcular_estadisticas_totales()
        self.assertEqual(service._llamadas_realizadas, 2)

    def test_estadisticas_v2_entrante_recibidas_y_tiempos(self):
        """Campaña entrante: INBOUND = recibidas; promedios de espera/abandono."""
        campana_entrante = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        OpcionCalificacionFactory.create(
            campana=campana_entrante, nombre='Op1', tipo=OpcionCalificacion.NO_ACCION
        )
        InteractionsSummary.objects.using('replica').create(
            interaction_id='ib-1',
            tenant_id='t',
            node_id='n1',
            campaign_id=campana_entrante.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ANSWERED',
            start_time=self.fecha_desde,
            end_time=self.fecha_desde + timedelta(seconds=60),
            wait_conn_duration=Decimal('10'),
            agent_duration=Decimal('50'),
        )
        InteractionsSummary.objects.using('replica').create(
            interaction_id='ib-2',
            tenant_id='t',
            node_id='n1',
            campaign_id=campana_entrante.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ABANDON',
            start_time=self.fecha_desde,
            end_time=self.fecha_desde,
            wait_conn_duration=Decimal('20'),
            agent_duration=Decimal('0'),
        )
        service = EstadisticasServiceV2(campana_entrante, self.fecha_desde, self.fecha_hasta)
        service.calcular_estadisticas_totales()
        self.assertEqual(service._llamadas_recibidas, 2)
        self.assertIsNotNone(service._tiempo_promedio_espera)
        self.assertEqual(service._tiempo_promedio_espera, 10.0)
        self.assertIsNotNone(service._tiempo_promedio_abandono)
        self.assertEqual(service._tiempo_promedio_abandono, 20.0)

    @unittest.skipUnless(
        _interaction_transfers_table_exists(),
        "Tabla interaction_transfers no existe",
    )
    def test_estadisticas_v2_origen_transferida_timeout_no_atendida_ni_expirada(self):
        """En campaña origen, transfer OK a otra campaña: recibida pero no atendida/expirada/abandonada."""
        campana_origen = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        campana_destino = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        OpcionCalificacionFactory.create(
            campana=campana_origen, nombre='Origen', tipo=OpcionCalificacion.NO_ACCION
        )
        OpcionCalificacionFactory.create(
            campana=campana_destino, nombre='Destino', tipo=OpcionCalificacion.NO_ACCION
        )
        InteractionsSummary.objects.using('replica').create(
            interaction_id='transfer-origin-timeout',
            tenant_id='t',
            node_id='n1',
            campaign_id=campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_TIMEOUT',
            is_transferred=True,
            start_time=self.fecha_desde,
            end_time=self.fecha_desde + timedelta(seconds=30),
            wait_conn_duration=Decimal('7'),
            agent_duration=Decimal('15'),
            agent_id=self.agente.pk,
        )
        InteractionTransfers.objects.using('replica').create(
            interaction_id='transfer-origin-timeout',
            destination_target='campana-destino',
            destination_type='CAMPAIGN',
            destination_campaign_id=campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
        )

        service = EstadisticasServiceV2(
            campana_origen, self.fecha_desde, self.fecha_hasta
        )
        service.calcular_estadisticas_totales()

        self.assertEqual(service._llamadas_recibidas, 1)
        self.assertIsNone(service._tiempo_promedio_espera)
        self.assertIsNone(service._tiempo_promedio_abandono)
        self.assertEqual(service.reporte_detalle_llamadas[_('Recibidas')], 1)
        self.assertEqual(service.reporte_detalle_llamadas[_('Atendidas')], 0)
        self.assertEqual(service.reporte_detalle_llamadas[_('Expiradas')], 0)
        self.assertEqual(service.reporte_detalle_llamadas[_('Abandonadas')], 0)
        self.assertEqual(service._total_no_atendidos, 0)

    @unittest.skipUnless(
        _interaction_transfers_table_exists(),
        "Tabla interaction_transfers no existe",
    )
    def test_estadisticas_v2_entrante_incluye_llamadas_recibidas_por_transferencia(self):
        """Una campaña entrante destino debe contar interacciones transferidas aunque campaign_id sea otro."""
        campana_origen = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        campana_destino = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        OpcionCalificacionFactory.create(
            campana=campana_origen,
            nombre='Origen',
            tipo=OpcionCalificacion.NO_ACCION,
        )
        OpcionCalificacionFactory.create(
            campana=campana_destino,
            nombre='Destino',
            tipo=OpcionCalificacion.NO_ACCION,
        )

        answered = InteractionsSummary.objects.using('replica').create(
            interaction_id='transfer-in-answered',
            tenant_id='t',
            node_id='n1',
            campaign_id=campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ANSWERED',
            start_time=self.fecha_desde,
            end_time=self.fecha_desde + timedelta(seconds=60),
            wait_conn_duration=Decimal('12'),
            agent_duration=Decimal('40'),
            agent_id=self.agente.pk,
        )
        abandoned = InteractionsSummary.objects.using('replica').create(
            interaction_id='transfer-in-abandon',
            tenant_id='t',
            node_id='n1',
            campaign_id=campana_origen.pk,
            channel_type='VOICE',
            direction='INBOUND',
            status='EXIT_ABANDON',
            start_time=self.fecha_desde + timedelta(minutes=1),
            end_time=self.fecha_desde + timedelta(minutes=1, seconds=20),
            wait_conn_duration=Decimal('18'),
            agent_duration=Decimal('0'),
        )
        InteractionTransfers.objects.using('replica').create(
            interaction_id=answered.interaction_id,
            destination_target='campana-destino',
            destination_type='CAMPAIGN',
            destination_campaign_id=campana_destino.pk,
            transfer_type='BLIND',
            status='OK',
        )
        InteractionTransfers.objects.using('replica').create(
            interaction_id=abandoned.interaction_id,
            destination_target='campana-destino',
            destination_type='CAMPAIGN',
            destination_campaign_id=campana_destino.pk,
            transfer_type='CONSULT',
            status='OK',
        )
        InteractionTransfers.objects.using('replica').create(
            interaction_id='transfer-failed',
            destination_target='campana-destino',
            destination_type='CAMPAIGN',
            destination_campaign_id=campana_destino.pk,
            transfer_type='BLIND',
            status='FAILED',
        )

        service = EstadisticasServiceV2(
            campana_destino, self.fecha_desde, self.fecha_hasta
        )
        service.calcular_estadisticas_totales()

        self.assertEqual(service._llamadas_recibidas, 2)
        self.assertEqual(service._tiempo_promedio_espera, 12.0)
        self.assertEqual(service._tiempo_promedio_abandono, 18.0)
        self.assertEqual(service.reporte_detalle_llamadas[_('Recibidas')], 2)
        self.assertEqual(service.reporte_detalle_llamadas[_('Atendidas')], 1)
        self.assertEqual(service.reporte_detalle_llamadas[_('Abandonadas')], 1)

    def test_estadisticas_v2_no_atendidos_incluye_inbound_abandon_timeout(self):
        """INBOUND con EXIT_ABANDON y EXIT_TIMEOUT se cuentan en reporte_no_atendidos."""
        # OUTBOUND no atendida (ej. timeout)
        self._create_interaction(
            'out-na1', direction='OUTBOUND', status='EXIT_TIMEOUT'
        )
        # INBOUND abandon y timeout
        self._create_interaction(
            'in-ab1', direction='INBOUND', status='EXIT_ABANDON',
            start_time=self.fecha_desde,
        )
        self._create_interaction(
            'in-ab2', direction='INBOUND', status='EXIT_ABANDON',
            start_time=self.fecha_desde,
        )
        self._create_interaction(
            'in-to1', direction='INBOUND', status='EXIT_TIMEOUT',
            start_time=self.fecha_desde,
        )
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        service.calcular_estadisticas_totales()
        # Bucket 8 = Abandonadas por el cliente, 10 = Expiradas
        self.assertEqual(
            service.reporte_no_atendidos[_NO_ATENDIDO_LABELS[8]], 2,
            'INBOUND EXIT_ABANDON debe sumar en Abandonadas por el cliente',
        )
        self.assertEqual(
            service.reporte_no_atendidos[_NO_ATENDIDO_LABELS[10]], 2,
            'OUTBOUND EXIT_TIMEOUT (1) + INBOUND EXIT_TIMEOUT (1) en Expiradas',
        )
        self.assertEqual(
            service._total_no_atendidos, 4,
            '1 outbound no atendida + 2 inbound abandon + 1 inbound timeout = 4',
        )

    def test_reporte_no_atendidos_exit_shortcall_contabilizado_como_shortcall(self):
        """EXIT_SHORTCALL se contabiliza en reporte_no_atendidos como Shortcall (índice 13)."""
        self._create_interaction(
            'out-short1', direction='OUTBOUND', status='EXIT_SHORTCALL',
            start_time=self.fecha_desde,
        )
        self._create_interaction(
            'out-short2', direction='OUTBOUND', status='EXIT_SHORTCALL',
            start_time=self.fecha_desde,
        )
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        service.calcular_estadisticas_totales()
        self.assertEqual(
            service.reporte_no_atendidos[_NO_ATENDIDO_LABELS[13]], 2,
            'EXIT_SHORTCALL debe sumar en Shortcall',
        )
        self.assertEqual(service._total_no_atendidos, 2)

    def test_estadisticas_v2_general_campana_crea_directorio_exist_ok(self):
        """general_campana() crea el directorio con makedirs exist_ok (no falla si ya existe)."""
        self._create_interaction('int-dir', direction='OUTBOUND', status='EXIT_ANSWERED')
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        result1 = service.general_campana()
        self.assertIn('estadisticas', result1)
        # Segunda llamada no debe fallar aunque el directorio ya exista
        result2 = service.general_campana()
        self.assertIn('estadisticas', result2)

    def test_calificaciones_crm_conteo_por_opcion(self):
        """Calificaciones CRM: conteo por opción desde CalificacionCliente (no qualification_id)."""
        contacto1 = ContactoFactory(bd_contacto=self.campana.bd_contacto)
        contacto2 = ContactoFactory(bd_contacto=self.campana.bd_contacto)
        contacto3 = ContactoFactory(bd_contacto=self.campana.bd_contacto)
        CalificacionClienteFactory(
            opcion_calificacion=self.opcion_gestion,
            contacto=contacto1,
            agente=self.agente,
        )
        CalificacionClienteFactory(
            opcion_calificacion=self.opcion_gestion,
            contacto=contacto2,
            agente=self.agente,
        )
        CalificacionClienteFactory(
            opcion_calificacion=self.opcion_no_accion,
            contacto=contacto3,
            agente=self.agente,
        )
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        service.calcular_estadisticas_totales()
        self.assertEqual(
            service.reporte_calificaciones_atendidas[self.opcion_gestion.nombre], 2,
        )
        self.assertEqual(
            service.reporte_calificaciones_atendidas[self.opcion_no_accion.nombre], 1,
        )
        self.assertEqual(service.total_calificados, 3)
        self.assertEqual(service.total_ventas, 2)

    def test_calificaciones_crm_conteo_por_agente(self):
        """Calificaciones CRM: conteo por agente y total_gestionados desde CalificacionCliente."""
        QueueFactory(campana=self.campana)
        self._hacer_miembro(self.agente, self.campana)
        agente2 = self.crear_agente_profile()
        self._hacer_miembro(agente2, self.campana)
        c1 = ContactoFactory(bd_contacto=self.campana.bd_contacto)
        c2 = ContactoFactory(bd_contacto=self.campana.bd_contacto)
        c3 = ContactoFactory(bd_contacto=self.campana.bd_contacto)
        CalificacionClienteFactory(
            opcion_calificacion=self.opcion_gestion,
            contacto=c1,
            agente=self.agente,
        )
        CalificacionClienteFactory(
            opcion_calificacion=self.opcion_gestion,
            contacto=c2,
            agente=self.agente,
        )
        CalificacionClienteFactory(
            opcion_calificacion=self.opcion_no_accion,
            contacto=c3,
            agente=agente2,
        )
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        service.calcular_estadisticas_totales()
        self.assertIn(self.agente.pk, service.reporte_calificaciones_agentes_dict)
        self.assertEqual(
            service.reporte_calificaciones_agentes_dict[self.agente.pk]['total_calificados'], 2,
        )
        self.assertEqual(
            service.reporte_calificaciones_agentes_dict[self.agente.pk]['total_gestionados'], 2,
        )
        self.assertIn(agente2.pk, service.reporte_calificaciones_agentes_dict)
        self.assertEqual(
            service.reporte_calificaciones_agentes_dict[agente2.pk]['total_calificados'], 1,
        )
        self.assertEqual(
            service.reporte_calificaciones_agentes_dict[agente2.pk]['total_gestionados'], 0,
        )

    def test_calificaciones_crm_llamadas_atendidas_sin_calificacion(self):
        """Llamadas atendidas sin calificación = atendidas humano (IS) - total_calificados (CRM)."""
        self._create_interaction(
            'int-a1', agent_id=self.agente.pk, agent_duration=10,
        )
        self._create_interaction(
            'int-a2', agent_id=self.agente.pk, agent_duration=5,
        )
        self._create_interaction(
            'int-a3', agent_id=self.agente.pk, agent_duration=8,
        )
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        service.calcular_estadisticas_totales()
        self.assertEqual(service.llamadas_atendidas_sin_calificacion, 3)
        c1 = ContactoFactory(bd_contacto=self.campana.bd_contacto)
        c2 = ContactoFactory(bd_contacto=self.campana.bd_contacto)
        CalificacionClienteFactory(
            opcion_calificacion=self.opcion_gestion,
            contacto=c1,
            agente=self.agente,
        )
        CalificacionClienteFactory(
            opcion_calificacion=self.opcion_no_accion,
            contacto=c2,
            agente=self.agente,
        )
        service2 = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        service2.calcular_estadisticas_totales()
        self.assertEqual(service2.llamadas_atendidas_sin_calificacion, 1)

    def test_calificaciones_crm_entrante_deduplica_por_callid(self):
        """
        Campaña entrante: dos históricos para el mismo callid cuentan como 1 calificación
        (se toma la última por history_date). Evita sobreconteo por actualizaciones.
        """
        campana_entrante = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        opcion_a = OpcionCalificacionFactory.create(
            campana=campana_entrante,
            nombre='OpcionA',
            tipo=OpcionCalificacion.GESTION,
        )
        opcion_b = OpcionCalificacionFactory.create(
            campana=campana_entrante,
            nombre='OpcionB',
            tipo=OpcionCalificacion.NO_ACCION,
        )
        QueueFactory(campana=campana_entrante)
        self._hacer_miembro(self.agente, campana_entrante)
        contacto = ContactoFactory(bd_contacto=campana_entrante.bd_contacto)
        cal = CalificacionClienteFactory(
            opcion_calificacion=opcion_a,
            contacto=contacto,
            agente=self.agente,
            callid='call-entrante-dup',
        )
        cal.opcion_calificacion = opcion_b
        cal.save()
        self.assertEqual(
            CalificacionCliente.history.filter(callid='call-entrante-dup').count(),
            2,
            'Debe haber 2 históricos para el mismo callid',
        )
        service = EstadisticasServiceV2(
            campana_entrante, self.fecha_desde, self.fecha_hasta
        )
        service.calcular_estadisticas_totales()
        self.assertEqual(
            service.total_calificados, 1,
            'Solo debe contarse 1 calificación efectiva por callid',
        )
        self.assertEqual(
            service.reporte_calificaciones_atendidas[opcion_a.nombre], 0,
        )
        self.assertEqual(
            service.reporte_calificaciones_atendidas[opcion_b.nombre], 1,
            'Cuenta la última (opcion_b), no la inicial',
        )
        self.assertIn(self.agente.pk, service.reporte_calificaciones_agentes_dict)
        self.assertEqual(
            service.reporte_calificaciones_agentes_dict[self.agente.pk]['total_calificados'],
            1,
        )
        self.assertEqual(
            service.reporte_calificaciones_agentes_dict[self.agente.pk]['total_gestionados'],
            0,
            'Última opción es NO_ACCION',
        )

    def test_calificaciones_crm_entrante_callid_null_excluido(self):
        """Histórico con callid None o vacío en rango no aumenta total_calificados."""
        campana_entrante = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        opcion = OpcionCalificacionFactory.create(
            campana=campana_entrante,
            nombre='Op1',
            tipo=OpcionCalificacion.NO_ACCION,
        )
        contacto = ContactoFactory(bd_contacto=campana_entrante.bd_contacto)
        CalificacionClienteFactory(
            opcion_calificacion=opcion,
            contacto=contacto,
            agente=self.agente,
            callid=None,
        )
        service = EstadisticasServiceV2(
            campana_entrante, self.fecha_desde, self.fecha_hasta
        )
        service.calcular_estadisticas_totales()
        self.assertEqual(
            service.total_calificados, 0,
            'callid=None debe excluirse del conteo entrante',
        )
        self.assertEqual(
            service.reporte_calificaciones_atendidas[opcion.nombre], 0,
        )

    def test_calificaciones_crm_entrante_callid_solo_espacios_excluido(self):
        """Histórico con callid solo espacios en blanco no aumenta total_calificados."""
        campana_entrante = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        opcion = OpcionCalificacionFactory.create(
            campana=campana_entrante,
            nombre='Op1',
            tipo=OpcionCalificacion.NO_ACCION,
        )
        contacto = ContactoFactory(bd_contacto=campana_entrante.bd_contacto)
        CalificacionClienteFactory(
            opcion_calificacion=opcion,
            contacto=contacto,
            agente=self.agente,
            callid='   ',
        )
        service = EstadisticasServiceV2(
            campana_entrante, self.fecha_desde, self.fecha_hasta
        )
        service.calcular_estadisticas_totales()
        self.assertEqual(
            service.total_calificados, 0,
            'callid con solo espacios debe excluirse del conteo entrante',
        )
        self.assertEqual(
            service.reporte_calificaciones_atendidas[opcion.nombre], 0,
        )

    def test_calificaciones_crm_entrante_history_type_delete_excluido(self):
        """Create + delete en rango para un callid: total_calificados 0 (último = delete)."""
        campana_entrante = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        opcion = OpcionCalificacionFactory.create(
            campana=campana_entrante,
            nombre='OpDel',
            tipo=OpcionCalificacion.NO_ACCION,
        )
        QueueFactory(campana=campana_entrante)
        self._hacer_miembro(self.agente, campana_entrante)
        contacto = ContactoFactory(bd_contacto=campana_entrante.bd_contacto)
        cal = CalificacionClienteFactory(
            opcion_calificacion=opcion,
            contacto=contacto,
            agente=self.agente,
            callid='call-delete-me',
        )
        cal.delete()
        self.assertEqual(
            CalificacionCliente.history.filter(callid='call-delete-me').count(),
            2,
            'Debe haber 2 históricos (create + delete)',
        )
        service = EstadisticasServiceV2(
            campana_entrante, self.fecha_desde, self.fecha_hasta
        )
        service.calcular_estadisticas_totales()
        self.assertEqual(
            service.total_calificados, 0,
            'Último histórico es delete, no debe contarse',
        )

    def test_calificaciones_crm_entrante_ultimo_fuera_de_rango(self):
        """Dos históricos mismo callid: uno en rango (A), otro fuera (B). Solo cuenta A."""
        campana_entrante = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        opcion_a = OpcionCalificacionFactory.create(
            campana=campana_entrante,
            nombre='OpA',
            tipo=OpcionCalificacion.GESTION,
        )
        opcion_b = OpcionCalificacionFactory.create(
            campana=campana_entrante,
            nombre='OpB',
            tipo=OpcionCalificacion.NO_ACCION,
        )
        QueueFactory(campana=campana_entrante)
        self._hacer_miembro(self.agente, campana_entrante)
        contacto = ContactoFactory(bd_contacto=campana_entrante.bd_contacto)
        cal = CalificacionClienteFactory(
            opcion_calificacion=opcion_a,
            contacto=contacto,
            agente=self.agente,
            callid='call-fuera-rango',
        )
        cal.opcion_calificacion = opcion_b
        cal.save()
        latest = CalificacionCliente.history.filter(
            callid='call-fuera-rango'
        ).order_by('-history_id').first()
        latest.history_date = self.fecha_hasta + timedelta(days=1)
        latest.save()
        service = EstadisticasServiceV2(
            campana_entrante, self.fecha_desde, self.fecha_hasta
        )
        service.calcular_estadisticas_totales()
        self.assertEqual(service.total_calificados, 1)
        self.assertEqual(
            service.reporte_calificaciones_atendidas[opcion_a.nombre], 1,
            'Solo el histórico en rango (opcion_a) cuenta',
        )
        self.assertEqual(
            service.reporte_calificaciones_atendidas[opcion_b.nombre], 0,
        )

    def test_calificaciones_crm_entrante_empate_history_date(self):
        """Dos históricos mismo callid, mismo history_date, distintos history_id: cuenta 1 (mayor history_id)."""
        campana_entrante = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_ENTRANTE,
        )
        opcion_a = OpcionCalificacionFactory.create(
            campana=campana_entrante,
            nombre='OpA',
            tipo=OpcionCalificacion.NO_ACCION,
        )
        opcion_b = OpcionCalificacionFactory.create(
            campana=campana_entrante,
            nombre='OpB',
            tipo=OpcionCalificacion.GESTION,
        )
        QueueFactory(campana=campana_entrante)
        self._hacer_miembro(self.agente, campana_entrante)
        contacto = ContactoFactory(bd_contacto=campana_entrante.bd_contacto)
        cal = CalificacionClienteFactory(
            opcion_calificacion=opcion_a,
            contacto=contacto,
            agente=self.agente,
            callid='call-empate',
        )
        first_hist = CalificacionCliente.history.filter(
            callid='call-empate'
        ).order_by('history_id').first()
        cal.opcion_calificacion = opcion_b
        cal.save()
        second_hist = CalificacionCliente.history.filter(
            callid='call-empate'
        ).order_by('-history_id').first()
        first_hist.history_date = second_hist.history_date
        first_hist.save()
        service = EstadisticasServiceV2(
            campana_entrante, self.fecha_desde, self.fecha_hasta
        )
        service.calcular_estadisticas_totales()
        self.assertEqual(service.total_calificados, 1)
        self.assertEqual(
            service.reporte_calificaciones_atendidas[opcion_b.nombre], 1,
            'Gana el de mayor history_id (opcion_b)',
        )
        self.assertEqual(
            service.reporte_calificaciones_atendidas[opcion_a.nombre], 0,
        )

    def test_llamadas_atendidas_sin_calificacion_agent_duration_solo_y_agent_id_solo(self):
        """Atendidas con solo agent_duration>0 (agent_id null) o solo agent_id (agent_duration=0) cuentan."""
        self._create_interaction(
            'int-dur', agent_id=None, agent_duration=10,
        )
        self._create_interaction(
            'int-id', agent_id=self.agente.pk, agent_duration=0,
        )
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        service.calcular_estadisticas_totales()
        self.assertEqual(
            service.llamadas_atendidas_sin_calificacion, 2,
            'Ambas cuentan como atendidas por humano',
        )

    def test_interacciones_por_agente_wa_desde_conversacion_whatsapp(self):
        """wa_in/wa_out se calculan desde ConversacionWhatsapp y no desde InteractionsSummary."""
        # Filas WA en interactions_summary: no deben afectar wa_in/wa_out finales.
        self._create_interaction(
            'is-wa-in',
            channel_type='WA',
            direction='INBOUND',
            agent_id=self.agente.pk,
        )
        self._create_interaction(
            'is-wa-out',
            channel_type='WHATSAPP',
            direction='OUTBOUND',
            agent_id=self.agente.pk,
        )
        # Conversaciones WA válidas: 1 inbound y 2 outbound.
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=False,
            timestamp=self.fecha_desde + timedelta(hours=1),
        )
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=True,
            timestamp=self.fecha_desde + timedelta(hours=2),
        )
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=True,
            timestamp=self.fecha_desde + timedelta(hours=3),
        )

        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        qs_interacciones = service._get_queryset_interacciones_por_agente()
        service._interacciones_por_agente(qs_interacciones)
        row = next(
            r for r in service.interacciones_por_agente if r['agent_id'] == self.agente.pk
        )

        self.assertEqual(row['wa_in'], 1)
        self.assertEqual(row['wa_out'], 2)
        self.assertEqual(row['tel_in'], 0)
        self.assertEqual(row['tel_out'], 0)

    def test_interacciones_por_agente_incluye_agente_solo_whatsapp(self):
        """Un agente con solo conversaciones WA debe aparecer con columnas no WA en cero."""
        agente_wa_only = AgenteProfileFactory()
        ConversacionFactory.create(
            campana=self.campana,
            agent=agente_wa_only,
            saliente=False,
            timestamp=self.fecha_desde + timedelta(hours=1),
        )
        ConversacionFactory.create(
            campana=self.campana,
            agent=agente_wa_only,
            saliente=True,
            timestamp=self.fecha_desde + timedelta(hours=2),
        )

        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        qs_interacciones = service._get_queryset_interacciones_por_agente()
        service._interacciones_por_agente(qs_interacciones)
        row = next(
            r for r in service.interacciones_por_agente if r['agent_id'] == agente_wa_only.pk
        )

        self.assertEqual(row['wa_in'], 1)
        self.assertEqual(row['wa_out'], 1)
        self.assertEqual(row['tel_in'], 0)
        self.assertEqual(row['tel_out'], 0)
        self.assertEqual(row['fbmsn_in'], 0)
        self.assertEqual(row['fbmsn_out'], 0)
        self.assertEqual(row['email_in'], 0)
        self.assertEqual(row['email_out'], 0)

    def test_interacciones_por_agente_wa_respeta_filtros(self):
        """Conversaciones WA fuera de rango, de otra campaña o sin agente no cuentan."""
        campana_otra = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA,
            type=Campana.TYPE_DIALER,
        )
        # Válidas (misma campaña, en rango, con agente)
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=False,
            timestamp=self.fecha_desde + timedelta(minutes=10),
        )
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=True,
            timestamp=self.fecha_desde + timedelta(minutes=20),
        )
        # Fuera de rango
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=False,
            timestamp=self.fecha_hasta + timedelta(seconds=1),
        )
        # Otra campaña
        ConversacionFactory.create(
            campana=campana_otra,
            agent=self.agente,
            saliente=True,
            timestamp=self.fecha_desde + timedelta(minutes=30),
        )
        # Sin agente
        ConversacionFactory.create(
            campana=self.campana,
            agent=None,
            saliente=True,
            timestamp=self.fecha_desde + timedelta(minutes=40),
        )

        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        qs_interacciones = service._get_queryset_interacciones_por_agente()
        service._interacciones_por_agente(qs_interacciones)
        row = next(
            r for r in service.interacciones_por_agente if r['agent_id'] == self.agente.pk
        )

        self.assertEqual(row['wa_in'], 1)
        self.assertEqual(row['wa_out'], 1)

    def test_whatsapp_recibidos_es_none_si_campana_sin_whatsapp_habilitado(self):
        """Si la campaña no tiene canalidad WhatsApp, whatsapp_recibidos es None."""
        self.campana.whatsapp_habilitado = False
        self.campana.save()
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=False,
            timestamp=self.fecha_desde + timedelta(hours=1),
        )
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        estadisticas = service._calcular_estadisticas(
            self.campana, self.fecha_desde, self.fecha_hasta
        )
        self.assertIsNone(estadisticas['whatsapp_recibidos'])

    def test_whatsapp_recibidos_cuenta_inbound_cuando_campana_tiene_whatsapp_habilitado(self):
        """Con canalidad WhatsApp habilitada, whatsapp_recibidos es el conteo de conversaciones inbound."""
        self.campana.whatsapp_habilitado = True
        self.campana.save()
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=False,
            timestamp=self.fecha_desde + timedelta(hours=1),
        )
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=False,
            timestamp=self.fecha_desde + timedelta(hours=2),
        )
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=True,
            timestamp=self.fecha_desde + timedelta(hours=3),
        )
        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        estadisticas = service._calcular_estadisticas(
            self.campana, self.fecha_desde, self.fecha_hasta
        )
        self.assertEqual(estadisticas['whatsapp_recibidos'], 2)

    def test_estadisticas_por_agente_reparte_credito_desde_agent_segments(self):
        """La llamada acredita al agente físico y a los agentes previos del JSON channel_data."""
        QueueFactory(campana=self.campana)
        self._hacer_miembro(self.agente, self.campana)
        agente2 = self.crear_agente_profile()
        self._hacer_miembro(agente2, self.campana)

        InteractionsSummary.objects.using('replica').create(
            interaction_id='dialer-segments-1',
            tenant_id='t',
            node_id='n1',
            campaign_id=self.campana.pk,
            channel_type='VOICE',
            direction='OUTBOUND',
            status='EXIT_ANSWERED',
            start_time=self.fecha_desde,
            end_time=self.fecha_desde + timedelta(seconds=60),
            total_duration=Decimal('60'),
            bot_duration=Decimal('0'),
            wait_conn_duration=Decimal('0'),
            agent_duration=Decimal('20'),
            agent_id=agente2.pk,
            channel_data={
                'agent_segments': [
                    {'agent_id': self.agente.pk, 'talk_duration': 8.0},
                    {'agent_id': agente2.pk, 'talk_duration': 12.0},
                ],
            },
        )

        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        qs = service._get_base_queryset()
        service._estadisticas_por_agente(qs)

        self.assertIn(self.agente.pk, service.estadisticas_llamadas_por_agente)
        self.assertIn(agente2.pk, service.estadisticas_llamadas_por_agente)
        self.assertEqual(
            service.estadisticas_llamadas_por_agente[self.agente.pk]['ofrecidas'], 1,
        )
        self.assertEqual(
            service.estadisticas_llamadas_por_agente[self.agente.pk]['atendidas'], 1,
        )
        self.assertEqual(
            service.estadisticas_llamadas_por_agente[agente2.pk]['ofrecidas'], 1,
        )
        self.assertEqual(
            service.estadisticas_llamadas_por_agente[agente2.pk]['atendidas'], 1,
        )

    def test_interacciones_por_agente_no_wa_se_mantiene_desde_interactions_summary(self):
        """Las columnas tel/fbmsn/email se siguen calculando desde InteractionsSummary."""
        self._create_interaction(
            'is-voice-out',
            channel_type='VOICE',
            direction='OUTBOUND',
            agent_id=self.agente.pk,
        )
        self._create_interaction(
            'is-voice-in',
            channel_type='VOICE',
            direction='INBOUND',
            agent_id=self.agente.pk,
        )
        self._create_interaction(
            'is-fb-out',
            channel_type='FBMSN',
            direction='OUTBOUND',
            agent_id=self.agente.pk,
        )
        self._create_interaction(
            'is-fb-in',
            channel_type='FACEBOOK_MSN',
            direction='INBOUND',
            agent_id=self.agente.pk,
        )
        self._create_interaction(
            'is-email-out',
            channel_type='EMAIL',
            direction='OUTBOUND',
            agent_id=self.agente.pk,
        )
        self._create_interaction(
            'is-email-in',
            channel_type='EMAIL',
            direction='INBOUND',
            agent_id=self.agente.pk,
        )
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=False,
            timestamp=self.fecha_desde + timedelta(hours=1),
        )
        ConversacionFactory.create(
            campana=self.campana,
            agent=self.agente,
            saliente=True,
            timestamp=self.fecha_desde + timedelta(hours=2),
        )

        service = EstadisticasServiceV2(self.campana, self.fecha_desde, self.fecha_hasta)
        qs_interacciones = service._get_queryset_interacciones_por_agente()
        service._interacciones_por_agente(qs_interacciones)
        row = next(
            r for r in service.interacciones_por_agente if r['agent_id'] == self.agente.pk
        )

        self.assertEqual(row['tel_out'], 1)
        self.assertEqual(row['tel_in'], 1)
        self.assertEqual(row['fbmsn_out'], 1)
        self.assertEqual(row['fbmsn_in'], 1)
        self.assertEqual(row['email_out'], 1)
        self.assertEqual(row['email_in'], 1)
        self.assertEqual(row['wa_in'], 1)
        self.assertEqual(row['wa_out'], 1)
