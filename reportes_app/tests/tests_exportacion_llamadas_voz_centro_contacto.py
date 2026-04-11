# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

from __future__ import unicode_literals

import csv
import os
import shutil
import tempfile

from django.test import SimpleTestCase

from mock import patch

from reportes_app.services.exportacion_llamadas_voz_centro_contacto import (
    DIRECTORIO_REPORTE,
    PREFIJO_ARCHIVO,
    generar_csv_llamadas_voz_centro_contacto,
    obtener_url_descarga_llamadas_voz,
)


class ExportacionLlamadasVozCentroContactoServiceTest(SimpleTestCase):
    def setUp(self):
        super(ExportacionLlamadasVozCentroContactoServiceTest, self).setUp()
        self.media_root = tempfile.mkdtemp(prefix='oml_media_llamadas_voz_cc_csv_')

    def tearDown(self):
        shutil.rmtree(self.media_root, ignore_errors=True)
        super(ExportacionLlamadasVozCentroContactoServiceTest, self).tearDown()

    @patch('reportes_app.services.exportacion_llamadas_voz_centro_contacto.redis.Redis')
    @patch('api_app.views.reports_centro_contacto.obtener_llamadas_por_campana')
    def test_genera_csv_con_transfer_in_out_y_totales(
            self, mock_obtener_llamadas_por_campana, mock_redis_cls):
        mock_obtener_llamadas_por_campana.return_value = [
            {
                'campaign_name': 'Campaña Uno',
                'received': 10,
                'answered': 8,
                'expired': 1,
                'abandoned': 1,
                'transferred': 3,
                'transfer_in_count': 2,
                'transfer_out_count': 3,
                'avg_wait_seconds': 12,
                'avg_talk_seconds': 45,
                'pct_answered': 80.0,
                'pct_expired': 10.0,
                'pct_abandoned': 10.0,
            },
            {
                'campaign_name': 'Campaña Dos',
                'received': 0,
                'answered': 0,
                'expired': 0,
                'abandoned': 0,
                'transferred': 0,
                'transfer_in_count': 1,
                'transfer_out_count': 0,
                'avg_wait_seconds': None,
                'avg_talk_seconds': None,
                'pct_answered': 0.0,
                'pct_expired': 0.0,
                'pct_abandoned': 0.0,
            },
        ]
        redis_conn = mock_redis_cls.return_value
        task_id = 'taskcsvvoz001'
        key_task = 'OML:STATUS_CSV_REPORT:LLAMADAS_VOZ_CC:cc:{0}'.format(task_id)

        with self.settings(MEDIA_ROOT=self.media_root, MEDIA_URL='/media/'):
            generar_csv_llamadas_voz_centro_contacto(
                key_task=key_task,
                task_id=task_id,
                start_date=None,
                end_date=None,
                allowed_campaigns=[1, 2],
                visible_campaigns=[1, 2, 3],
            )

            redis_conn.publish.assert_any_call(key_task, 0)
            redis_conn.publish.assert_any_call(key_task, 100)
            self.assertEqual(
                mock_obtener_llamadas_por_campana.call_args[1]['visible_campaigns'],
                [1, 2, 3],
            )

            filepath = os.path.join(
                self.media_root,
                DIRECTORIO_REPORTE,
                '{0}_{1}.csv'.format(PREFIJO_ARCHIVO, task_id),
            )
            self.assertTrue(os.path.exists(filepath))

            with open(filepath, 'r', newline='', encoding='utf-8') as csv_file:
                rows = list(csv.reader(csv_file))

            self.assertEqual(
                rows[0],
                [
                    'Campaña', 'Recibidas', 'Respondidas', 'Expiradas', 'Abandonadas',
                    'Transfer In', 'Transfer Out', 'Espera prom.', 'Habla prom.',
                    '% Respondidas', '% Expiradas', '% Abandonadas',
                ],
            )
            self.assertNotIn('Transferidas', rows[0])
            self.assertEqual(rows[1][5], '2')
            self.assertEqual(rows[1][6], '3')
            self.assertEqual(rows[2][5], '1')
            self.assertEqual(rows[2][6], '0')

            totals = rows[-1]
            self.assertEqual(totals[0], 'Total')
            self.assertEqual(totals[5], '3')
            self.assertEqual(totals[6], '3')

            download_url = obtener_url_descarga_llamadas_voz(task_id)
            self.assertEqual(
                download_url,
                '/media/{0}/{1}_{2}.csv'.format(DIRECTORIO_REPORTE, PREFIJO_ARCHIVO, task_id),
            )
