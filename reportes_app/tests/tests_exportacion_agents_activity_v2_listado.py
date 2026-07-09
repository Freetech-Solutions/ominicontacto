# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

from __future__ import unicode_literals

import csv
import os
import shutil
import tempfile

from django.test import SimpleTestCase

from mock import patch

from reportes_app.services.exportacion_agents_activity_v2_listado import (
    DIRECTORIO_REPORTE,
    PREFIJO_ARCHIVO,
    generar_csv_agents_activity_v2_listado,
    obtener_url_descarga_agents_activity_v2_listado,
)


class ExportacionAgentsActivityV2ListadoServiceTest(SimpleTestCase):
    def setUp(self):
        super(ExportacionAgentsActivityV2ListadoServiceTest, self).setUp()
        self.media_root = tempfile.mkdtemp(prefix='oml_media_agents_activity_csv_')

    def tearDown(self):
        shutil.rmtree(self.media_root, ignore_errors=True)
        super(ExportacionAgentsActivityV2ListadoServiceTest, self).tearDown()

    @patch('reportes_app.services.exportacion_agents_activity_v2_listado.redis.Redis')
    @patch('api_app.views.reports_agent_activity_v2.get_agents_activity_v2_flat_rows')
    def test_genera_csv_con_total_y_progreso_redis(
        self,
        mock_get_rows,
        mock_redis_cls,
    ):
        mock_get_rows.return_value = [
            {
                'agent_name': 'Agente Uno',
                'agent_id': 1,
                'session_seconds': 3600,
                'ready_seconds': 1800,
                'ready_pct': 50.0,
                'pause_seconds': 900,
                'pause_pct': 25.0,
                'acw_seconds': 900,
                'acw_pct': 25.0,
                'total_interactions': 20,
                'gestiones_count': 18,
                'inbound_count': 11,
                'outbound_count': 9,
                'conversation_seconds': 600,
                'tmo_avg': 120,
                'act_avg': 60,
                'transfer_in_count': 2,
                'transfer_out_count': 3,
                'hold_count': 4,
            },
            {
                'agent_name': 'Agente Dos',
                'agent_id': 2,
                'session_seconds': 1800,
                'ready_seconds': 900,
                'ready_pct': 50.0,
                'pause_seconds': 300,
                'pause_pct': 16.7,
                'acw_seconds': 600,
                'acw_pct': 33.3,
                'total_interactions': 10,
                'gestiones_count': 9,
                'inbound_count': 6,
                'outbound_count': 4,
                'conversation_seconds': 300,
                'tmo_avg': 90,
                'act_avg': 45,
                'transfer_in_count': 1,
                'transfer_out_count': 1,
                'hold_count': 2,
            },
        ]
        redis_conn = mock_redis_cls.return_value

        task_id = 'taskcsv001'
        key_task = 'OML:STATUS_CSV_REPORT:AGENTS_ACTIVITY_LISTADO:cc:{0}'.format(task_id)

        with self.settings(MEDIA_ROOT=self.media_root, MEDIA_URL='/media/'):
            generar_csv_agents_activity_v2_listado(
                key_task=key_task,
                task_id=task_id,
                date_start=None,
                date_end=None,
                allowed_agent_ids=[1, 2],
            )

            redis_conn.publish.assert_any_call(key_task, 0)
            redis_conn.publish.assert_any_call(key_task, 100)

            filepath = os.path.join(
                self.media_root,
                DIRECTORIO_REPORTE,
                '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id),
            )
            self.assertTrue(os.path.exists(filepath))

            with open(filepath, 'r', newline='', encoding='utf-8') as csv_file:
                rows = list(csv.reader(csv_file))

            self.assertGreaterEqual(len(rows), 4)
            header = rows[0]
            self.assertEqual(header[0], 'Agente')
            self.assertEqual(header[13], 'Chat In')
            self.assertEqual(header[15], 'Talk Time')
            self.assertEqual(header[16], 'ATT')
            self.assertEqual(header[17], 'ACT')

            first_data = rows[1]
            self.assertEqual(first_data[2], '01:00:00')
            self.assertEqual(first_data[3], '00:30:00')
            self.assertEqual(first_data[15], '00:10:00')
            self.assertEqual(first_data[16], '00:02:00')
            self.assertEqual(first_data[17], '00:01:00')

            totals = rows[-1]
            self.assertEqual(totals[0], 'Total')
            self.assertEqual(totals[2], '01:30:00')
            self.assertEqual(totals[4], '50.0')
            self.assertEqual(totals[6], '22.2')
            self.assertEqual(totals[8], '27.8')
            self.assertEqual(totals[16], '')
            self.assertEqual(totals[17], '')

            download_url = obtener_url_descarga_agents_activity_v2_listado(task_id)
            self.assertEqual(
                download_url,
                '/media/{0}/{1}_{2}.csv'.format(DIRECTORIO_REPORTE, PREFIJO_ARCHIVO, task_id),
            )
