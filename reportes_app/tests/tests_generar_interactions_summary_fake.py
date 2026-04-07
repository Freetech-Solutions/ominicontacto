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

"""Tests para el comando generar_interactions_summary_fake."""

from __future__ import unicode_literals

import unittest

from django.core.management import call_command
from django.db import connection

from ominicontacto_app.tests.utiles import OMLBaseTest
from reportes_app.models import InteractionsSummary


FAKE_PREFIX = 'fake-'


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
class GenerarInteractionsSummaryFakeTest(OMLBaseTest):

    def setUp(self):
        super(GenerarInteractionsSummaryFakeTest, self).setUp()
        self.crear_administrador()
        # Limpiar posibles datos fake previos para no afectar conteos
        InteractionsSummary.objects.filter(interaction_id__startswith=FAKE_PREFIX).delete()

    def tearDown(self):
        InteractionsSummary.objects.filter(interaction_id__startswith=FAKE_PREFIX).delete()
        super(GenerarInteractionsSummaryFakeTest, self).tearDown()

    def test_dry_run_no_crea_registros(self):
        count_before = InteractionsSummary.objects.filter(
            interaction_id__startswith=FAKE_PREFIX
        ).count()
        call_command('generar_interactions_summary_fake', '10', '--dry-run')
        count_after = InteractionsSummary.objects.filter(
            interaction_id__startswith=FAKE_PREFIX
        ).count()
        self.assertEqual(count_before, count_after, 'dry-run no debe crear registros')

    def test_crea_registros_con_prefijo_fake(self):
        n = 5
        call_command('generar_interactions_summary_fake', str(n), '--dias', '1')
        created = list(
            InteractionsSummary.objects.filter(
                interaction_id__startswith=FAKE_PREFIX
            ).values_list('interaction_id', flat=True)
        )
        self.assertEqual(len(created), n)
        for iid in created:
            self.assertTrue(
                iid.startswith(FAKE_PREFIX),
                'interaction_id debe empezar por "{}": {}'.format(FAKE_PREFIX, iid),
            )

    def test_clear_borra_solo_fake_y_luego_crea(self):
        call_command('generar_interactions_summary_fake', '3', '--dias', '1')
        self.assertEqual(
            InteractionsSummary.objects.filter(interaction_id__startswith=FAKE_PREFIX).count(),
            3,
        )
        call_command('generar_interactions_summary_fake', '2', '--dias', '1', '--clear')
        created = InteractionsSummary.objects.filter(
            interaction_id__startswith=FAKE_PREFIX
        ).count()
        self.assertEqual(created, 2, '--clear borra los fake previos y se crean solo 2 nuevos')
