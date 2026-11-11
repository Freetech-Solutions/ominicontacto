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
import fnmatch
import importlib
import os
from io import StringIO
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from redis.exceptions import ConnectionError as RedisConnectionError, WatchError

from ominicontacto_app.models import Campana, User
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD
from supervision_app.services.redisgears_service import RedisGearsService

SUPERVISOR_ID = 999001
CAMPANAS_IDS = '999101,999102'
# En settings de tests BASE_DIR no es la raíz del proyecto, donde están los scripts de Gears
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def registro_gears(registro_id, desc, regex):
    """Arma un registro con la forma de una entrada de RG.DUMPREGISTRATIONS"""
    registration_data = [None] * 14
    registration_data[13] = ['regex', regex]
    registro = [None] * 8
    registro[1] = registro_id
    registro[5] = desc
    registro[7] = registration_data
    return registro


class PipelineFalso(object):
    """Simula un pipeline de redis-py con WATCH / MULTI / EXEC sobre RedisGearsFalso"""

    def __init__(self, redis_falso):
        self.redis = redis_falso
        self.operaciones = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def watch(self, clave):
        self.operaciones = []

    def unwatch(self):
        pass

    def hget(self, clave, campo):
        return self.redis.hashes.get(clave, {}).get(campo)

    def multi(self):
        pass

    def hset(self, clave, campo, valor):
        self.operaciones.append(('hset', clave, campo, valor))

    def hdel(self, clave, campo):
        self.operaciones.append(('hdel', clave, campo))

    def execute(self):
        if self.redis.conflictos_watch > 0:
            # Otro cliente modificó la clave entre WATCH y EXEC
            self.redis.conflictos_watch -= 1
            raise WatchError()
        for operacion in self.operaciones:
            if operacion[0] == 'hset':
                self.redis.hashes.setdefault(operacion[1], {})[operacion[2]] = operacion[3]
            else:
                self.redis.hashes.get(operacion[1], {}).pop(operacion[2], None)


class RedisGearsFalso(object):
    """Simula los comandos de Redis y RedisGears que usa RedisGearsService"""

    def __init__(self, registros=None, total_claves=0, hashes=None, streams=None,
                 conflictos_watch=0):
        self.registros = list(registros or [])
        self.total_claves = total_claves
        self.hashes = hashes or {}
        self.streams = streams or []
        self.conflictos_watch = conflictos_watch
        self.scripts_ejecutados = []
        self.bajas = []
        self.conn = MagicMock()
        self.conn.execute_command.side_effect = self.execute_command
        self.conn.scan_iter.side_effect = self.scan_iter
        self.conn.hkeys.side_effect = lambda clave: list(self.hashes.get(clave, {}).keys())
        self.conn.pipeline.side_effect = lambda: PipelineFalso(self)

    def scan_iter(self, match='*', count=None, _type=None):
        claves = self.streams if _type == 'STREAM' else list(self.hashes.keys())
        return iter([c for c in claves if fnmatch.fnmatchcase(c, match)])

    def streams_suscriptos(self, clave):
        streams = self.hashes.get(clave, {}).get('STREAMS')
        return streams.split(',') if streams else []

    def execute_command(self, comando, *args):
        if comando == 'RG.DUMPREGISTRATIONS':
            return list(self.registros)
        if comando == 'RG.UNREGISTER':
            self.bajas.append(args[0])
            self.registros = [r for r in self.registros if r[1] != args[0]]
            return 'OK'
        if comando == 'RG.PYEXECUTE':
            script = args[0]
            if '.count().run(' in script:
                return [[self.total_claves]]
            self.scripts_ejecutados.append(script)
            if '.register(' in script:
                desc = script.split("desc='")[1].split("'")[0]
                regex = script.split(".register('")[1].split("'")[0]
                self.registros.append(registro_gears(f'nuevo-{desc}', desc, regex))
            return 'OK'
        raise AssertionError(f'Comando no esperado: {comando}')

    def scripts_registrar(self):
        return [s for s in self.scripts_ejecutados if '.register(' in s]

    def scripts_prepara(self):
        return [s for s in self.scripts_ejecutados if ".run('OML:SUPERVISOR:" in s]


@override_settings(BASE_DIR=PROJECT_DIR)
class RedisGearsServiceTestBase(SimpleTestCase):

    def crear_service(self, **kwargs):
        self.redis = RedisGearsFalso(**kwargs)
        with patch('supervision_app.services.redisgears_service.redis.Redis',
                   return_value=self.redis.conn):
            return RedisGearsService()


