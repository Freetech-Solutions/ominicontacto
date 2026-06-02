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

import json

from ominicontacto_app.models import Campana, AgenteProfile, SupervisorProfile, QueueMember
from ominicontacto_app.services.asterisk.redis_database import AbstractRedisFamily


class ReporteSupervisores(object):

    def __init__(self):
        self.estadisticas = {}
        self.calcular_datos_de_agentes_asignados_por_supervisor()

    def calcular_datos_de_agentes_asignados_por_supervisor(self):

        nombres_campanas = dict(Campana.objects.obtener_all_dialplan_asterisk().values_list(
            'id', 'nombre'))
        agentes_por_campana = {}
        for id_campana in nombres_campanas.keys():
            agentes_por_campana[id_campana] = set()

        # Obtengo los datos de cada agente
        datos_por_agente = {}
        # Grupo
        grupos_de_agentes = AgenteProfile.objects.obtener_activos().values('id', 'grupo__nombre')
        for grupo_de_agente in grupos_de_agentes:
            datos_por_agente[grupo_de_agente['id']] = {
                'grupo': grupo_de_agente['grupo__nombre'],
                'campana': []
            }
        # Nombres de campañas a la que esta asignado
        asignaciones_agentes = QueueMember.objects.values('member_id', 'queue_name__campana_id')
        for asignacion in asignaciones_agentes:
            id_campana = asignacion['queue_name__campana_id']
            id_agente = asignacion['member_id']
            if id_campana in nombres_campanas and id_agente in datos_por_agente:
                datos_por_agente[id_agente]['campana'].append(nombres_campanas[id_campana])
                agentes_por_campana[id_campana].add(id_agente)

        # Los administradores tendran asignados a todos los agentes
        administradores = []
        agentes_por_supervisor = {}
        supervisores = SupervisorProfile.objects.using('replica').filter(
            borrado=False, user__is_active=True, user__borrado=False)
        for supervisor in supervisores:
            if supervisor.is_administrador:
                administradores.append(supervisor.id)
            else:
                agentes_por_supervisor[supervisor.id] = set()

        # Calculo ids de agentes asociados a supervisores a traves de campañas
        asignaciones_campanas = Campana.objects.obtener_all_dialplan_asterisk().values(
            'id', 'supervisors__supervisorprofile')
        for asignacion in asignaciones_campanas:
            id_campana = asignacion['id']
            id_supervisor = asignacion['supervisors__supervisorprofile']
            if id_supervisor in agentes_por_supervisor:
                agentes_por_supervisor[id_supervisor].update(agentes_por_campana[id_campana])

        # Para cada supervisor asigno los datos completos de sus agentes asignados
        for id_supervisor, ids_agentes in agentes_por_supervisor.items():
            if ids_agentes:
                self.estadisticas[id_supervisor] = {}
                for id_agente in ids_agentes:
                    self.estadisticas[id_supervisor][id_agente] = datos_por_agente[id_agente]

        # Completo los datos de todos los agentes para todos los administradores
        for id_administrador in administradores:
            self.estadisticas[id_administrador] = datos_por_agente


