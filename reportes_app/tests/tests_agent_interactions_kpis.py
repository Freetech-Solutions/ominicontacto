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

from mock import patch
from django.utils import timezone

from ominicontacto_app.tests.utiles import OMLBaseTest
from ominicontacto_app.tests.factories import AgenteProfileFactory
from reportes_app.services.agent_interactions_kpis import (
    _get_agent_whatsapp_act_avg,
    get_agent_interactions_kpis,
)
from whatsapp_app.tests.factories import ConversacionFactory


class AgentInteractionsKpisWhatsappMergeTests(OMLBaseTest):
    def test_mergea_voz_y_whatsapp_en_in_out_sin_tocar_total(self):
        agent = AgenteProfileFactory()
        now_ts = timezone.now()

        ConversacionFactory.create(agent=agent, saliente=False, timestamp=now_ts)
        ConversacionFactory.create(agent=agent, saliente=True, timestamp=now_ts)
        ConversacionFactory.create(agent=agent, saliente=True, timestamp=now_ts)

        voice_rows = [{
            'agent_id': agent.id,
            'interactions_total': 5,
            'interactions_inbound': 2,
            'interactions_outbound': 1,
            'answered_count': 4,
            'cancel_count': 0,
            'sales_count': 1,
            'talk_seconds': 120.0,
            'avg_talk_seconds_answered': 30.0,
            'wait_conn_duration': 20.0,
            'avg_wait_conn_duration': 5.0,
        }]

        with patch(
            'reportes_app.services.agent_interactions_kpis._get_agent_voice_interactions_kpis',
            return_value=voice_rows,
        ):
            rows = get_agent_interactions_kpis(
                since=now_ts - timezone.timedelta(hours=1),
                until=now_ts + timezone.timedelta(hours=1),
                agent_id=None,
                group_by='agent',
                channel_type='VOICE',
                include_whatsapp_in_out=True,
            )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['interactions_total'], 5)
        self.assertEqual(row['interactions_inbound'], 3)  # voz 2 + wa 1
        self.assertEqual(row['interactions_outbound'], 3)  # voz 1 + wa 2
        self.assertEqual(row['interactions_inbound_voice'], 2)
        self.assertEqual(row['interactions_outbound_voice'], 1)
        self.assertEqual(row['interactions_inbound_chat'], 1)
        self.assertEqual(row['interactions_outbound_chat'], 2)
        self.assertEqual(row['talk_seconds'], 120.0)

    def test_crea_fila_con_solo_whatsapp_si_no_hay_voz(self):
        agent = AgenteProfileFactory()
        now_ts = timezone.now()

        ConversacionFactory.create(agent=agent, saliente=False, timestamp=now_ts)
        ConversacionFactory.create(agent=agent, saliente=False, timestamp=now_ts)
        ConversacionFactory.create(agent=agent, saliente=True, timestamp=now_ts)

        with patch(
            'reportes_app.services.agent_interactions_kpis._get_agent_voice_interactions_kpis',
            return_value=[],
        ):
            rows = get_agent_interactions_kpis(
                since=now_ts - timezone.timedelta(hours=1),
                until=now_ts + timezone.timedelta(hours=1),
                agent_id=None,
                group_by='agent',
                channel_type='VOICE',
                include_whatsapp_in_out=True,
            )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['agent_id'], agent.id)
        self.assertEqual(row['interactions_total'], 0)
        self.assertEqual(row['interactions_inbound'], 2)
        self.assertEqual(row['interactions_outbound'], 1)
        self.assertEqual(row['interactions_inbound_voice'], 0)
        self.assertEqual(row['interactions_outbound_voice'], 0)
        self.assertEqual(row['interactions_inbound_chat'], 2)
        self.assertEqual(row['interactions_outbound_chat'], 1)
        self.assertEqual(row['answered_count'], 0)
        self.assertEqual(row['cancel_count'], 0)

    def test_respeta_rango_y_filtro_de_agente_para_whatsapp(self):
        agent_in = AgenteProfileFactory()
        agent_other = AgenteProfileFactory()
        now_ts = timezone.now()

        # Dentro de rango y agente filtrado
        ConversacionFactory.create(
            agent=agent_in,
            saliente=False,
            timestamp=now_ts - timezone.timedelta(minutes=5),
        )
        ConversacionFactory.create(
            agent=agent_in,
            saliente=True,
            timestamp=now_ts + timezone.timedelta(minutes=5),
        )
        # Fuera de rango
        ConversacionFactory.create(
            agent=agent_in,
            saliente=False,
            timestamp=now_ts + timezone.timedelta(days=2),
        )
        # Otro agente
        ConversacionFactory.create(
            agent=agent_other,
            saliente=False,
            timestamp=now_ts,
        )

        with patch(
            'reportes_app.services.agent_interactions_kpis._get_agent_voice_interactions_kpis',
            return_value=[],
        ):
            rows = get_agent_interactions_kpis(
                since=now_ts - timezone.timedelta(hours=1),
                until=now_ts + timezone.timedelta(hours=1),
                agent_id=agent_in.id,
                group_by='agent',
                channel_type='VOICE',
                include_whatsapp_in_out=True,
            )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['agent_id'], agent_in.id)
        self.assertEqual(row['interactions_inbound'], 1)
        self.assertEqual(row['interactions_outbound'], 1)
        self.assertEqual(row['interactions_inbound_voice'], 0)
        self.assertEqual(row['interactions_outbound_voice'], 0)
        self.assertEqual(row['interactions_inbound_chat'], 1)
        self.assertEqual(row['interactions_outbound_chat'], 1)