class SuscripcionStreamSupervisorTest(RedisGearsServiceTestBase):
    """RS-02: al suscribirse se vacía el stream una sola vez, antes de republicar"""

    def suscribir(self, service, pantalla):
        if pantalla == RedisGearsService.AGENTES_TASK_ID:
            service.registra_stream_supervisor(SUPERVISOR_ID)
        else:
            metodo = getattr(service, f'registra_stream_supervisor_{pantalla}')
            metodo(SUPERVISOR_ID, CAMPANAS_IDS)

    def test_vacia_el_stream_de_la_pantalla_una_sola_vez(self):
        for pantalla in ('agentes', 'entrantes', 'salientes', 'dialers'):
            with self.subTest(pantalla=pantalla):
                service = self.crear_service()
                self.suscribir(service, pantalla)
                self.redis.conn.xtrim.assert_called_once_with(
                    f'supervisor_{SUPERVISOR_ID}_{pantalla}', maxlen=0, approximate=False)

    def test_vacia_el_stream_antes_de_republicar_el_estado(self):
        for pantalla in ('agentes', 'entrantes', 'salientes', 'dialers'):
            with self.subTest(pantalla=pantalla):
                service = self.crear_service()
                self.suscribir(service, pantalla)
                llamadas = [c[0] for c in self.redis.conn.mock_calls]
                primer_prepara = next(
                    i for i, c in enumerate(self.redis.conn.mock_calls)
                    if c[0] == 'execute_command' and c[1][0] == 'RG.PYEXECUTE'
                    and ".run('OML:SUPERVISOR:" in c[1][1])
                self.assertLess(llamadas.index('xtrim'), primer_prepara)


class LimiteStreamsTest(RedisGearsServiceTestBase):
    """RS-01: todo XADD a un stream de supervisión tiene MAXLEN"""

    def registrar_todos(self, total_claves):
        # Entre las 3 pantallas de campañas se registran los 4 eventos de supervisión
        service = self.crear_service(total_claves=total_claves)
        service.registra_stream_supervisor_entrantes(SUPERVISOR_ID, CAMPANAS_IDS)
        service.registra_stream_supervisor_salientes(SUPERVISOR_ID, CAMPANAS_IDS)
        service.registra_stream_supervisor_dialers(SUPERVISOR_ID, CAMPANAS_IDS)
        return self.redis.scripts_registrar()

    def test_todos_los_eventos_registrados_limitan_el_stream(self):
        scripts = self.registrar_todos(total_claves=3)
        self.assertEqual(len(scripts), 4)
        for script in scripts:
            compile(script, 'registrar_evento', 'exec')
            for linea in script.splitlines():
                if "'XADD'" in linea:
                    self.assertIn("'MAXLEN', '~'", linea)

    def test_tamano_del_buffer_tiene_minimo_100(self):
        scripts = self.registrar_todos(total_claves=3)
        entrantes = next(s for s in scripts if "desc='sup_entrantes'" in s)
        self.assertIn('STREAM_LENGTH = 100', entrantes)

    def test_tamano_del_buffer_escala_con_la_cantidad_de_claves(self):
        scripts = self.registrar_todos(total_claves=50)
        dialers = next(s for s in scripts if "desc='sup_dialers'" in s)
        self.assertIn('STREAM_LENGTH = 250', dialers)


class ScriptsPreparaTest(RedisGearsServiceTestBase):
    """RS-05 / RS-06: solo se interpolan IDs, no nombres de campaña"""

    def test_scripts_prepara_solo_reciben_ids(self):
        service = self.crear_service()
        service.registra_stream_supervisor_entrantes(SUPERVISOR_ID, CAMPANAS_IDS)
        service.registra_stream_supervisor_salientes(SUPERVISOR_ID, CAMPANAS_IDS)
        service.registra_stream_supervisor_dialers(SUPERVISOR_ID, CAMPANAS_IDS)
        scripts = [s for s in self.redis.scripts_prepara() if 'CAMPANAS_ID_LIST' in s]
        self.assertEqual(len(scripts), 3)
        for script in scripts:
            compile(script, 'prepara', 'exec')
            self.assertNotIn('CAMPANAS_LIST', script)
            self.assertIn(f"CAMPANAS_ID_LIST = '{CAMPANAS_IDS}'", script)
            self.assertIn(f"run('OML:SUPERVISOR:{SUPERVISOR_ID}')", script)


