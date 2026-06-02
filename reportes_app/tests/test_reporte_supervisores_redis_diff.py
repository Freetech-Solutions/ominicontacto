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

import json

from mock import MagicMock, patch

from ominicontacto_app.tests.utiles import OMLBaseTest
from reportes_app.reportes.reporte_supervisores import ReporteSupervisoresFamily


class ReporteSupervisoresRedisDiffTest(OMLBaseTest):

    def _metadata(self, grupo, campanas):
        return json.dumps({'grupo': grupo, 'campana': campanas})

    def _build_family(self, reporte_resultado, redis_state=None, existing_scan_keys=None):
        """
        redis_state: {supervisor_id: {agent_id: metadata_json}}
        existing_scan_keys: {supervisor_id: redis_key} — claves ya presentes en Redis
        """
        family = ReporteSupervisoresFamily(redis_connection=MagicMock())
        family.reporte_resultado = reporte_resultado

        redis_state = redis_state or {}
        existing_scan_keys = existing_scan_keys or {
            supervisor_id: 'OML:SUPERVISOR:{0}'.format(supervisor_id)
            for supervisor_id in redis_state
        }

        def hgetall_side_effect(key):
            prefix = 'OML:SUPERVISOR:'
            if key.startswith(prefix):
                supervisor_id = int(key[len(prefix):])
                return dict(redis_state.get(supervisor_id, {}))
            return {}

        read_pipeline = MagicMock()
        write_pipeline = MagicMock()
        pipeline_calls = {'count': 0}

        def pipeline_factory():
            pipeline_calls['count'] += 1
            if pipeline_calls['count'] == 1:
                return read_pipeline
            return write_pipeline

        family.redis_connection.pipeline.side_effect = pipeline_factory
        family.redis_connection.hgetall.side_effect = hgetall_side_effect

        read_results = []
        for supervisor_id, _ in sorted(reporte_resultado, key=lambda item: item[0]):
            read_results.append(dict(redis_state.get(supervisor_id, {})))
        read_pipeline.execute.return_value = read_results

        def scan_side_effect(index, pattern):
            keys = list(existing_scan_keys.values())
            return (0, keys)

        family.redis_connection.scan.side_effect = scan_side_effect

        return family, write_pipeline

    def test_sin_cambios_no_ejecuta_pipeline_de_escritura(self):
        metadata = self._metadata('Grupo A', ['Campana 1', 'Campana 2'])
        reporte_resultado = [(1, {10: metadata})]
        redis_state = {1: {'10': metadata}}
        family, write_pipeline = self._build_family(reporte_resultado, redis_state)

        family._sync_families_to_redis()

        write_pipeline.execute.assert_not_called()
        write_pipeline.hset.assert_not_called()
        write_pipeline.hdel.assert_not_called()
        write_pipeline.delete.assert_not_called()

    def test_orden_distinto_de_campanas_no_genera_escrituras(self):
        metadata_nuevo = self._metadata('Grupo A', ['Campana 2', 'Campana 1'])
        metadata_actual = self._metadata('Grupo A', ['Campana 1', 'Campana 2'])
        reporte_resultado = [(1, {10: metadata_nuevo})]
        redis_state = {1: {'10': metadata_actual}}
        family, write_pipeline = self._build_family(reporte_resultado, redis_state)

        family._sync_families_to_redis()

        write_pipeline.execute.assert_not_called()

    def test_agente_nuevo_genera_hset(self):
        metadata_existente = self._metadata('Grupo A', ['Campana 1'])
        metadata_nuevo = self._metadata('Grupo B', ['Campana 2'])
        reporte_resultado = [(1, {10: metadata_existente, 20: metadata_nuevo})]
        redis_state = {1: {'10': metadata_existente}}
        family, write_pipeline = self._build_family(reporte_resultado, redis_state)

        family._sync_families_to_redis()

        write_pipeline.hset.assert_called_once_with(
            'OML:SUPERVISOR:1', mapping={'20': metadata_nuevo})
        write_pipeline.execute.assert_called_once()

    def test_agente_desasignado_genera_hdel(self):
        metadata = self._metadata('Grupo A', ['Campana 1'])
        reporte_resultado = [(1, {10: metadata})]
        redis_state = {1: {'10': metadata, '20': self._metadata('Grupo B', ['Campana 2'])}}
        family, write_pipeline = self._build_family(reporte_resultado, redis_state)

        family._sync_families_to_redis()

        write_pipeline.hdel.assert_called_once_with('OML:SUPERVISOR:1', '20')
        write_pipeline.execute.assert_called_once()

    def test_cambio_de_grupo_genera_hset(self):
        metadata_nuevo = self._metadata('Grupo Nuevo', ['Campana 1'])
        metadata_actual = self._metadata('Grupo Viejo', ['Campana 1'])
        reporte_resultado = [(1, {10: metadata_nuevo})]
        redis_state = {1: {'10': metadata_actual}}
        family, write_pipeline = self._build_family(reporte_resultado, redis_state)

        family._sync_families_to_redis()

        write_pipeline.hset.assert_called_once_with(
            'OML:SUPERVISOR:1', mapping={'10': metadata_nuevo})
        write_pipeline.execute.assert_called_once()

    def test_supervisor_huerfano_genera_del(self):
        reporte_resultado = [(1, {10: self._metadata('Grupo A', ['Campana 1'])})]
        redis_state = {1: {'10': self._metadata('Grupo A', ['Campana 1'])}}
        existing_scan_keys = {
            1: 'OML:SUPERVISOR:1',
            2: 'OML:SUPERVISOR:2',
        }
        family, write_pipeline = self._build_family(
            reporte_resultado, redis_state, existing_scan_keys)

        family._sync_families_to_redis()

        write_pipeline.delete.assert_called_once_with('OML:SUPERVISOR:2')
        write_pipeline.execute.assert_called_once()

    def test_supervisor_nuevo_genera_hset_completo(self):
        metadata_10 = self._metadata('Grupo A', ['Campana 1'])
        metadata_20 = self._metadata('Grupo B', ['Campana 2'])
        reporte_resultado = [(5, {10: metadata_10, 20: metadata_20})]
        family, write_pipeline = self._build_family(reporte_resultado, redis_state={})

        family._sync_families_to_redis()

        write_pipeline.hset.assert_called_once_with(
            'OML:SUPERVISOR:5',
            mapping={'10': metadata_10, '20': metadata_20})
        write_pipeline.execute.assert_called_once()

    def test_multiples_supervisores_solo_uno_mutado(self):
        metadata = self._metadata('Grupo A', ['Campana 1'])
        metadata_nuevo = self._metadata('Grupo B', ['Campana 2'])
        reporte_resultado = [
            (1, {10: metadata}),
            (2, {20: metadata_nuevo}),
        ]
        redis_state = {
            1: {'10': metadata},
            2: {'20': metadata},
        }
        existing_scan_keys = {
            1: 'OML:SUPERVISOR:1',
            2: 'OML:SUPERVISOR:2',
        }
        family, write_pipeline = self._build_family(
            reporte_resultado, redis_state, existing_scan_keys)

        family._sync_families_to_redis()

        write_pipeline.hset.assert_called_once_with(
            'OML:SUPERVISOR:2', mapping={'20': metadata_nuevo})
        write_pipeline.hdel.assert_not_called()
        write_pipeline.delete.assert_not_called()
        write_pipeline.execute.assert_called_once()

    @patch.object(ReporteSupervisoresFamily, '_obtener_resultado')
    def test_regenerar_families_usa_sync_diferencial(self, obtener_resultado_mock):
        metadata = self._metadata('Grupo A', ['Campana 1'])
        obtener_resultado_mock.return_value = [(1, {10: metadata})]
        family = ReporteSupervisoresFamily(redis_connection=MagicMock())

        with patch.object(family, '_sync_families_to_redis') as sync_mock:
            family.regenerar_families()

        sync_mock.assert_called_once()
        self.assertEqual(family.reporte_resultado, [(1, {10: metadata})])

    def test_regenerar_family_sincroniza_un_supervisor(self):
        metadata = self._metadata('Grupo A', ['Campana 1'])
        family = ReporteSupervisoresFamily(redis_connection=MagicMock())

        with patch.object(family, '_sync_single_family_to_redis') as sync_mock:
            family.regenerar_family((3, {10: metadata}))

        sync_mock.assert_called_once_with((3, {10: metadata}))