class AgentInteractionsKpisWhatsappActTests(OMLBaseTest):
    def test_act_promedio_por_agente_excluye_reglas_invalidas(self):
        agent = AgenteProfileFactory()
        now_ts = timezone.now()
        since = now_ts - timezone.timedelta(hours=1)
        until = now_ts + timezone.timedelta(hours=1)

        # Válidas: 60s y 180s => promedio 120s
        ConversacionFactory.create(
            agent=agent,
            atendida=True,
            saliente=False,
            timestamp=now_ts - timezone.timedelta(minutes=10),
            date_last_interaction=now_ts - timezone.timedelta(minutes=9),
        )
        ConversacionFactory.create(
            agent=agent,
            atendida=True,
            saliente=True,
            timestamp=now_ts - timezone.timedelta(minutes=8),
            date_last_interaction=now_ts - timezone.timedelta(minutes=5),
        )

        # Fuera de rango
        ConversacionFactory.create(
            agent=agent,
            atendida=True,
            timestamp=now_ts + timezone.timedelta(days=2),
            date_last_interaction=now_ts + timezone.timedelta(days=2, minutes=2),
        )
        # No atendida
        ConversacionFactory.create(
            agent=agent,
            atendida=False,
            timestamp=now_ts - timezone.timedelta(minutes=7),
            date_last_interaction=now_ts - timezone.timedelta(minutes=6),
        )
        # Sin date_last_interaction
        ConversacionFactory.create(
            agent=agent,
            atendida=True,
            timestamp=now_ts - timezone.timedelta(minutes=6),
            date_last_interaction=None,
        )
        # Duración negativa
        ConversacionFactory.create(
            agent=agent,
            atendida=True,
            timestamp=now_ts - timezone.timedelta(minutes=4),
            date_last_interaction=now_ts - timezone.timedelta(minutes=5),
        )

        rows = _get_agent_whatsapp_act_avg(since=since, until=until, agent_id=None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['agent_id'], agent.id)
        self.assertAlmostEqual(rows[0]['act_avg'], 120.0, places=3)

    def test_act_respeta_filtro_por_agente(self):
        agent_in = AgenteProfileFactory()
        agent_out = AgenteProfileFactory()
        now_ts = timezone.now()
        since = now_ts - timezone.timedelta(hours=1)
        until = now_ts + timezone.timedelta(hours=1)

        ConversacionFactory.create(
            agent=agent_in,
            atendida=True,
            timestamp=now_ts - timezone.timedelta(minutes=10),
            date_last_interaction=now_ts - timezone.timedelta(minutes=8),
        )
        ConversacionFactory.create(
            agent=agent_out,
            atendida=True,
            timestamp=now_ts - timezone.timedelta(minutes=9),
            date_last_interaction=now_ts - timezone.timedelta(minutes=4),
        )

        rows = _get_agent_whatsapp_act_avg(
            since=since,
            until=until,
            agent_id=agent_in.id,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['agent_id'], agent_in.id)
        self.assertAlmostEqual(rows[0]['act_avg'], 120.0, places=3)
