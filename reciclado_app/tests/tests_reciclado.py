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
Tests del metodo 'ominicontacto_app.models'
"""

from __future__ import unicode_literals

import random
import unittest
import uuid

from decimal import Decimal
from mock import patch

from django.db import connection, connections
from django.db.models import Count
from django.utils.timezone import now, timedelta
from ominicontacto_app.tests.utiles import OMLBaseTest
from ominicontacto_app.models import CalificacionCliente
from ominicontacto_app.services.audio_conversor import ConversorDeAudioService
from reciclado_app.resultado_contactacion import (
    EstadisticasContactacion, RecicladorContactosCampanaDIALER,
    _status_hangup_to_reciclado_id,
)
from reportes_app.models import InteractionsSummary, LlamadaLog


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
class RecicladoTest(OMLBaseTest):

    @patch.object(ConversorDeAudioService, '_convertir_audio')
    def setUp(self, _convertir_audio):
        super(RecicladoTest, self).setUp()
        base_datos = self.crear_base_datos_contacto(cant_contactos=100)
        self.campana = self.crear_campana_dialer(bd_contactos=base_datos)
        self.campana_2 = self.crear_campana_dialer(bd_contactos=base_datos)
        user_agente = self.crear_user_agente()
        self.agente = self.crear_agente_profile(user_agente)

        # estados no contactados (no incluye ABANDONWEL porque es solo de entrantes):
        self.estados = LlamadaLog.EVENTOS_NO_CONEXION[:-1]

        connections['replica']._orig_cursor = connections['replica'].cursor
        connections['replica'].cursor = connections['default'].cursor

        self._created_interaction_ids = []

    def tearDown(self):
        if self._created_interaction_ids:
            InteractionsSummary.objects.filter(
                interaction_id__in=self._created_interaction_ids
            ).delete()
        super(RecicladoTest, self).tearDown()

    def _evento_to_interaction_fields(self, evento):
        if evento in ('COMPLETEOUTNUM', 'COMPLETEAGENT'):
            return 'EXIT_ANSWERED', None
        if evento == 'AMD':
            return 'EXIT_AMD', 'EXIT_AMD'
        return evento, evento

    def _evento_to_reciclado_id(self, evento):
        status, hangup_cause = self._evento_to_interaction_fields(evento)
        return _status_hangup_to_reciclado_id(status, hangup_cause)

    def _create_interaction(self, campana, contacto, evento, start_time=None):
        status, hangup_cause = self._evento_to_interaction_fields(evento)
        start_time = start_time or now()
        interaction_id = 'reciclado-test-{}'.format(uuid.uuid4().hex)
        self._created_interaction_ids.append(interaction_id)
        return InteractionsSummary.objects.using('replica').create(
            interaction_id=interaction_id,
            tenant_id='test-tenant',
            node_id='node-1',
            campaign_id=campana.id,
            channel_type='VOICE',
            direction='OUTBOUND',
            status=status,
            hangup_cause=hangup_cause,
            source_address='',
            destination_address=contacto.telefono,
            start_time=start_time,
            end_time=start_time + timedelta(seconds=60),
            total_duration=Decimal('60'),
            bot_duration=Decimal('0'),
            wait_conn_duration=Decimal('0'),
            agent_duration=Decimal('0'),
            customer_id=contacto.id,
        )

    def test_devuelve_correctamente_no_contactacion(self):
        """
        este test testea todos los resultados las cantidad de los no
        contactdos chequeando que devuelva correctamente
        """

        contactos = self.campana.bd_contacto.contactos.all()

        cant_llamados = 100
        for _ in range(0, cant_llamados):
            contacto = random.choice(contactos)
            estado = random.choice(self.estados)
            self._create_interaction(self.campana, contacto, estado)

        cantidades = {}
        for estado in self.estados:
            cantidades[self._evento_to_reciclado_id(estado)] = 0

        ultima_por_contacto = {}
        for row in InteractionsSummary.objects.using('replica').filter(
                campaign_id=self.campana.id,
                customer_id__isnull=False):
            cid = row.customer_id
            prev = ultima_por_contacto.get(cid)
            if prev is None or row.start_time > prev.start_time:
                ultima_por_contacto[cid] = row

        for row in ultima_por_contacto.values():
            if (row.status or '').strip().upper() == 'EXIT_ANSWERED':
                continue
            rec_id = _status_hangup_to_reciclado_id(row.status, row.hangup_cause)
            if rec_id in EstadisticasContactacion.TXT_ESTADO:
                cantidades[rec_id] = cantidades.get(rec_id, 0) + 1

        estadisticas = EstadisticasContactacion()
        no_contactados = estadisticas.obtener_cantidad_no_contactados(self.campana)
        for key, value in no_contactados.items():
            self.assertEqual(cantidades.get(key, 0), value.cantidad)

    def test_devuelve_correctamente_calificados(self):
        """
        este test testea todos los resultados las cantidad de los
        contactdos chequeando que devuelva correctamente
        """

        contactos = self.campana.bd_contacto.contactos.all()
        opciones_calificacion = self.campana.opciones_calificacion.all()

        for contacto in contactos:
            opcion_calificacion = random.choice(opciones_calificacion)
            self.crear_calificacion_cliente(self.agente, contacto, opcion_calificacion)

        estadisticas = EstadisticasContactacion()
        calificados = estadisticas.obtener_cantidad_calificacion(self.campana)

        calificaciones_query = self.campana.obtener_calificaciones().values(
            'opcion_calificacion__nombre', 'opcion_calificacion__id').annotate(
            Count('opcion_calificacion')).filter(
            opcion_calificacion__count__gt=0).order_by()

        contactados_dict = {}
        for contactado in calificados:
            contactados_dict.update({contactado.id: contactado.cantidad})
        for contactacion in calificaciones_query:
            self.assertEqual(contactacion['opcion_calificacion__count'],
                              contactados_dict[contactacion['opcion_calificacion__id']])

    def _generar_interacciones_y_calificaciones(self, estados):
        contactos = self.campana.bd_contacto.contactos.all()
        opciones_calificacion = self.campana.opciones_calificacion.all()

        for contacto in contactos:
            contactacion = random.choice(['contacta_califica', 'contacta_no_califica',
                                          'no_contacta', 'no_llama'])

            if contactacion == 'contacta_califica':
                self._create_interaction(self.campana, contacto, 'COMPLETEOUTNUM')
                opcion_calificacion = random.choice(opciones_calificacion)
                self.crear_calificacion_cliente(self.agente, contacto, opcion_calificacion)
            if contactacion == 'contacta_no_califica':
                self._create_interaction(self.campana, contacto, 'COMPLETEOUTNUM')
            if contactacion == 'no_contacta':
                estado = random.choice(estados)
                self._create_interaction(self.campana, contacto, estado)
            if contactacion == 'no_llama':
                pass

    def test_obtiene_contactos_reciclados_contactados_calificados(self):
        self._generar_interacciones_y_calificaciones(self.estados)
        reciclador = RecicladorContactosCampanaDIALER()

        # vamos a chequear que sea la misma cantidad de contactos reciclados
        # para los calificados
        for calificacion in self.campana.opciones_calificacion.all():
            contactos_reciclados = reciclador._obtener_contactos_calificados(
                self.campana, [calificacion])

            calificaciones_query = self.campana.obtener_calificaciones().filter(
                opcion_calificacion=calificacion).values_list('contacto_id', flat=True)
            self.assertEqual(calificaciones_query.count(), len(contactos_reciclados))

    def test_obtiene_contactos_reciclados_contactados_no_calificados(self):
        self._generar_interacciones_y_calificaciones(self.estados)
        reciclador = RecicladorContactosCampanaDIALER()

        # ahora chequeamos para agente no califico
        calificados = set(self.campana.obtener_calificaciones().values_list(
            'contacto_id', flat=True).distinct())
        contactados = set(
            InteractionsSummary.objects.using('replica').filter(
                campaign_id=self.campana.id,
                status__iexact='EXIT_ANSWERED',
                customer_id__isnull=False,
            ).values_list('customer_id', flat=True)
        )
        contactados_no_calificados = contactados - calificados

        no_calificados_reciclados = reciclador._obtener_contactos_no_contactados(
            self.campana, [EstadisticasContactacion.AGENTE_NO_CALIFICO, ]).values_list(
            'id', flat=True)
        self.assertEqual(set(no_calificados_reciclados), contactados_no_calificados)

    def test_obtiene_contactos_reciclados_no_contactados(self):
        reciclador = RecicladorContactosCampanaDIALER()
        contactos = list(self.campana.bd_contacto.contactos.all()[:len(self.estados)])

        for contacto, estado in zip(contactos, self.estados):
            self._create_interaction(self.campana, contacto, estado)

        for estado in self.estados:
            id_estado = self._evento_to_reciclado_id(estado)
            no_contactados_reciclados = reciclador._obtener_contactos_no_contactados(
                self.campana, [id_estado, ])
            for contacto in no_contactados_reciclados:
                self.assertEqual(CalificacionCliente.objects.filter(
                    contacto_id=contacto.id).count(), 0)
                ultima = InteractionsSummary.objects.using('replica').filter(
                    campaign_id=self.campana.id,
                    customer_id=contacto.id,
                ).order_by('-start_time').first()
                self.assertIsNotNone(ultima)
                self.assertEqual(
                    _status_hangup_to_reciclado_id(ultima.status, ultima.hangup_cause),
                    id_estado)

    def test_obtiene_contactos_no_llamados_campana_activas(self):
        reciclador = RecicladorContactosCampanaDIALER()
        contactos = self.campana_2.bd_contacto.contactos.all()
        cant_llamados = 20
        # Al ser una campana activa puede haber contactos no llamados, por lo tanto
        # solo llamamos a 20 de 100 contactos
        for i in range(0, cant_llamados):
            contacto = contactos[i]
            estado = random.choice(self.estados)
            self._create_interaction(self.campana_2, contacto, estado)
        contactos_no_llamados = reciclador._obtener_contactos_no_llamados(self.campana_2)
        self.assertEqual(len(contactos_no_llamados), 80)

    def test_ultima_interaccion_por_contacto_usa_solo_la_mas_reciente(self):
        contacto = self.campana.bd_contacto.contactos.first()
        base_time = now()

        self._create_interaction(
            self.campana, contacto, 'NOANSWER',
            start_time=base_time - timedelta(hours=2))
        self._create_interaction(
            self.campana, contacto, 'BUSY',
            start_time=base_time - timedelta(hours=1))
        self._create_interaction(
            self.campana, contacto, 'CANCEL',
            start_time=base_time)

        estadisticas = EstadisticasContactacion()
        no_contactados = estadisticas.obtener_cantidad_no_contactados(self.campana)

        id_cancel = EstadisticasContactacion.MAP_ESTADO_ID['CANCEL']
        id_busy = EstadisticasContactacion.MAP_ESTADO_ID['BUSY']
        id_noanswer = EstadisticasContactacion.MAP_ESTADO_ID['NOANSWER']

        self.assertEqual(no_contactados[id_cancel].cantidad, 1)
        self.assertNotIn(id_busy, no_contactados)
        self.assertNotIn(id_noanswer, no_contactados)