class ReporteSupervisoresFamily(AbstractRedisFamily):

    def _create_dict(self, family_member):
        return family_member[1]

    def _obtener_todos(self):
        return self.reporte_resultado

    def _obtener_resultado(self):
        reporte_resultado = []
        reporte = ReporteSupervisores()
        for (supervisor_id, datos) in reporte.estadisticas.items():
            datos_json = {}
            for agente_id, dato in datos.items():
                datos_json[agente_id] = json.dumps(dato)
            reporte_resultado.append((supervisor_id, datos_json))
        return reporte_resultado

    def _get_nombre_family(self, family_member):
        return "{0}:{1}".format(self.get_nombre_families(), family_member[0])

    def get_nombre_families(self):
        return "OML:SUPERVISOR"

    def _supervisor_redis_key(self, supervisor_id):
        return "{0}:{1}".format(self.get_nombre_families(), supervisor_id)

    def _build_dict_nuevo(self):
        result = {}
        for supervisor_id, datos_json in self.reporte_resultado:
            result[supervisor_id] = {
                str(agent_id): metadata for agent_id, metadata in datos_json.items()
            }
        return result

    def _normalize_redis_hash(self, raw):
        if not raw:
            return {}
        return {str(field): value for field, value in raw.items()}

    def _parse_metadata(self, metadata_json):
        data = json.loads(metadata_json)
        return data.get('grupo'), sorted(data.get('campana', []))

    def _metadata_semantically_equal(self, metadata_a, metadata_b):
        try:
            return self._parse_metadata(metadata_a) == self._parse_metadata(metadata_b)
        except (ValueError, TypeError):
            return metadata_a == metadata_b

    def _compute_supervisor_diff(self, dict_actual, dict_nuevo):
        hset_mapping = {}
        hdel_fields = []

        for agent_id, metadata in dict_nuevo.items():
            agent_id_str = str(agent_id)
            actual_value = dict_actual.get(agent_id_str)
            if actual_value is None or not self._metadata_semantically_equal(actual_value, metadata):
                hset_mapping[agent_id_str] = metadata

        dict_nuevo_keys = {str(agent_id) for agent_id in dict_nuevo}
        for agent_id in dict_actual:
            if agent_id not in dict_nuevo_keys:
                hdel_fields.append(agent_id)

        return hset_mapping, hdel_fields

    def _scan_supervisor_keys(self):
        redis_connection = self.get_redis_connection()
        pattern = self._get_families_pattern()
        prefix = "{0}:".format(self.get_nombre_families())
        existing = {}
        index = 0
        while True:
            index, keys = redis_connection.scan(index, pattern)
            for key in keys:
                supervisor_id = int(key[len(prefix):])
                existing[supervisor_id] = key
            if index == 0:
                break
        return existing

    def _apply_supervisor_diff(self, write_pipe, supervisor_id, dict_actual, dict_nuevo):
        key = self._supervisor_redis_key(supervisor_id)
        if not dict_nuevo:
            if dict_actual:
                write_pipe.delete(key)
                return True
            return False

        hset_mapping, hdel_fields = self._compute_supervisor_diff(dict_actual, dict_nuevo)
        has_writes = False
        if hset_mapping:
            write_pipe.hset(key, mapping=hset_mapping)
            has_writes = True
        if hdel_fields:
            write_pipe.hdel(key, *hdel_fields)
            has_writes = True
        return has_writes

    def _sync_families_to_redis(self):
        redis_connection = self.get_redis_connection()
        dict_nuevo_by_supervisor = self._build_dict_nuevo()
        supervisor_ids_nuevo = sorted(dict_nuevo_by_supervisor.keys())

        read_pipe = redis_connection.pipeline()
        for supervisor_id in supervisor_ids_nuevo:
            read_pipe.hgetall(self._supervisor_redis_key(supervisor_id))
        read_results = read_pipe.execute() if supervisor_ids_nuevo else []

        existing_keys = self._scan_supervisor_keys()
        write_pipe = redis_connection.pipeline()
        has_writes = False

        for idx, supervisor_id in enumerate(supervisor_ids_nuevo):
            dict_nuevo = dict_nuevo_by_supervisor[supervisor_id]
            dict_actual = self._normalize_redis_hash(read_results[idx])
            if self._apply_supervisor_diff(write_pipe, supervisor_id, dict_actual, dict_nuevo):
                has_writes = True

        for supervisor_id, redis_key in existing_keys.items():
            if supervisor_id not in dict_nuevo_by_supervisor:
                write_pipe.delete(redis_key)
                has_writes = True

        if has_writes:
            write_pipe.execute()

    def _sync_single_family_to_redis(self, family_member):
        supervisor_id = family_member[0]
        datos_json = family_member[1]
        dict_nuevo = {str(agent_id): metadata for agent_id, metadata in datos_json.items()}

        redis_connection = self.get_redis_connection()
        key = self._supervisor_redis_key(supervisor_id)
        dict_actual = self._normalize_redis_hash(redis_connection.hgetall(key))

        write_pipe = redis_connection.pipeline()
        if self._apply_supervisor_diff(write_pipe, supervisor_id, dict_actual, dict_nuevo):
            write_pipe.execute()

    def regenerar_families(self):
        """Sincroniza families en Redis aplicando solo cambios diferenciales."""
        self.reporte_resultado = self._obtener_resultado()
        self._sync_families_to_redis()

    def regenerar_family(self, family_member):
        """Sincroniza una family en Redis aplicando solo cambios diferenciales."""
        self._sync_single_family_to_redis(family_member)
