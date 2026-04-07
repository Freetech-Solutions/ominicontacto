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

import logging
from django.conf import settings
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from ominicontacto_app.services.dialer.notification.subscription \
    import DialerStatsSubscriptionManager
from notification_app.subscriptions import SupervisorNotificationSubscriptionManager
from supervision_app.services.data_management import SupervisionDataManager
from ominicontacto_app.services.redis.connection import create_redis_connection

logger = logging.getLogger(__name__)


class AgentConsole(AsyncJsonWebsocketConsumer):

    GROUP_USER_CLS = "agent-console"
    GROUP_USER_OBJ = "agent-console-{user_id}"
    GROUPS = [
        GROUP_USER_CLS,
        GROUP_USER_OBJ,
    ]

    async def connect(self):
        self.user = self.scope["user"]

        group_name = AgentConsole.GROUP_USER_OBJ.format(user_id=self.user.id)
        await get_channel_layer().group_send(group_name, {
            "type": "broadcast",
            "payload": {
                "type": "logout",
            }})

        if self.user.is_authenticated and self.user.is_agente:
            for group in self.GROUPS:
                await self.channel_layer.group_add(
                    group.format(user_id=self.user.id), self.channel_name)
            return await self.accept()
        return await self.close()

    async def disconnect(self, close_code):
        for group in self.GROUPS:
            await self.channel_layer.group_discard(
                group.format(user_id=self.user.id), self.channel_name)

    async def broadcast(self, event):
        await self.send_json(event["payload"])


class AgentConsoleWhatsapp(AsyncJsonWebsocketConsumer):

    GROUP_USER_CLS = "agent-console-whatsapp"
    GROUP_USER_OBJ = "agent-console-whatsapp-{user_id}"
    GROUPS = [
        GROUP_USER_CLS,
        GROUP_USER_OBJ,
    ]

    async def connect(self):
        self.user = self.scope["user"]

        if self.user.is_authenticated and self.user.is_agente:
            for group in self.GROUPS:
                await self.channel_layer.group_add(
                    group.format(user_id=self.user.id), self.channel_name)
            return await self.accept()
        return await self.close()

    async def disconnect(self, close_code):
        for group in self.GROUPS:
            await self.channel_layer.group_discard(
                group.format(user_id=self.user.id), self.channel_name)

    async def broadcast(self, event):
        await self.send_json(event["payload"])


class DialerStatsConsumer(AsyncJsonWebsocketConsumer):

    GROUP_USER_CLS = 'supervisor-dialer'
    GROUP_USER_OBJ = 'supervisor-dialer-{user_id}'
    GROUPS = [
        GROUP_USER_CLS,
        GROUP_USER_OBJ,
    ]
    OMNIDIALER_USER_ID = 'omnidialer'
    # Subscription services:
    DIALER_STATS = 'dialer_stats'
    NOTIFICATION = 'supervisor_notification'

    def __init__(self):
        super(DialerStatsConsumer, self).__init__()
        self.subscriptions = set()
        self.dialer_subscription = DialerStatsSubscriptionManager()
        self.notifications_subscription = SupervisorNotificationSubscriptionManager()

    async def connect(self):
        self.is_omnidialer = False
        if 'secret' in self.scope['url_route']['kwargs']:
            # Accept OMNIDIALER Connection
            secret = self.scope['url_route']['kwargs']['secret']
            if secret != settings.OML_OMNIDIALER_SECRET:
                return
            self.is_omnidialer = True
            for group in self.GROUPS:
                await self.channel_layer.group_add(
                    group.format(user_id=self.OMNIDIALER_USER_ID), self.channel_name)
            await self.accept()
            return

        self.user = self.scope['user']
        if self.user.is_authenticated and self.user.get_supervisor_profile():
            for group in self.GROUPS:
                await self.channel_layer.group_add(
                    group.format(user_id=self.user.id), self.channel_name)
            await self.accept()
            # Compatibilidad con clientes legacy que no envían mensaje "subscribe".
            self.dialer_subscription.add_subscription(self.user)
            self.subscriptions.add(self.DIALER_STATS)
            return

        return await self.close()

    async def disconnect(self, close_code):
        if not (self.is_omnidialer or hasattr(self, 'user')):
            return
        if self.is_omnidialer:
            user_id = self.OMNIDIALER_USER_ID
        else:
            user_id = self.user.id

        for group in self.GROUPS:
            await self.channel_layer.group_discard(
                group.format(user_id=user_id), self.channel_name)
        if hasattr(self, 'user') and self.user.is_authenticated \
                and self.user.get_supervisor_profile():
            if self.DIALER_STATS in self.subscriptions:
                self.dialer_subscription.remove_subscription(self.user)
            if self.NOTIFICATION in self.subscriptions:
                self.notifications_subscription.remove_subscription(self.user, self.NOTIFICATION)

    async def broadcast(self, event):
        await self.send_json(event['payload'])

    async def receive_json(self, content, **kwargs):
        """
        Mensaje desde el cliente.
        """
        action = content.get("action")
        if action != 'subscribe':
            await self.send_json({
                'type': 'error',
                'error': f'Unknown action: {action!r}',
            })
            return

        payload = content.get('payload') or {}
        service = payload.get('service')
        if service == self.DIALER_STATS:
            if service not in self.subscriptions:
                self.dialer_subscription.add_subscription(self.user)
                self.subscriptions.add(service)
        elif service == self.NOTIFICATION:
            if service not in self.subscriptions:
                self.notifications_subscription.add_subscription(self.user, service)
                self.subscriptions.add(service)
        else:
            await self.send_json({
                'type': 'error',
                'error': f'Unknown service: {service!r}',
            })
            return

        await self.send_json({
            'type': 'info',
            'message': 'Subscribed to: ' + service,
        })


