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
Tests del circuito de mensajes de la búsqueda de grabaciones en segundo plano:

    navegador -> consumer cliente (search_recordings.request)
    consumer cliente -> worker (search_recordings.enqueue, por el channel layer)
    worker -> consumer cliente (search_recordings.status, por group_send)
    consumer cliente -> navegador (search_recordings.status)
    navegador -> ResultadoTareaBusquedaGrabacionView (resultado por HTTP)

No requieren Redis: el channel layer es InMemoryChannelLayer y el registro de tareas
usa FakeTaskRedis. El procesamiento de la búsqueda se reemplaza por un mock; se testea
en tests_grabaciones.
"""

import asyncio
from unittest.mock import patch
from urllib.parse import urlencode

import msgpack
from asgiref.sync import async_to_sync, sync_to_async
from channels.consumer import get_handler_name
from channels.layers import get_channel_layer
from channels.testing import ApplicationCommunicator, WebsocketCommunicator
from django.contrib.auth.models import Group
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils.timezone import now

from ominicontacto.asgi import application
from ominicontacto_app.bgtasks.consumers import (
    CLIENT_ALLOWED_TASKS,
    BackgroundTasksConsumerClient,
)
from ominicontacto_app.bgtasks.mixins import (
    SEARCH_RECORDINGS_STATUS_DONE,
    SEARCH_RECORDINGS_STATUS_FAILED,
    SEARCH_RECORDINGS_STATUS_QUEUED,
    SEARCH_RECORDINGS_STATUS_RUNNING,
    SearchRecordingsMixin,
    SearchRecordingTaskRegister,
)
from ominicontacto_app.models import Campana, User
from ominicontacto_app.tests.factories import CampanaFactory
from ominicontacto_app.tests.utiles import OMLTestUtilsMixin
from ominicontacto_app.utiles import fecha_hora_local

TASK_ID = "3f2b8c1e-5d4a-4e6b-9c7d-1a2b3c4d5e6f"
RESULTADO = {"fragments": {"#table-body": "<tr><td>resultado</td></tr>"}}


class FakeTaskRedis(object):
    """Implementa solo los comandos de Redis que usa SearchRecordingTaskRegister."""

    def __init__(self):
        self.data = {}

    def hset(self, key, mapping):
        self.data.setdefault(key, {}).update(mapping)

    def expire(self, key, ttl):
        pass

    def hgetall(self, key):
        return dict(self.data.get(key, {}))


class CircuitoBusquedaGrabacionesTests(TransactionTestCase, OMLTestUtilsMixin):

    databases = {'default', 'replica'}

    def setUp(self):
        super(CircuitoBusquedaGrabacionesTests, self).setUp()
        Group.objects.get_or_create(name=User.SUPERVISOR)
        Group.objects.get_or_create(name=User.AGENTE)
        self.supervisor = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.otro_supervisor = self.crear_supervisor_profile(rol=User.SUPERVISOR)
        self.campana = CampanaFactory(estado=Campana.ESTADO_ACTIVA)
        self.campana.supervisors.add(self.supervisor.user)
        self.client.login(username=self.supervisor.user, password=self.DEFAULT_PASSWORD)

        self.fake_redis = FakeTaskRedis()
        patcher = patch.object(
            SearchRecordingTaskRegister, "_connection", return_value=self.fake_redis)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.channel_layer = get_channel_layer()
        async_to_sync(self.channel_layer.flush)()

    def _formdata(self, **extra):
        hoy = fecha_hora_local(now()).date().strftime('%d/%m/%Y')
        formdata = {
            "fecha": "{0} - {0}".format(hoy),
            "pagina": "1",
            "grabaciones_x_pagina": "10",
            "BASE_URL": "/",
        }
        formdata.update(extra)
        return urlencode(formdata)

    async def _conectar(self):
        ws = WebsocketCommunicator(
            application=application,
            path="channels/background-tasks",
            headers=[
                (b"cookie", self.client.cookies.output(header="")[1:].encode()),
            ],
        )
        connected, _ = await ws.connect(timeout=1)
        self.assertTrue(connected)
        return ws

    async def _solicitar_busqueda(self, ws, task_id=None, **extra):
        message = {
            "type": "search_recordings.request",
            "data": self._formdata(**extra),
        }
        if task_id is not None:
            message["task_id"] = task_id
        await ws.send_json_to(message)
        return await ws.receive_json_from(timeout=1)

    async def _no_hay_tareas_encoladas(self):
        try:
            await asyncio.wait_for(self.channel_layer.receive("background-tasks"), timeout=0.2)
        except asyncio.TimeoutError:
            return True
        return False

    async def _recibir_tarea_encolada(self):
        """Saca el mensaje del canal background-tasks, como lo hace `runworker`."""
        return await asyncio.wait_for(self.channel_layer.receive("background-tasks"), timeout=1)

    async def _ejecutar_en_worker(self, enqueue_message):
        worker = ApplicationCommunicator(
            application=application,
            scope={"type": "channel", "channel": "background-tasks"},
        )
        await worker.send_input(enqueue_message)
        return worker

    async def _esperar_hasta(self, condicion, timeout=2):
        async def _esperar():
            while not condicion():
                await asyncio.sleep(0.01)
        await asyncio.wait_for(_esperar(), timeout=timeout)

    def _status(self, task_id, status, error_message=None):
        return {
            "type": "search_recordings.status",
            "task_id": task_id,
            "status": status,
            "error_message": error_message,
        }

    async def test_usuario_no_logueado_no_conecta(self):
        ws = WebsocketCommunicator(application=application, path="channels/background-tasks")
        connected, _ = await ws.connect(timeout=1)
        self.assertFalse(connected)

    async def test_request_valido_encola_tarea_y_responde_queued(self):
        ws = await self._conectar()
        queued = await self._solicitar_busqueda(ws)
        task_id = queued["task_id"]
        self.assertEqual(queued, {
            "type": "search_recordings.status",
            "task_id": task_id,
            "status": SEARCH_RECORDINGS_STATUS_QUEUED,
        })

        enqueue = await self._recibir_tarea_encolada()
        self.assertEqual(enqueue["type"], "search_recordings.enqueue")
        self.assertEqual(enqueue["task_id"], task_id)
        self.assertEqual(
            enqueue["addressee"]["group"],
            "background-tasks.user-{0}".format(self.supervisor.user.id),
        )
        self.assertEqual(enqueue["addressee"]["role"], "supervisor")
        self.assertEqual(enqueue["requester"]["user_id"], self.supervisor.user.id)
        self.assertEqual(enqueue["campana_choice"], [self.campana.id])
        self.assertEqual(enqueue["context"], {"BASE_URL": "/"})
        self.assertIn("fecha_desde", enqueue["query"])
        self.assertIn("fecha_hasta", enqueue["query"])
        # InMemoryChannelLayer no serializa; channels_redis usa msgpack, así que el mensaje
        # tiene que poder viajar serializado.
        self.assertEqual(
            msgpack.unpackb(msgpack.packb(enqueue, use_bin_type=True), raw=False), enqueue)

        self.assertEqual(
            SearchRecordingTaskRegister.get(task_id, self.supervisor.user.id)["status"],
            SEARCH_RECORDINGS_STATUS_QUEUED,
        )
        await ws.disconnect()

    async def test_request_invalido_responde_errores_sin_encolar(self):
        ws = await self._conectar()
        respuesta = await self._solicitar_busqueda(ws, grabaciones_x_pagina="7")
        self.assertEqual(respuesta["type"], "search_recordings.respond")
        self.assertIn("grabaciones_x_pagina", respuesta["result"]["errors"])

        self.assertTrue(await self._no_hay_tareas_encoladas())
        self.assertIsNone(
            SearchRecordingTaskRegister.get(respuesta["task_id"], self.supervisor.user.id))
        await ws.disconnect()

    async def test_worker_procesa_tarea_y_notifica_solo_a_la_pestana_que_la_pidio(self):
        ws = await self._conectar()
        ws_otra_pestana = await self._conectar()
        queued = await self._solicitar_busqueda(ws)
        task_id = queued["task_id"]
        enqueue = await self._recibir_tarea_encolada()

        with patch.object(SearchRecordingsMixin, "build_recording_search_result",
                          return_value=RESULTADO) as build_recording_search_result:
            worker = await self._ejecutar_en_worker(enqueue)
            try:
                running = await ws.receive_json_from(timeout=2)
                done = await ws.receive_json_from(timeout=2)
            finally:
                worker.stop()

        build_recording_search_result.assert_called_once_with(
            enqueue["query"], enqueue["campana_choice"], "supervisor", enqueue["context"])
        self.assertEqual(running, self._status(task_id, SEARCH_RECORDINGS_STATUS_RUNNING))
        self.assertEqual(done, self._status(task_id, SEARCH_RECORDINGS_STATUS_DONE))
        # Otra pestaña del mismo usuario está en el mismo grupo pero no recibe el aviso.
        self.assertTrue(await ws_otra_pestana.receive_nothing())

        task = SearchRecordingTaskRegister.get(task_id, self.supervisor.user.id)
        self.assertEqual(task["status"], SEARCH_RECORDINGS_STATUS_DONE)
        self.assertEqual(task["result"], RESULTADO)

        # Al recibir "done" el navegador pide el resultado por HTTP.
        response = await sync_to_async(self.client.get)(
            reverse('api_recording_search_task_result'), {"task_id": task_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), RESULTADO)

        await ws.disconnect()
        await ws_otra_pestana.disconnect()

    async def test_worker_notifica_failed_si_falla_el_procesamiento(self):
        ws = await self._conectar()
        queued = await self._solicitar_busqueda(ws)
        task_id = queued["task_id"]
        enqueue = await self._recibir_tarea_encolada()

        with patch.object(SearchRecordingsMixin, "build_recording_search_result",
                          side_effect=Exception("error de prueba")), \
                patch("ominicontacto_app.bgtasks.consumers.logger") as worker_logger:
            worker = await self._ejecutar_en_worker(enqueue)
            try:
                running = await ws.receive_json_from(timeout=2)
                failed = await ws.receive_json_from(timeout=2)
                # La excepción se relanza después de notificar "failed" y la loguea el worker.
                await self._esperar_hasta(lambda: worker_logger.exception.called)
            finally:
                worker.stop()

        self.assertEqual(running, self._status(task_id, SEARCH_RECORDINGS_STATUS_RUNNING))
        self.assertEqual(failed, self._status(
            task_id, SEARCH_RECORDINGS_STATUS_FAILED, "No se pudo generar el reporte."))
        task = SearchRecordingTaskRegister.get(task_id, self.supervisor.user.id)
        self.assertEqual(task["status"], SEARCH_RECORDINGS_STATUS_FAILED)
        self.assertNotIn("result", task)

        response = await sync_to_async(self.client.get)(
            reverse('api_recording_search_task_result'), {"task_id": task_id})
        self.assertEqual(response.status_code, 409)
        await ws.disconnect()

    async def test_resume_informa_estado_de_tarea_propia(self):
        SearchRecordingTaskRegister.store(
            TASK_ID, self.supervisor.user.id, SEARCH_RECORDINGS_STATUS_RUNNING)
        ws = await self._conectar()
        await ws.send_json_to({"type": "search_recordings.resume", "task_id": TASK_ID})
        self.assertEqual(
            await ws.receive_json_from(timeout=1),
            self._status(TASK_ID, SEARCH_RECORDINGS_STATUS_RUNNING),
        )
        await ws.disconnect()

    async def test_resume_ignora_tarea_de_otro_usuario(self):
        SearchRecordingTaskRegister.store(
            TASK_ID, self.otro_supervisor.user.id, SEARCH_RECORDINGS_STATUS_DONE,
            result=RESULTADO)
        ws = await self._conectar()
        await ws.send_json_to({"type": "search_recordings.resume", "task_id": TASK_ID})
        self.assertTrue(await ws.receive_nothing())
        await ws.disconnect()

    async def test_request_con_task_id_de_otro_usuario_no_pisa_su_tarea(self):
        SearchRecordingTaskRegister.store(
            TASK_ID, self.otro_supervisor.user.id, SEARCH_RECORDINGS_STATUS_DONE,
            result=RESULTADO)
        ws = await self._conectar()
        queued = await self._solicitar_busqueda(ws, task_id=TASK_ID)
        self.assertEqual(queued["status"], SEARCH_RECORDINGS_STATUS_QUEUED)

        tarea_ajena = SearchRecordingTaskRegister.get(TASK_ID, self.otro_supervisor.user.id)
        self.assertEqual(tarea_ajena["status"], SEARCH_RECORDINGS_STATUS_DONE)
        self.assertEqual(tarea_ajena["result"], RESULTADO)
        self.assertEqual(
            SearchRecordingTaskRegister.get(TASK_ID, self.supervisor.user.id)["status"],
            SEARCH_RECORDINGS_STATUS_QUEUED,
        )
        await ws.disconnect()

    async def test_request_con_task_id_mal_formado_se_ignora(self):
        ws = await self._conectar()
        for task_id in ("corto", "a" * 65, "../../etc", "OML:OTRA:CLAVE", 1234567890):
            await ws.send_json_to({
                "type": "search_recordings.request",
                "task_id": task_id,
                "data": self._formdata(),
            })
            self.assertTrue(await ws.receive_nothing(), msg=repr(task_id))
        self.assertTrue(await self._no_hay_tareas_encoladas())
        self.assertEqual(self.fake_redis.data, {})
        await ws.disconnect()

    async def test_request_acepta_task_id_alternativo_del_frontend(self):
        # Fuera de un contexto seguro el frontend no tiene crypto.randomUUID().
        task_id = "1759676400000-9f3a6c2e1b"
        ws = await self._conectar()
        queued = await self._solicitar_busqueda(ws, task_id=task_id)
        self.assertEqual(queued["task_id"], task_id)
        await ws.disconnect()

    async def test_tipos_no_permitidos_desde_el_cliente_se_ignoran(self):
        ws = await self._conectar()
        for message_type in ("search_recordings.enqueue", "search_recordings.status",
                             "search_recordings.dequeue", "websocket.disconnect", None):
            with patch("ominicontacto_app.bgtasks.consumers.logger") as consumer_logger:
                await ws.send_json_to({
                    "type": message_type,
                    "task_id": TASK_ID,
                    "current_language": "es",
                    "requester": {"user_id": self.otro_supervisor.user.id},
                    "addressee": {"group": "background-tasks", "channel_name": "x"},
                })
                self.assertTrue(await ws.receive_nothing(), msg=repr(message_type))
            consumer_logger.warning.assert_called_once()
        self.assertEqual(self.fake_redis.data, {})

        # La conexión sigue abierta y los tipos permitidos se siguen atendiendo.
        queued = await self._solicitar_busqueda(ws)
        self.assertEqual(queued["status"], SEARCH_RECORDINGS_STATUS_QUEUED)
        await ws.disconnect()

    def test_tipos_permitidos_desde_el_cliente_tienen_handler(self):
        self.assertTrue(
            set(SearchRecordingsMixin.CLIENT_ALLOWED_TASKS) <= CLIENT_ALLOWED_TASKS)
        self.assertNotIn("search_recordings.enqueue", CLIENT_ALLOWED_TASKS)
        for message_type in CLIENT_ALLOWED_TASKS:
            handler = getattr(
                BackgroundTasksConsumerClient,
                get_handler_name({"type": message_type}),
                None,
            )
            self.assertTrue(asyncio.iscoroutinefunction(handler), msg=message_type)

    def _get_resultado(self, **params):
        return self.client.get(reverse('api_recording_search_task_result'), params)

    def test_resultado_http_sin_task_id_devuelve_400(self):
        self.assertEqual(self._get_resultado().status_code, 400)

    def test_resultado_http_de_tarea_en_curso_devuelve_202(self):
        SearchRecordingTaskRegister.store(
            TASK_ID, self.supervisor.user.id, SEARCH_RECORDINGS_STATUS_RUNNING)
        response = self._get_resultado(task_id=TASK_ID)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"status": SEARCH_RECORDINGS_STATUS_RUNNING})

    def test_resultado_http_de_tarea_ajena_devuelve_404(self):
        SearchRecordingTaskRegister.store(
            TASK_ID, self.otro_supervisor.user.id, SEARCH_RECORDINGS_STATUS_DONE,
            result=RESULTADO)
        self.assertEqual(self._get_resultado(task_id=TASK_ID).status_code, 404)

    def test_resultado_http_de_tarea_inexistente_devuelve_404(self):
        self.assertEqual(self._get_resultado(task_id=TASK_ID).status_code, 404)
