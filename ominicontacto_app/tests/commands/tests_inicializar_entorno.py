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
Tests relacionados a inicializar_entorno
"""

from mock import patch
from ominicontacto_app.tests.utiles import OMLBaseTest
from ominicontacto_app.management.commands.inicializar_entorno import Command
from ominicontacto_app.models import AgenteProfile, Campana, SupervisorProfile
from collections import Counter

from ominicontacto_app.tests.factories import (
    CANTIDAD_PSTN_QA,
    CANTIDAD_PSTN_QA_RELAY_ITSP,
    PREFIJOS_PSTN_EMULATOR,
    PSTN_QA_PREFIX_COUNTS,
)


class TestsInicializarEntorno (OMLBaseTest):

    def setUp(self, *args, **kwargs):
        super(TestsInicializarEntorno, self).setUp(*args, **kwargs)
        admin = self.crear_administrador()
        admin.is_staff = True
        admin.save()

    @patch('ominicontacto_app.management.commands.inicializar_entorno.wombat_habilitado')
    @patch('redis.Redis.sadd')
    @patch('ominicontacto_app.services.queue_member_service.obtener_status_agentes_sesiones_activas')
    @patch('ominicontacto_app.management.commands.inicializar_entorno.'
           'escribir_ruta_entrante_config')
    @patch('configuracion_telefonia_app.regeneracion_configuracion_telefonia.'
           'SincronizadorDeConfiguracionDeRutaSalienteEnAsterisk.regenerar_asterisk')
    @patch('configuracion_telefonia_app.regeneracion_configuracion_telefonia.'
           'SincronizadorDeConfiguracionTroncalSipEnAsterisk.regenerar_troncales')
    @patch('ominicontacto_app.services.creacion_queue.ActivacionQueueService.activar_campanas')
    @patch('ominicontacto_app.services.asterisk_service.ActivacionAgenteService.activar')
    def test_multiples_agentes(self, activar_agente, activar_queue, regenerar_troncales,
                               regenerar_asterisk, escribir_ruta_entrante_config,
                               obtener_status_agentes_sesiones_activas, sadd, wombat_habilitado):
        wombat_habilitado.return_value = False  # omnidialer: se crean campaña y template dialer
        inicializar_entorno = Command()
        inicializar_entorno._crear_datos_entorno(False, 3, 2)
        activar_agente.assert_called()
        activar_queue.assert_called()
        regenerar_troncales.assert_called()
        regenerar_asterisk.assert_called()
        escribir_ruta_entrante_config.assert_called()
        obtener_status_agentes_sesiones_activas.assert_called()
        sadd.assert_called()
        self.assertEqual(AgenteProfile.objects.count(), 4)
        self.assertEqual(SupervisorProfile.objects.count(), 4)  # 1 Admin, 1 Gerente, 2 Supervisor
        template_campanas = Campana.objects.filter(estado=Campana.ESTADO_TEMPLATE_ACTIVO)
        self.assertEqual(1, template_campanas.filter(type=Campana.TYPE_MANUAL).count())
        self.assertEqual(1, template_campanas.filter(type=Campana.TYPE_DIALER).count())
        self.assertEqual(1, template_campanas.filter(type=Campana.TYPE_ENTRANTE).count())
        self.assertEqual(2, template_campanas.filter(type=Campana.TYPE_PREVIEW).count())

        contactos = list(inicializar_entorno.bd_contacto.contactos.all())
        self.assertEqual(len(contactos), 100)
        telefonos = [c.telefono for c in contactos]
        prefijos_encontrados = []
        sin_prefijo = 0
        for telefono in telefonos:
            prefijo = telefono[:3]
            if prefijo in PREFIJOS_PSTN_EMULATOR:
                prefijos_encontrados.append(prefijo)
            else:
                sin_prefijo += 1
        self.assertEqual(sorted(prefijos_encontrados), sorted(PREFIJOS_PSTN_EMULATOR))
        self.assertEqual(len(prefijos_encontrados), 15)
        self.assertEqual(sin_prefijo, 75)

        contactos_pstn = list(inicializar_entorno.bd_contacto_pstn_qa.contactos.all())
        self.assertEqual(len(contactos_pstn), CANTIDAD_PSTN_QA)
        prefijos_pstn = Counter(c.telefono[:3] for c in contactos_pstn)
        for prefijo, cantidad in PSTN_QA_PREFIX_COUNTS.items():
            self.assertEqual(prefijos_pstn[prefijo], cantidad)
        relay_itsp = sum(
            count for prefijo, count in prefijos_pstn.items()
            if prefijo not in PSTN_QA_PREFIX_COUNTS
        )
        self.assertEqual(relay_itsp, CANTIDAD_PSTN_QA_RELAY_ITSP)
