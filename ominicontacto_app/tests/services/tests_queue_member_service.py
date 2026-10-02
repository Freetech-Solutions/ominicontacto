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

from mock import patch, call, MagicMock

from ominicontacto_app.services.asterisk.redis_database import CampaignAgentsFamily
from ominicontacto_app.services.queue_member_service import QueueMemberService
from ominicontacto_app.tests.utiles import OMLBaseTest
from ominicontacto_app.tests.factories import (CampanaFactory, QueueFactory, )


class QueueMemberServiceTests(OMLBaseTest):

    def setUp(self):
        super(QueueMemberServiceTests, self).setUp()
        self.campana1 = CampanaFactory.create()
        self.campana2 = CampanaFactory.create()
        self.queue = QueueFactory.create(campana=self.campana1)
        self.queue2 = QueueFactory.create(campana=self.campana2)
        self.agente1 = self.crear_agente_profile()
        self._hacer_miembro(self.agente1, self.campana1)
        self._hacer_miembro(self.agente1, self.campana2)
        self.agente2 = self.crear_agente_profile()
        self._hacer_miembro(self.agente2, self.campana1)
        self.agente3 = self.crear_agente_profile()
        # Evitar regenerar OML:SUPERVISOR en cada mutación (H3) durante tests unitarios.
        self._supervision_patcher = patch(
            'ominicontacto_app.services.queue_member_service.QueueMemberService'
            '._refrescar_supervision_tras_asignacion')
        self._supervision_patcher.start()
        self.addCleanup(self._supervision_patcher.stop)

    @patch('ominicontacto_app.services.creacion_queue.ActivacionQueueService.activar')
    @patch('ominicontacto_app.services'
           '.queue_member_service.obtener_status_agentes_sesiones_activas')
    @patch('redis.Redis.hdel')
    @patch('redis.Redis.srem')
    @patch('redis.Redis.keys')
    @patch('redis.Redis.delete')
    def test_eliminar_agente_de_colas_asignadas(
            self, delete, keys, srem, hdel, obtener_status_agentes_sesiones_activas, activar):
        obtener_status_agentes_sesiones_activas.return_value = {}
        keys.return_value = []
        service = QueueMemberService()
        self.assertEqual(self.agente1.queue_set.count(), 2)
        keys.side_effect = [
            ['OML:CAMPAIGN-AGENTS:1'],
            ['OML:CAMP:1:MEMBER-PENALTY'],
        ]
        service.eliminar_agente_de_colas_asignadas(self.agente1)
        obtener_status_agentes_sesiones_activas.assert_called()
        keys.assert_any_call('OML:CAMPAIGN-AGENTS:*')
        keys.assert_any_call('OML:CAMP:*:MEMBER-PENALTY')
        delete.assert_any_call('OML:AGENT-CAMPAIGNS:' + str(self.agente1.id))
        srem.assert_called_with('OML:CAMPAIGN-AGENTS:1', self.agente1.id)
        hdel.assert_called_with('OML:CAMP:1:MEMBER-PENALTY', self.agente1.id)
        self.assertEqual(self.agente1.queue_set.count(), 0)

    @patch('ominicontacto_app.services.creacion_queue.ActivacionQueueService.activar')
    @patch('ominicontacto_app.services.queue_member_service.QueueMemberService'
           '._remover_agente_cola_asterisk')
    @patch('ominicontacto_app.services'
           '.queue_member_service.obtener_status_agentes_sesiones_activas')
    @patch('redis.Redis.hdel')
    @patch('redis.Redis.srem')
    @patch('redis.Redis.keys')
    @patch('redis.Redis.delete')
    def test_eliminar_agente_conectado_de_colas_asignadas(
            self, delete, keys, srem, hdel,
            obtener_status_agentes_sesiones_activas, _remover_agente_cola_asterisk, activar):
        obtener_status_agentes_sesiones_activas.return_value = {self.agente1.id: 'READY'}
        keys.return_value = []
        service = QueueMemberService()
        self.assertEqual(self.agente1.queue_set.count(), 2)
        keys.side_effect = [
            ['OML:CAMPAIGN-AGENTS:1'],
            ['OML:CAMP:1:MEMBER-PENALTY'],
        ]
        service.eliminar_agente_de_colas_asignadas(self.agente1)
        obtener_status_agentes_sesiones_activas.assert_called()
        keys.assert_any_call('OML:CAMPAIGN-AGENTS:*')
        delete.assert_any_call('OML:AGENT-CAMPAIGNS:' + str(self.agente1.id))
        self.assertEqual(self.agente1.queue_set.count(), 0)
        _remover_agente_cola_asterisk.assert_has_calls([call(self.campana1, self.agente1),
                                                        call(self.campana2, self.agente1)],
                                                       any_order=True)
        srem.assert_called_with('OML:CAMPAIGN-AGENTS:1', self.agente1.id)
        hdel.assert_called_with('OML:CAMP:1:MEMBER-PENALTY', self.agente1.id)

    @patch('ominicontacto_app.services.queue_member_service.QueueMemberService'
           '._remover_agente_cola_asterisk')
    @patch('ominicontacto_app.services'
           '.queue_member_service.obtener_status_agentes_sesiones_activas')
    @patch('redis.Redis.hdel')
    @patch('redis.Redis.srem')
    def test_eliminar_agentes_de_cola(
            self, srem, hdel,
            obtener_status_agentes_sesiones_activas, _remover_agente_cola_asterisk):
        self.assertEqual(self.agente1.queue_set.count(), 2)
        self.assertEqual(self.agente2.queue_set.count(), 1)
        obtener_status_agentes_sesiones_activas.return_value = {self.agente2.id: 'READY'}
        service = QueueMemberService()
        service.eliminar_agentes_de_cola(self.campana1, (self.agente1, self.agente2))
        obtener_status_agentes_sesiones_activas.assert_called()
        # Se eliminan de la lista de campañas del agente en Redis
        srem.assert_has_calls([
            call('OML:AGENT-CAMPAIGNS:' + str(self.agente1.id), self.campana1.id),
            call('OML:AGENT-CAMPAIGNS:' + str(self.agente2.id), self.campana1.id)],
            any_order=True)
        hdel.assert_has_calls([
            call(
                'OML:CAMP:{0}:MEMBER-PENALTY'.format(self.campana1.id),
                self.agente1.id),
            call(
                'OML:CAMP:{0}:MEMBER-PENALTY'.format(self.campana1.id),
                self.agente2.id),
        ], any_order=True)
        # Se eliminaron los QueueMember asociados
        self.assertEqual(self.agente1.queue_set.count(), 1)
        self.assertEqual(self.agente2.queue_set.count(), 0)
        # Se remueve de la cola de asterisk el agente conectado
        _remover_agente_cola_asterisk.assert_called_with(self.campana1, self.agente2)

    @patch('ominicontacto_app.services.queue_member_service.QueueMemberService'
           '._adicionar_agente_cola_asterisk')
    @patch('ominicontacto_app.services'
           '.queue_member_service.obtener_status_agentes_sesiones_activas')
    @patch('redis.Redis.hset')
    @patch('redis.Redis.sadd')
    def test_agregar_agentes_en_cola(
        self, sadd, hset, obtener_status_agentes_sesiones_activas, _adicionar_agente_cola_asterisk
    ):
        self.assertEqual(self.agente3.queue_set.count(), 0)
        obtener_status_agentes_sesiones_activas.return_value = {self.agente2.id: 'READY'}
        service = QueueMemberService()
        penalties = {self.agente2.id: 3, self.agente3.id: 4}
        service.agregar_agentes_en_cola(self.campana2, [self.agente2, self.agente3], penalties)
        obtener_status_agentes_sesiones_activas.assert_called()
        # Se crean los QueueMember
        id_campana = self.campana2.get_queue_id_name()
        queue_member_2 = self.agente2.campana_member.get(id_campana=id_campana, penalty=3)
        self.agente3.campana_member.get(id_campana=id_campana, penalty=4)
        # Se agregan a la lista de campañas del agente en Redis
        sadd.assert_has_calls([
            call('OML:AGENT-CAMPAIGNS:' + str(self.agente2.id), self.campana2.id),
            call('OML:AGENT-CAMPAIGNS:' + str(self.agente3.id), self.campana2.id)],
            any_order=True)
        # Penalty por membresía proyectado a Redis
        hset.assert_any_call(
            'OML:CAMP:{0}:MEMBER-PENALTY'.format(self.campana2.id),
            mapping={
                str(self.agente2.id): 3,
                str(self.agente3.id): 4,
            },
        )
        # Se agrega a la cola de asterisk el agente conectado (flujo mantenido; AMI fuera de Django)
        _adicionar_agente_cola_asterisk.assert_called_with(
            self.agente2, queue_member_2, self.campana2, False)

    @patch('ominicontacto_app.services'
           '.queue_member_service.obtener_status_agentes_sesiones_activas')
    @patch('redis.Redis.hset')
    @patch('redis.Redis.sadd')
    def test_agregar_agentes_en_cola_sin_penalties(
        self, sadd, hset, obtener_status_agentes_sesiones_activas
    ):
        self.assertEqual(self.agente3.queue_set.count(), 0)
        obtener_status_agentes_sesiones_activas.return_value = {}
        service = QueueMemberService()
        service.agregar_agentes_en_cola(self.campana2, [self.agente2, self.agente3])
        obtener_status_agentes_sesiones_activas.assert_called()
        # Se crean los QueueMember
        id_campana = self.campana2.get_queue_id_name()
        self.agente2.campana_member.get(id_campana=id_campana, penalty=0)
        self.agente3.campana_member.get(id_campana=id_campana, penalty=0)
        # Se agregan a la lista de campañas del agente en Redis
        sadd.assert_has_calls([
            call('OML:AGENT-CAMPAIGNS:' + str(self.agente2.id), self.campana2.id),
            call('OML:AGENT-CAMPAIGNS:' + str(self.agente3.id), self.campana2.id)],
            any_order=True)
        hset.assert_any_call(
            'OML:CAMP:{0}:MEMBER-PENALTY'.format(self.campana2.id),
            mapping={
                str(self.agente2.id): 0,
                str(self.agente3.id): 0,
            },
        )

    @patch('redis.Redis.hset')
    @patch('redis.Redis.sadd')
    def test_agregar_agente_a_campanas(self, sadd, hset):
        service = QueueMemberService()
        service.agregar_agente_a_campanas(self.agente3, [self.campana1, self.campana2])

        self.assertEqual(self.agente3.queue_set.count(), 2)
        id_campana1 = self.campana1.get_queue_id_name()
        id_campana2 = self.campana2.get_queue_id_name()
        # Se crean los QueueMember
        self.agente3.campana_member.get(id_campana=id_campana1, penalty=0)
        self.agente3.campana_member.get(id_campana=id_campana2, penalty=0)
        # Se agregan a la lista de campañas del agente en Redis
        sadd.assert_has_calls([
            call('OML:AGENT-CAMPAIGNS:' + str(self.agente3.id), *[self.campana1.id,
                                                                  self.campana2.id]),
            call('OML:CAMPAIGN-AGENTS:' + str(self.campana2.id), self.agente3.id),
            call('OML:CAMPAIGN-AGENTS:' + str(self.campana1.id), self.agente3.id)
        ], any_order=True)
        hset.assert_has_calls([
            call(
                'OML:CAMP:{0}:MEMBER-PENALTY'.format(self.campana1.id),
                str(self.agente3.id),
                0),
            call(
                'OML:CAMP:{0}:MEMBER-PENALTY'.format(self.campana2.id),
                str(self.agente3.id),
                0),
        ], any_order=True)

    @patch('ominicontacto_app.services.creacion_queue.ActivacionQueueService.activar')
    @patch('ominicontacto_app.services'
           '.queue_member_service.obtener_status_agentes_sesiones_activas')
    @patch('redis.Redis.sadd')
    def test_agregar_agentes_refresca_supervision(self, sadd, obtener_status, activar):
        """H3: al asignar agentes se refresca OML:SUPERVISOR/CAMPANAS de inmediato."""
        obtener_status.return_value = {}
        service = QueueMemberService()
        service._refrescar_supervision_tras_asignacion.reset_mock()
        service.agregar_agentes_en_cola(self.campana2, [self.agente3])
        service._refrescar_supervision_tras_asignacion.assert_called_once()

    def test_refrescar_supervision_delega_a_stream_service(self):
        self._supervision_patcher.stop()
        try:
            service = QueueMemberService()
            fake_conn = object()
            with patch.object(service, '_get_redis_connection', return_value=fake_conn):
                with patch(
                    'supervision_app.services.supervision_stream_service.'
                    'SupervisionStreamService'
                ) as StreamCls:
                    instance = StreamCls.return_value
                    service._refrescar_supervision_tras_asignacion()
            StreamCls.assert_called_once_with(conn=fake_conn)
            instance.refrescar_asignaciones_desde_db.assert_called_once()
        finally:
            self._supervision_patcher.start()


