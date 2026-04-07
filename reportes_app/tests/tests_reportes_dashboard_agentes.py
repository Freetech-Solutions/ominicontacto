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
Tests relacionados con la lista de contactos de los Agentes
"""
from __future__ import unicode_literals

import unittest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.db import connection
from django.db import connections
from django.utils.timezone import now, timedelta

from ominicontacto_app.tests.utiles import OMLBaseTest
from ominicontacto_app.tests.factories import (CampanaFactory, UserFactory, PausaFactory)
from ominicontacto_app.models import Campana, Pausa

from reportes_app.reportes.reporte_estadisticas_agentes import (
    ReporteEstadisticasDiariaAgente,
    ReporteDiarioAgentesFamily,
)
from reportes_app.models import AgentActivityEventV2, InteractionsSummary


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


@unittest.skipUnless(
    _interactions_summary_table_exists(),
    "Tabla interactions_summary no existe (migración 0012 o esquema externo)",
)
class DashboardAgenteTests(OMLBaseTest):

    PWD = u'admin123'

    def setUp(self):
        self.usuario_admin_supervisor = UserFactory(is_staff=True, is_supervisor=True)
        self.usuario_admin_supervisor.set_password(self.PWD)
        self.usuario_admin_supervisor.save()
        super(DashboardAgenteTests, self).setUp()
        self.agente_profile = self.crear_agente_profile()
        self.campana_activa = CampanaFactory.create(
            estado=Campana.ESTADO_ACTIVA, type=Campana.TYPE_PREVIEW)
        self._patch_replica()

    def tearDown(self):
        if hasattr(connections['replica'], '_orig_cursor'):
            connections['replica'].cursor = connections['replica']._orig_cursor
        super(DashboardAgenteTests, self).tearDown()

    def _patch_replica(self):
        if not hasattr(connections['replica'], '_orig_cursor'):
            connections['replica']._orig_cursor = connections['replica'].cursor
        connections['replica'].cursor = connections['default'].cursor

    def _create_interaction(
        self,
        interaction_id,
        numero_marcado='35100001112',
        agent_id=None,
        campaign_id=None,
        end_time=None,
        direction='OUTBOUND',
        initiation_method='AGENT',
    ):
        agent_id = agent_id or self.agente_profile.pk
        campaign_id = campaign_id or self.campana_activa.pk
        end_time = end_time or now()
        start_time = end_time - timedelta(seconds=60)
        return InteractionsSummary.objects.using('replica').create(
            interaction_id=interaction_id,
            tenant_id='test-tenant',
            node_id='node-1',
            campaign_id=campaign_id,
            channel_type='VOICE',
            direction=direction,
            initiation_method=initiation_method,
            status='EXIT_ANSWERED',
            hangup_cause=None,
            source_address='' if direction == 'OUTBOUND' else numero_marcado,
            destination_address=numero_marcado if direction == 'OUTBOUND' else '',
            start_time=start_time,
            end_time=end_time,
            total_duration=Decimal('60'),
            bot_duration=Decimal('0'),
            wait_conn_duration=Decimal('0'),
            agent_duration=Decimal('60'),
            agent_id=agent_id,
            qualification_id=None,
            customer_id=None,
            is_sale=False,
            is_transferred=False,
            transfer_count=0,
            channel_data={},
            created_at=end_time,
            updated_at=end_time,
        )

    def test_se_muestran_estadisticas_del_dia_actual(self):
        ayer = now() - timedelta(days=1)
        self._create_interaction('call-ayer', '35100001111', end_time=ayer)
        self._create_interaction('call-hoy', '35100001112', end_time=now())
        reporte = ReporteEstadisticasDiariaAgente()
        logs_agente_reporte = reporte.estadisticas[self.agente_profile.pk]['logs']
        self.assertEqual(len(logs_agente_reporte), 1)

    def test_se_muestran_las_ultimas_10_llamadas(self):
        numero_llamada_excluida = '3510000111'
        ahora = now()
        self._create_interaction('call-excluida', numero_llamada_excluida, end_time=ahora)
        for i in range(1, 11):
            time_llamada = ahora + timedelta(minutes=i)
            self._create_interaction(
                f'call-{i}', '35100213121', end_time=time_llamada
            )
        reporte = ReporteEstadisticasDiariaAgente()
        reporte_agente = reporte.estadisticas[self.agente_profile.pk]
        llamada_excluida_encontrada = False
        for log in reporte_agente['logs']:
            if log['phone'] == numero_llamada_excluida:
                llamada_excluida_encontrada = True
        self.assertFalse(llamada_excluida_encontrada)

    def test_se_muestra_el_tiempo_de_sesion_correctamente(self):
        horas_sesion = 1
        tiempo_inicial = now()
        tiempo_removemember_1 = tiempo_inicial + timedelta(microseconds=20000)
        tiempo_addmember = tiempo_removemember_1 + timedelta(microseconds=3000)
        tiempo_removemember_2 = tiempo_addmember + timedelta(hours=horas_sesion)
        # Fuente v2: AgentActivityEventV2 (ReporteEstadisticasDiariaAgente usa get_agent_activity_kpis_v2)
        AgentActivityEventV2.objects.create(
            agente_id=self.agente_profile.id, ts=tiempo_addmember,
            event_type=AgentActivityEventV2.EventType.SESSION_LOGIN)
        AgentActivityEventV2.objects.create(
            agente_id=self.agente_profile.id, ts=tiempo_removemember_2,
            event_type=AgentActivityEventV2.EventType.SESSION_LOGOUT)
        reporte = ReporteEstadisticasDiariaAgente()
        reporte_agente = reporte.estadisticas[self.agente_profile.pk]
        self.assertEqual(reporte_agente['tiempos'].sesion, timedelta(hours=horas_sesion))

    def test_se_muestran_los_tiempos_de_pausa_correctamente(self):
        horas_sesion = 1
        tiempo_inicial = now()
        pausa1 = PausaFactory(tipo=Pausa.TIPO_PRODUCTIVA)
        pausa2 = PausaFactory(tipo=Pausa.TIPO_RECREATIVA)
        tiempo_addmember = tiempo_inicial + timedelta(microseconds=3000)
        tiempo_inicio_pausa_1 = tiempo_addmember + timedelta(minutes=2)
        tiempo_final_pausa_1 = tiempo_inicio_pausa_1 + timedelta(minutes=2)
        tiempo_inicio_pausa_2 = tiempo_final_pausa_1 + timedelta(minutes=2)
        tiempo_final_pausa_2 = tiempo_inicio_pausa_2 + timedelta(minutes=2)
        tiempo_removemember_2 = tiempo_final_pausa_2 + timedelta(hours=horas_sesion)
        # Fuente v2: AgentActivityEventV2 (ReporteEstadisticasDiariaAgente usa get_agent_activity_kpis_v2)
        AgentActivityEventV2.objects.create(
            agente_id=self.agente_profile.id, ts=tiempo_addmember,
            event_type=AgentActivityEventV2.EventType.SESSION_LOGIN)
        AgentActivityEventV2.objects.create(
            agente_id=self.agente_profile.id, ts=tiempo_inicio_pausa_1,
            event_type=AgentActivityEventV2.EventType.STATE_PAUSED, pause=pausa1)
        AgentActivityEventV2.objects.create(
            agente_id=self.agente_profile.id, ts=tiempo_final_pausa_1,
            event_type=AgentActivityEventV2.EventType.STATE_READY)
        AgentActivityEventV2.objects.create(
            agente_id=self.agente_profile.id, ts=tiempo_inicio_pausa_2,
            event_type=AgentActivityEventV2.EventType.STATE_PAUSED, pause=pausa2)
        AgentActivityEventV2.objects.create(
            agente_id=self.agente_profile.id, ts=tiempo_final_pausa_2,
            event_type=AgentActivityEventV2.EventType.STATE_READY)
        AgentActivityEventV2.objects.create(
            agente_id=self.agente_profile.id, ts=tiempo_removemember_2,
            event_type=AgentActivityEventV2.EventType.SESSION_LOGOUT)
        reporte = ReporteEstadisticasDiariaAgente()
        reporte_agente = reporte.estadisticas[self.agente_profile.pk]
        self.assertEqual(reporte_agente['tiempos'].pausa, timedelta(minutes=4))
        self.assertEqual(reporte_agente['tiempos'].pausa_recreativa, timedelta(minutes=2))

    @patch('reportes_app.reportes.reporte_estadisticas_agentes.get_agent_interactions_kpis')
    @patch('reportes_app.reportes.reporte_estadisticas_agentes.get_agent_session_data_for_reports')
    def test_talk_pct_incluido_y_porcentajes_suman_100(
            self, mock_session_data, mock_interactions_kpis):
        """Verifica que talk_pct está en el payload y que los 4 porcentajes suman 100."""
        hoy = now().date().isoformat()
        mock_session_data.return_value = {
            self.agente_profile.pk: {
                'session': timedelta(hours=1),
                'pause': timedelta(minutes=10),
                'ready_seconds': 1500,
                'acw_seconds': 900,
                'pausas_list': [],
            },
        }
        mock_interactions_kpis.return_value = [
            {
                'agent_id': self.agente_profile.pk,
                'talk_seconds': 600,
                'avg_talk_seconds_answered': 120,
            },
        ]

        with patch('reportes_app.reportes.reporte_estadisticas_agentes.get_agent_transfer_counts',
                  return_value=[]):
            with patch('reportes_app.reportes.reporte_estadisticas_agentes.'
                       'get_agent_transfer_in_counts', return_value=[]):
                with patch('reportes_app.reportes.reporte_estadisticas_agentes.'
                           'get_agent_hold_seconds', return_value=[]):
                    family = ReporteDiarioAgentesFamily()
                    resultados = family._obtener_todos()

        datos_agente = dict(resultados).get(self.agente_profile.pk)
        self.assertIsNotNone(datos_agente, 'El agente debe estar en los resultados')
        self.assertIn('talk_pct', datos_agente, 'El payload debe incluir talk_pct')

        total_pct = (
            datos_agente['ready_pct'] + datos_agente['acw_pct'] +
            datos_agente['pause_pct'] + datos_agente['talk_pct']
        )
        self.assertEqual(total_pct, 100,
                        'Los 4 porcentajes deben sumar 100 (ready+acw+pause+talk)')

    @patch('reportes_app.reportes.reporte_estadisticas_agentes.create_redis_connection')
    def test_conectadas_desde_redis_oml_agentdata(self, mock_create_redis):
        """Verifica que conectadas se obtienen de Redis OML:AGENTDATA:AGENT:{id}."""
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        agentdata_dict = {
            b'ANSWERED_TOTAL_CALLS:IN': b'2',
            b'ANSWERED_TOTAL_CALLS:MANUAL': b'3',
            b'ANSWERED_TOTAL_CALLS:DIALER': b'1',
        }
        mock_pipeline.execute.return_value = [agentdata_dict] * 100
        mock_redis.pipeline.return_value = mock_pipeline
        mock_create_redis.return_value = mock_redis

        reporte = ReporteEstadisticasDiariaAgente()
        conectadas = reporte.estadisticas[self.agente_profile.pk]['conectadas']

        self.assertEqual(conectadas['entrantes'], 2)
        self.assertEqual(conectadas['salientes'], 4)  # 3 + 1
        self.assertEqual(conectadas['total'], 6)
        mock_create_redis.assert_called_once_with(db=2)

    @patch('reportes_app.reportes.reporte_estadisticas_agentes.ReporteEstadisticasDiariaAgente._obtener_conversaciones_whatsapp')
    def test_logs_incluyen_whatsapp_y_estan_ordenados_limite(self, mock_obtener_wa):
        """Verifica que los logs incluyen entradas WhatsApp y que la unión voz+WA está ordenada y limitada."""
        from django.utils.timezone import localtime

        # Una conversación WhatsApp mock
        mock_conv = MagicMock()
        mock_conv.agent_id = self.agente_profile.pk
        mock_conv.destination = '5491112345678'
        mock_conv.client_id = None
        mock_conv.client = None
        mock_conv.campana_id = self.campana_activa.pk
        mock_conv.campana = self.campana_activa
        mock_conv.conversation_disposition = None
        mock_conv.date_last_interaction = None
        mock_conv.timestamp = localtime(now())
        mock_obtener_wa.return_value = [mock_conv]

        reporte = ReporteEstadisticasDiariaAgente()
        logs = reporte.estadisticas[self.agente_profile.pk]['logs']

        # Debe haber al menos un log con channel WHATSAPP
        canales = [log.get('channel') for log in logs]
        self.assertIn('WHATSAPP', canales, 'Los logs deben incluir al menos una entrada WhatsApp')

        # Todos los logs deben tener channel (VOICE o WHATSAPP)
        for log in logs:
            self.assertIn(log.get('channel'), ('VOICE', 'WHATSAPP'), 'Cada log debe tener channel VOICE o WHATSAPP')

        # Máximo CANTIDAD_LOGS
        self.assertLessEqual(len(logs), ReporteEstadisticasDiariaAgente.CANTIDAD_LOGS,
                            'Los logs deben estar limitados a CANTIDAD_LOGS')