class BajaEventosSupervisionTest(RedisGearsServiceTestBase):
    """RS-04: solo se dan de baja los eventos de supervisión"""

    REGISTROS = [
        registro_gears('id-agent', 'sup_agent', 'OML:AGENT:*'),
        registro_gears('id-entrantes', 'sup_entrantes', 'OML:SUPERVISION_CAMPAIGN:*'),
        registro_gears('id-salientes', 'sup_salientes', 'OML:SUPERVISION_SALIENTE:*'),
        registro_gears('id-dialers', 'sup_dialers', 'OML:SUPERVISION_DIALER:*'),
        registro_gears('id-ajeno', 'otro_evento', 'OML:OTRA_CLAVE:*'),
    ]

    def test_da_de_baja_solo_eventos_de_supervision(self):
        service = self.crear_service(registros=self.REGISTROS)
        bajas = service.da_de_baja_eventos_supervision()
        self.assertEqual(bajas, 4)
        self.assertCountEqual(
            self.redis.bajas, ['id-agent', 'id-entrantes', 'id-salientes', 'id-dialers'])
        self.assertEqual(self.redis.scripts_registrar(), [])

    def test_eventos_dados_de_baja_se_registran_al_suscribirse(self):
        service = self.crear_service(registros=self.REGISTROS)
        service.da_de_baja_eventos_supervision()
        service.registra_stream_supervisor_entrantes(SUPERVISOR_ID, CAMPANAS_IDS)
        descs = sorted(s.split("desc='")[1].split("'")[0]
                       for s in self.redis.scripts_registrar())
        self.assertEqual(descs, ['sup_agent', 'sup_entrantes'])

    def test_no_vuelve_a_registrar_eventos_existentes(self):
        service = self.crear_service(registros=self.REGISTROS)
        service.registra_stream_supervisor_entrantes(SUPERVISOR_ID, CAMPANAS_IDS)
        self.assertEqual(self.redis.scripts_registrar(), [])


class LimpiaStreamsSupervisoresTest(RedisGearsServiceTestBase):

    def test_vacia_todos_los_streams_de_supervisores(self):
        streams = [f'supervisor_{SUPERVISOR_ID}_agentes', f'supervisor_{SUPERVISOR_ID}_dialers']
        service = self.crear_service(streams=streams + ['otro_stream'])
        self.redis.conn.xtrim.side_effect = [3, 4]
        self.assertEqual(service.limpia_streams_supervisores(), 7)
        self.redis.conn.scan_iter.assert_called_once_with(match='supervisor_*', _type='STREAM')
        self.assertEqual(self.redis.conn.xtrim.call_count, 2)
        for stream in streams:
            self.redis.conn.xtrim.assert_any_call(stream, maxlen=0, approximate=False)