class CampaignAgentsFamilyMemberPenaltyTests(OMLBaseTest):
    """Proyección Redis de OML:CAMP:{id}:MEMBER-PENALTY."""

    def setUp(self):
        super(CampaignAgentsFamilyMemberPenaltyTests, self).setUp()
        self.campana1 = CampanaFactory.create()
        self.campana2 = CampanaFactory.create()
        QueueFactory.create(campana=self.campana1)
        QueueFactory.create(campana=self.campana2)
        self.agente = self.crear_agente_profile()
        self._hacer_miembro(self.agente, self.campana1)
        qm = self.agente.campana_member.get(
            id_campana=self.campana1.get_queue_id_name())
        qm.penalty = 0
        qm.save()
        self._hacer_miembro(self.agente, self.campana2)
        qm2 = self.agente.campana_member.get(
            id_campana=self.campana2.get_queue_id_name())
        qm2.penalty = 5
        qm2.save()

    def test_regenerar_families_escribe_set_y_hash_penalty(self):
        redis_conn = MagicMock()
        redis_conn.keys.return_value = []
        family = CampaignAgentsFamily(redis_connection=redis_conn)
        family.regenerar_families()

        redis_conn.sadd.assert_any_call(
            'OML:CAMPAIGN-AGENTS:{0}'.format(self.campana1.id), self.agente.id)
        redis_conn.sadd.assert_any_call(
            'OML:CAMPAIGN-AGENTS:{0}'.format(self.campana2.id), self.agente.id)

        hset_maps = {}
        for c in redis_conn.hset.call_args_list:
            args, kwargs = c
            key = args[0]
            mapping = kwargs.get('mapping')
            if mapping is not None:
                hset_maps[key] = mapping
        self.assertEqual(
            hset_maps['OML:CAMP:{0}:MEMBER-PENALTY'.format(self.campana1.id)],
            {str(self.agente.id): 0},
        )
        self.assertEqual(
            hset_maps['OML:CAMP:{0}:MEMBER-PENALTY'.format(self.campana2.id)],
            {str(self.agente.id): 5},
        )

    def test_borrar_agente_de_campana_hace_hdel(self):
        redis_conn = MagicMock()
        family = CampaignAgentsFamily(redis_connection=redis_conn)
        family.borrar_agente_de_campana(self.campana2.id, self.agente.id)
        redis_conn.srem.assert_called_with(
            'OML:CAMPAIGN-AGENTS:{0}'.format(self.campana2.id), self.agente.id)
        redis_conn.hdel.assert_called_with(
            'OML:CAMP:{0}:MEMBER-PENALTY'.format(self.campana2.id), self.agente.id)
