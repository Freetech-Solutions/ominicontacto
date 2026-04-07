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
from ominicontacto_app.services.asterisk.supervisor_activity import SupervisorActivityAmiManager
from ominicontacto_app.models import Campana, OpcionCalificacion
from mock import patch

from django.test import TestCase
from django.db import connections

from reportes_app.reportes.reporte_llamadas_supervision import (
    ReporteDeLLamadasEntrantesDeSupervision
)
from reportes_app.services.redis_service import RedisService
from reportes_app.tests.utiles import GeneradorDeLlamadaLogs
from ominicontacto_app.tests.factories import AgenteProfileFactory, \
    CampanaFactory, OpcionCalificacionFactory, QueueFactory, \
    QueueMemberFactory, SupervisorProfileFactory


class ReporteDeLLamadasEntrantesDeSupervisionTest(TestCase):
    databases = {'default', 'replica'}

    PWD = u'admin123'

    def setUp(self):
        super(ReporteDeLLamadasEntrantesDeSupervisionTest, self).setUp()
        self.generador = GeneradorDeLlamadaLogs()

        self.supervisor = SupervisorProfileFactory()
        self.supervisor.user.set_password(self.PWD)
        self.supervisor.user.save()

        self.agente1 = AgenteProfileFactory()
        self.agente2 = AgenteProfileFactory()

        self.entrante1 = CampanaFactory.create(type=Campana.TYPE_ENTRANTE, nombre='camp-entrante-1',
                                               estado=Campana.ESTADO_ACTIVA,
                                               supervisors=[self.supervisor.user])
        self.opcion_calificacion = OpcionCalificacionFactory(campana=self.entrante1,
                                                             tipo=OpcionCalificacion.GESTION)
        # Campaña que no debe estar en los reportes por no ser del supervisor
        self.entrante2 = CampanaFactory.create(type=Campana.TYPE_ENTRANTE, nombre='camp-entrante-2',
                                               estado=Campana.ESTADO_ACTIVA)
        self.queue = QueueFactory.create(campana=self.entrante1)
        connections['replica']._orig_cursor = connections['replica'].cursor
        connections['replica'].cursor = connections['default'].cursor

    def tearDown(self):
        connections['replica'].cursor = connections['replica']._orig_cursor
        super(ReporteDeLLamadasEntrantesDeSupervisionTest, self).tearDown()

    @patch('redis.Redis.keys')
    @patch.object(RedisService, 'obtener_estadisticas_campanas_entrantes')
    def test_reporte_vacio(self, obtener_estadisticas_campanas_entrantes, keys):
        obtener_estadisticas_campanas_entrantes.return_value = {}
        keys.return_value = []
        reporte = ReporteDeLLamadasEntrantesDeSupervision(self.supervisor.user)
        keys.assert_called()
        self.assertNotIn(self.entrante1.id, reporte.estadisticas)
        self.assertNotIn(self.entrante2.id, reporte.estadisticas)

    def _obtener_agentes_activos(self):
        return [{
            'id': self.agente1.id,
            'status': 'PAUSE-ACW'
        },
            {
            'id': self.agente2.id,
            'status': 'ONCALL-IN01'
        }
        ]

    def _obtener_estadisticas_redis(self):
        return {
            self.entrante1.id: {
                'nombre': self.entrante1.nombre,
                'atendidas': 0,
                'abandonadas': 1,
                'expiradas': 1,
                'gestiones': 0,
                't_promedio_abandono': 12.5,
                't_promedio_espera': 1,
                'llamadas_en_espera': 1
            }
        }

    @patch.object(RedisService, 'obtener_estadisticas_campanas_entrantes')
    @patch.object(SupervisorActivityAmiManager, 'obtener_agentes_activos')
    def test_contabilizar_estadisticas_campanas(self, obtener_agentes_activos,
                                                obtener_estadisticas_campanas_entrantes):
        obtener_agentes_activos.return_value = []
        obtener_estadisticas_campanas_entrantes.return_value = self._obtener_estadisticas_redis()
        reporte = ReporteDeLLamadasEntrantesDeSupervision(self.supervisor.user)
        self.assertNotIn(self.entrante2.id, reporte.estadisticas)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['atendidas'], 0)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['abandonadas'], 1)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['expiradas'], 1)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['gestiones'], 0)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['t_promedio_abandono'], 12.5)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['t_promedio_espera'], 1)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['llamadas_en_espera'], 1)

    @patch.object(SupervisorActivityAmiManager, 'obtener_agentes_activos')
    @patch.object(RedisService, 'obtener_estadisticas_campanas_entrantes')
    def test_contabilizar_agentes_activos_reporte_vacio(self,
                                                        obtener_estadisticas_campanas_entrantes,
                                                        obtener_agentes_activos):
        obtener_agentes_activos.return_value = []
        obtener_estadisticas_campanas_entrantes.return_value = {}
        reporte = ReporteDeLLamadasEntrantesDeSupervision(self.supervisor.user)
        self.assertNotIn(self.entrante1.id, reporte.estadisticas)
        self.assertNotIn(self.entrante2.id, reporte.estadisticas)

    @patch.object(RedisService, 'obtener_estadisticas_campanas_entrantes')
    @patch.object(SupervisorActivityAmiManager, 'obtener_agentes_activos')
    def test_contabilizar_agentes_pausa(self, obtener_agentes_activos,
                                        obtener_estadisticas_campanas_entrantes):
        obtener_estadisticas_campanas_entrantes.return_value = self._obtener_estadisticas_redis()
        obtener_agentes_activos.return_value = self._obtener_agentes_activos()
        QueueMemberFactory.create(member=self.agente1, queue_name=self.queue)

        reporte = ReporteDeLLamadasEntrantesDeSupervision(self.supervisor.user)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['agentes_pausa'], 1)

    @patch.object(RedisService, 'obtener_estadisticas_campanas_entrantes')
    @patch.object(SupervisorActivityAmiManager, 'obtener_agentes_activos')
    def test_contabilizar_agentes_llamada(self, obtener_agentes_activos,
                                          obtener_estadisticas_campanas_entrantes):
        obtener_agentes_activos.return_value = self._obtener_agentes_activos()
        obtener_estadisticas_campanas_entrantes.return_value = self._obtener_estadisticas_redis()
        QueueMemberFactory.create(member=self.agente2, queue_name=self.queue)

        reporte = ReporteDeLLamadasEntrantesDeSupervision(self.supervisor.user)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['agentes_llamada'], 1)

    @patch.object(RedisService, 'obtener_estadisticas_campanas_entrantes')
    @patch.object(SupervisorActivityAmiManager, 'obtener_agentes_activos')
    def test_contabilizar_agentes_llamada_pausa_activos(self, obtener_agentes_activos,
                                                        obtener_estadisticas_campanas_entrantes):
        obtener_agentes_activos.return_value = self._obtener_agentes_activos()
        obtener_estadisticas_campanas_entrantes.return_value = self._obtener_estadisticas_redis()
        QueueMemberFactory.create(member=self.agente1, queue_name=self.queue)
        QueueMemberFactory.create(member=self.agente2, queue_name=self.queue)

        reporte = ReporteDeLLamadasEntrantesDeSupervision(self.supervisor.user)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['agentes_pausa'], 1)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['agentes_llamada'], 1)
        self.assertEqual(
            reporte.estadisticas[self.entrante1.id]['agentes_online'], 2)