class DepuracionSuscripcionesTest(RedisGearsServiceTestBase):
    """
    RS-05: al suscribirse, el stream del supervisor se quita de las listas de campañas y
    agentes que ya no tiene asignados (deny by default), sin tocar otros streams.
    """

    STREAM = f'supervisor_{SUPERVISOR_ID}_entrantes'
    OTRO = 'supervisor_999002_entrantes'
    CAMPANAS = 'OML:SUPERVISION_CAMPAIGN_STREAMS:'
    AGENTES = 'OML:AGENT:'

    def hashes_iniciales(self):
        return {
            # 999101 asignada; 999103 y 999104 ya no
            f'{self.CAMPANAS}999101': {'STREAMS': f'{self.STREAM},{self.OTRO}'},
            f'{self.CAMPANAS}999103': {'STREAMS': f'{self.OTRO},{self.STREAM}'},
            f'{self.CAMPANAS}999104': {'STREAMS': self.STREAM},
            # Agentes visibles para el supervisor: solo 999201
            f'OML:SUPERVISOR:{SUPERVISOR_ID}': {'999201': '{}'},
            f'{self.AGENTES}999201': {'STREAMS': self.STREAM, 'STATUS': 'READY'},
            f'{self.AGENTES}999202': {'STREAMS': f'{self.STREAM},{self.OTRO}',
                                      'STATUS': 'READY'},
        }

    def test_quita_el_stream_de_campanas_no_asignadas(self):
        service = self.crear_service(hashes=self.hashes_iniciales())
        service.registra_stream_supervisor_entrantes(SUPERVISOR_ID, CAMPANAS_IDS)
        suscriptos = self.redis.streams_suscriptos
        self.assertEqual(suscriptos(f'{self.CAMPANAS}999101'), [self.STREAM, self.OTRO])
        self.assertEqual(suscriptos(f'{self.CAMPANAS}999103'), [self.OTRO])
        self.assertEqual(suscriptos(f'{self.CAMPANAS}999104'), [])
        self.assertNotIn('STREAMS', self.redis.hashes[f'{self.CAMPANAS}999104'])

    def test_quita_el_stream_de_agentes_no_asignados(self):
        service = self.crear_service(hashes=self.hashes_iniciales())
        service.registra_stream_supervisor_entrantes(SUPERVISOR_ID, CAMPANAS_IDS)
        self.assertEqual(self.redis.streams_suscriptos(f'{self.AGENTES}999201'), [self.STREAM])
        self.assertEqual(self.redis.streams_suscriptos(f'{self.AGENTES}999202'), [self.OTRO])
        self.assertEqual(self.redis.hashes[f'{self.AGENTES}999202']['STATUS'], 'READY')

    def test_sin_campanas_asignadas_quita_el_stream_de_todas(self):
        service = self.crear_service(hashes=self.hashes_iniciales())
        service.registra_stream_supervisor_entrantes(SUPERVISOR_ID, '')
        for camp_id in ('999101', '999103', '999104'):
            self.assertNotIn(self.STREAM,
                             self.redis.streams_suscriptos(f'{self.CAMPANAS}{camp_id}'))

    def test_solo_depura_las_listas_de_la_pantalla(self):
        hashes = self.hashes_iniciales()
        hashes['OML:SUPERVISION_SALIENTE_STREAMS:999105'] = {
            'STREAMS': f'supervisor_{SUPERVISOR_ID}_salientes'}
        service = self.crear_service(hashes=hashes)
        service.registra_stream_supervisor_salientes(SUPERVISOR_ID, CAMPANAS_IDS)
        self.assertEqual(
            self.redis.streams_suscriptos('OML:SUPERVISION_SALIENTE_STREAMS:999105'), [])
        # Salientes no usa agentes ni campañas entrantes
        self.assertEqual(self.redis.streams_suscriptos(f'{self.AGENTES}999202'),
                         [self.STREAM, self.OTRO])
        self.assertEqual(self.redis.streams_suscriptos(f'{self.CAMPANAS}999103'),
                         [self.OTRO, self.STREAM])

    def test_reintenta_si_otro_cliente_modifica_la_lista(self):
        service = self.crear_service(hashes=self.hashes_iniciales(), conflictos_watch=1)
        service.registra_stream_supervisor_entrantes(SUPERVISOR_ID, CAMPANAS_IDS)
        self.assertEqual(self.redis.streams_suscriptos(f'{self.CAMPANAS}999103'), [self.OTRO])


@override_settings(MIGRACIONES_OMITIR_REDIS=False)
class MigracionStreamsSupervisionTest(SimpleTestCase):
    """La migración da de baja los eventos y vacía los streams, sin frenar si Redis no responde"""

    SERVICE = 'supervision_app.services.redisgears_service.RedisGearsService'

    def setUp(self):
        self.migracion = importlib.import_module(
            'supervision_app.migrations.0001_actualizar_streams_supervision')

    def test_da_de_baja_eventos_y_vacia_streams(self):
        with patch(self.SERVICE) as service:
            service.return_value.da_de_baja_eventos_supervision.return_value = 4
            service.return_value.limpia_streams_supervisores.return_value = 10
            self.migracion.actualizar_streams_supervision(None, None)
        service.return_value.da_de_baja_eventos_supervision.assert_called_once_with()
        service.return_value.limpia_streams_supervisores.assert_called_once_with()

    @override_settings(MIGRACIONES_OMITIR_REDIS=True)
    def test_omite_redis_en_tests(self):
        with patch(self.SERVICE) as service, patch('builtins.print') as imprimir:
            self.migracion.actualizar_streams_supervision(None, None)
        service.assert_not_called()
        imprimir.assert_not_called()

    def test_redis_no_disponible_no_frena_la_migracion(self):
        with patch(self.SERVICE, side_effect=RedisConnectionError('sin redis')), \
                patch('builtins.print'):
            self.migracion.actualizar_streams_supervision(None, None)


class ComandoActualizarStreamsTest(SimpleTestCase):
    """RS-07: el comando informa y registra lo que hizo"""

    SERVICE = 'supervision_app.management.commands.actualizar_streams_supervision.' \
              'RedisGearsService'

    def test_da_de_baja_vacia_y_registra_en_el_log(self):
        with patch(self.SERVICE) as service, \
                self.assertLogs('supervision_app.management.commands.'
                                'actualizar_streams_supervision', 'INFO') as logs:
            service.return_value.da_de_baja_eventos_supervision.return_value = 4
            service.return_value.limpia_streams_supervisores.return_value = 10
            salida = StringIO()
            call_command('actualizar_streams_supervision', stdout=salida)
        self.assertIn('dados de baja: 4', salida.getvalue())
        self.assertIn('10 entradas', salida.getvalue())
        self.assertIn('ejecutado por', logs.output[0])

    def test_sin_limpiar_streams(self):
        with patch(self.SERVICE) as service:
            service.return_value.da_de_baja_eventos_supervision.return_value = 4
            call_command('actualizar_streams_supervision', '--sin-limpiar-streams',
                         stdout=StringIO())
        service.return_value.limpia_streams_supervisores.assert_not_called()


class VistasSupervisionTest(OMLBaseTest):
    """
    RS-03: el stream que se vacía y depura es siempre el del supervisor de la sesión, con las
    campañas que tiene asignadas, sin importar lo que llegue en la request.
    """

    ejecutar_actualizar_permisos = True
    SERVICE = 'supervision_app.views.RedisGearsService'

    def setUp(self):
        super(VistasSupervisionTest, self).setUp()
        self.supervisor = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.otro_supervisor = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.campanas = {}
        self.campanas_ajenas = {}
        for tipo, crear in (('entrantes', self.crear_campana_entrante),
                            ('salientes', self.crear_campana_manual),
                            ('dialers', self.crear_campana_dialer)):
            self.campanas[tipo] = self.crear_activa(crear, self.supervisor)
            self.campanas_ajenas[tipo] = self.crear_activa(crear, self.otro_supervisor)
        self.client.login(username=self.supervisor.user.username, password=PASSWORD)

    def crear_activa(self, crear, supervisor):
        campana = crear(user=supervisor.user)
        campana.estado = Campana.ESTADO_ACTIVA
        campana.save()
        return campana

    def parametros_maliciosos(self):
        ajenas = ','.join(str(c.id) for c in self.campanas_ajenas.values())
        return {'supervisor_id': self.otro_supervisor.id, 'campanas_ids': ajenas,
                'campanas': ajenas}

    def test_vistas_de_campanas_usan_supervisor_y_campanas_de_la_sesion(self):
        vistas = (('entrantes', 'supervision_campanas_entrantes'),
                  ('salientes', 'supervision_campanas_salientes'),
                  ('dialers', 'supervision_campanas_dialer'))
        for tipo, url_name in vistas:
            with self.subTest(pantalla=tipo), patch(self.SERVICE) as service:
                response = self.client.get(reverse(url_name), self.parametros_maliciosos())
                self.assertEqual(response.status_code, 200)
                metodo = getattr(service.return_value, f'registra_stream_supervisor_{tipo}')
                metodo.assert_called_once()
                supervisor_id, campanas_ids = metodo.call_args[0]
                campanas_ids = {int(camp_id) for camp_id in campanas_ids.split(',')}
                self.assertEqual(supervisor_id, self.supervisor.id)
                self.assertIn(self.campanas[tipo].id, campanas_ids)
                # Solo campañas propias (salientes también incluye las dialer)
                self.assertTrue(campanas_ids <= {c.id for c in self.campanas.values()})

    @patch('supervision_app.views.KamailioService')
    def test_vista_de_agentes_usa_supervisor_de_la_sesion(self, kamailio):
        kamailio.return_value.generar_sip_user.return_value = 'sip_user'
        kamailio.return_value.generar_sip_password.return_value = 'sip_password'
        with patch(self.SERVICE) as service:
            response = self.client.get(reverse('supervision_agentes'),
                                       self.parametros_maliciosos(), HTTP_HOST='localhost',
                                       HTTP_X_FORWARDED_PORT='443')
        self.assertEqual(response.status_code, 200)
        service.return_value.registra_stream_supervisor.assert_called_once_with(
            self.supervisor.id)

    def test_usuario_anonimo_no_modifica_streams(self):
        self.client.logout()
        with patch(self.SERVICE) as service:
            for url_name in ('supervision_agentes', 'supervision_campanas_entrantes',
                             'supervision_campanas_salientes', 'supervision_campanas_dialer'):
                response = self.client.get(reverse(url_name))
                self.assertNotEqual(response.status_code, 200)
        service.assert_not_called()