class SupervisionConsumer(AsyncJsonWebsocketConsumer):

    GROUP_USER_CLS = 'supervision'
    GROUP_USER_OBJ = 'supervision-{user_id}'
    GROUPS = [
        GROUP_USER_CLS,
        GROUP_USER_OBJ,
    ]
    OMNIDIALER_USER_ID = 'omnidialer'

    def __init__(self):
        super(SupervisionConsumer, self).__init__()
        self.redis_oml_connection = create_redis_connection(db=0)
        self.redis_calldata_connection = create_redis_connection(db=2)
        self.data_manager = SupervisionDataManager(self.redis_oml_connection,
                                                   self.redis_calldata_connection)

    async def connect(self):
        try:
            self.section = self.scope['url_route']['kwargs']['section']
            if self.section not in self.data_manager.SECTIONS:
                return await self.close()
            self.user = self.scope['user']
            if self.user.is_authenticated and \
                    await database_sync_to_async(self.user.get_supervisor_profile)():
                for group in self.GROUPS:
                    await self.channel_layer.group_add(
                        group.format(user_id=self.user.id), self.channel_name)
                await self.accept()
                initial_data = await database_sync_to_async(self.data_manager.add_subscription)(
                    self.user,
                    self.section,
                )
                return await self.send_json({'initial_data': initial_data})
            return await self.close()
        except Exception as e:
            logger.error(e, exc_info=True)
            return await self.close()

    async def disconnect(self, close_code):
        self.user = self.scope['user']

        for group in self.GROUPS:
            await self.channel_layer.group_discard(
                group.format(user_id=self.user.id), self.channel_name)
        if self.user.is_authenticated and \
                await database_sync_to_async(self.user.get_supervisor_profile)():
            await database_sync_to_async(self.data_manager.remove_subscription)(
                self.user,
                self.section,
            )

    async def broadcast(self, event):
        await self.send_json(event['payload'])


import asyncio

SUBSCRIBED_MESSAGE = 'Subscribed!'


class ReporteCentroContactoCanalidadesCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Canalidades por campaña.
    URL: channels/reporte_centro_contacto_canalidades/<task_id>/
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CANALIDADES_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ReporteCentroContactoCanalidadesCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoCanalidadesEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Canalidades por campaña (Egresos).
    URL: channels/reporte_centro_contacto_canalidades_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CANALIDADES_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ReporteCentroContactoCanalidadesEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoCanalidadesPorHoraCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Canalidades por hora.
    URL: channels/reporte_centro_contacto_canalidades_por_hora/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CANALIDADES_POR_HORA_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ReporteCentroContactoCanalidadesPorHoraCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoCanalidadesPorDiaCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Canalidades por día.
    URL: channels/reporte_centro_contacto_canalidades_por_dia/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CANALIDADES_POR_DIA_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ReporteCentroContactoCanalidadesPorDiaCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoCanalidadesPorDiaEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Canalidades por día (Egresos).
    URL: channels/reporte_centro_contacto_canalidades_por_dia_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CANALIDADES_POR_DIA_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ReporteCentroContactoCanalidadesPorDiaEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoCanalidadesPorMesCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Canalidades por mes.
    URL: channels/reporte_centro_contacto_canalidades_por_mes/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CANALIDADES_POR_MES_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ReporteCentroContactoCanalidadesPorMesCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoCanalidadesPorMesEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Canalidades por mes (Egresos).
    URL: channels/reporte_centro_contacto_canalidades_por_mes_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CANALIDADES_POR_MES_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ReporteCentroContactoCanalidadesPorMesEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoCanalidadesPorHoraEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Canalidades por hora (Egresos).
    URL: channels/reporte_centro_contacto_canalidades_por_hora_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CANALIDADES_POR_HORA_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ReporteCentroContactoCanalidadesPorHoraEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoWhatsappMensajesPorHoraEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Mensajes por hora (WhatsApp Egresos).
    URL: channels/reporte_centro_contacto_whatsapp_mensajes_por_hora_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:WA_MSG_HORA_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ReporteCentroContactoWhatsappMensajesPorHoraEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasAtendidasCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Listado de llamadas atendidas (Ingresos/Voz).
    URL: channels/reporte_centro_contacto_llamadas_atendidas_csv/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_ATENDIDAS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasAtendidasCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasAtendidasEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Listado de llamadas atendidas (Egresos/Voz).
    URL: channels/reporte_centro_contacto_llamadas_atendidas_egresos_csv/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_ATENDIDAS_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasAtendidasEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasNoAtendidasCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Listado de llamadas no atendidas (Ingresos/Voz).
    URL: channels/reporte_centro_contacto_llamadas_no_atendidas_csv/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_NO_ATENDIDAS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasNoAtendidasCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasNoAtendidasEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Listado de llamadas no atendidas (Egresos/Voz).
    URL: channels/reporte_centro_contacto_llamadas_no_atendidas_egresos_csv/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_NO_ATENDIDAS_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasNoAtendidasEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasVozCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Llamadas de voz por campaña (Ingresos).
    URL: channels/reporte_centro_contacto_llamadas_voz/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_VOZ_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasVozCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasVozEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Llamadas de voz por campaña (Egresos).
    URL: channels/reporte_centro_contacto_llamadas_voz_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_VOZ_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasVozEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasPorHoraCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Llamadas por hora de día (Ingresos/Voz/Horas).
    URL: channels/reporte_centro_contacto_llamadas_por_hora/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_POR_HORA_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasPorHoraCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasPorHoraEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Llamadas por hora de día (Egresos/Voz/Horas).
    URL: channels/reporte_centro_contacto_llamadas_por_hora_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_POR_HORA_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasPorHoraEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasPorDiaCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Llamadas por día (Ingresos/Voz/Días).
    URL: channels/reporte_centro_contacto_llamadas_por_dia/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_POR_DIA_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasPorDiaCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasPorDiaEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Llamadas por día (Egresos/Voz/Días).
    URL: channels/reporte_centro_contacto_llamadas_por_dia_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_POR_DIA_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasPorDiaEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasPorMesCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Llamadas por mes (Ingresos/Voz/Mes).
    URL: channels/reporte_centro_contacto_llamadas_por_mes/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_POR_MES_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasPorMesCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoLlamadasPorMesEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Llamadas por mes (Egresos/Voz/Mes).
    URL: channels/reporte_centro_contacto_llamadas_por_mes_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:LLAMADAS_POR_MES_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoLlamadasPorMesEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoConversacionesRespondidasCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Conversaciones Respondidas (Ingresos WhatsApp).
    URL: channels/reporte_centro_contacto_conversaciones_respondidas/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CONV_RESP_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoConversacionesRespondidasCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoConversacionesRespondidasEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Conversaciones Respondidas (Egresos WhatsApp).
    URL: channels/reporte_centro_contacto_conversaciones_respondidas_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CONV_RESP_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoConversacionesRespondidasEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoConversacionesNoRespondidasCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Conversaciones no respondidas (Ingresos WhatsApp).
    URL: channels/reporte_centro_contacto_conversaciones_no_respondidas/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CONV_NO_RESP_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoConversacionesNoRespondidasCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoConversacionesNoRespondidasEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Conversaciones no respondidas (Egresos WhatsApp).
    URL: channels/reporte_centro_contacto_conversaciones_no_respondidas_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:CONV_NO_RESP_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoConversacionesNoRespondidasEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoWhatsappMensajesPorCampanaCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Mensajes por campaña (WhatsApp Ingresos).
    URL: channels/reporte_centro_contacto_whatsapp_mensajes_por_campana/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:WA_MSG_CAMPANA:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoWhatsappMensajesPorCampanaCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoWhatsappMensajesPorCampanaEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Mensajes por campaña (WhatsApp Egresos).
    URL: channels/reporte_centro_contacto_whatsapp_mensajes_por_campana_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:WA_MSG_CAMPANA_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoWhatsappMensajesPorCampanaEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoWhatsappMensajesPorDiaCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Mensajes por día (WhatsApp Ingresos).
    URL: channels/reporte_centro_contacto_whatsapp_mensajes_por_dia/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:WA_MSG_DIA:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoWhatsappMensajesPorDiaCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoWhatsappMensajesPorDiaEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Mensajes por día (WhatsApp Egresos).
    URL: channels/reporte_centro_contacto_whatsapp_mensajes_por_dia_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:WA_MSG_DIA_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoWhatsappMensajesPorDiaEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoWhatsappMensajesPorMesCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Mensajes por mes (WhatsApp Ingresos).
    URL: channels/reporte_centro_contacto_whatsapp_mensajes_por_mes/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:WA_MSG_MES:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoWhatsappMensajesPorMesCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteCentroContactoWhatsappMensajesPorMesEgresosCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV Mensajes por mes (WhatsApp Egresos).
    URL: channels/reporte_centro_contacto_whatsapp_mensajes_por_mes_egresos/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:WA_MSG_MES_EGRESOS_CC:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reporte_centro_de_contacto')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteCentroContactoWhatsappMensajesPorMesEgresosCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteAgentsActivityListadoCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV del tab Listado (agents-activity-v2).
    URL: consumers/reporte_grafico_campana/agents_activity_listado/cc/<task_id>
    Al conectar envía 'Subscribed!', luego reenvía cada mensaje del canal Redis
    (porcentaje 0-100) al cliente.
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:AGENTS_ACTIVITY_LISTADO:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('reportes_agents_activity_v2')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteAgentsActivityListadoCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReportePerformanceAgentesCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV de Performance de Agentes
    (reporte gráfico campaña).
    URL: consumers/reporte_grafico_campana/performance_agentes/<campana_id>/<task_id>
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:PERFORMANCE_AGENTES:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('campana_reporte_grafico')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReportePerformanceAgentesCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass


class ReporteInteraccionesPorAgenteCSVConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket para progreso de exportación CSV de Interacciones por Agente
    (reporte gráfico campaña).
    URL: consumers/reporte_grafico_campana/interacciones_por_agente/<campana_id>/<task_id>
    """
    KEY_TASK_TEMPLATE = 'OML:STATUS_CSV_REPORT:INTERACCIONES_POR_AGENTE:cc:{task_id}'

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            return await self.close()
        has_perm = await database_sync_to_async(self._user_has_report_perm)()
        if not has_perm:
            return await self.close()
        self.task_id = self.scope['url_route']['kwargs'].get('task_id', '')
        if not self.task_id:
            return await self.close()
        await self.accept()
        await self.send(text_data=SUBSCRIBED_MESSAGE)
        self._redis_task = asyncio.create_task(self._listen_redis())

    def _user_has_report_perm(self):
        return self.user.tiene_permiso_oml('campana_reporte_grafico')

    async def _listen_redis(self):
        loop = asyncio.get_event_loop()
        key_task = self.KEY_TASK_TEMPLATE.format(task_id=self.task_id)
        pubsub = None
        try:
            redis_conn = create_redis_connection(db=0)
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(key_task)
            while True:
                def _get():
                    return pubsub.get_message(timeout=1.5)
                message = await loop.run_in_executor(None, _get)
                if message is None:
                    continue
                if message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        await self.send(text_data=str(data))
                        if str(data) == '100':
                            break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(
                "ReporteInteraccionesPorAgenteCSVConsumer redis: %s", e)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe(key_task)
                    pubsub.close()
                except Exception:
                    pass

    async def disconnect(self, close_code):
        if getattr(self, '_redis_task', None) and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass
