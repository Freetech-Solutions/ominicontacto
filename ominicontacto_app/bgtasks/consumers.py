import logging
from asyncio import coroutines

from channels.consumer import SyncConsumer, get_handler_name
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.apps import apps
from django.core.handlers.asgi import ASGIRequest
from django.utils import translation

from .mixins import SearchRecordingsMixin

logger = logging.getLogger("background-tasks")

BACKGROUND_TASKS_MIXINS = [
    SearchRecordingsMixin,
]

if apps.is_installed("premium_reports_app"):
    BACKGROUND_TASKS_MIXINS.extend(
        getattr(apps.get_app_config("premium_reports_app"), "BACKGROUND_TASKS_CONSUMERS", [])
    )

# Tipos de tasks que el cliente puede ejecutar. Cada mixin declara los suyos; se recorre
# la lista porque con herencia múltiple self.CLIENT_ALLOWED_TASKS sólo vería el del primero.
CLIENT_ALLOWED_TASKS = frozenset(
    message_type
    for mixin in BACKGROUND_TASKS_MIXINS
    for message_type in getattr(mixin, "CLIENT_ALLOWED_TASKS", ())
)


class BackgroundTasksConsumerClient(AsyncJsonWebsocketConsumer, *BACKGROUND_TASKS_MIXINS):
    groups = [
        "background-tasks",
        "background-tasks.user-{user_id}",
    ]

    async def websocket_connect(self, message):
        self.groups = [group.format(user_id=self.scope["user"].id) for group in self.groups]
        await super().websocket_connect(message)

    async def connect(self):
        if self.scope["user"].is_authenticated:
            tiene_permiso_oml = database_sync_to_async(self.scope["user"].tiene_permiso_oml)
            if await tiene_permiso_oml(self.scope["url_route"]["kwargs"]["viewname"]):
                self.current_language = translation.get_language_from_request(
                    ASGIRequest(dict(self.scope, method="get"), None)
                )
                await self.accept()
            else:
                await self.close()
        else:
            await self.close()

    async def receive_json(self, content, **kwargs):
        message_type = content.get("type") if isinstance(content, dict) else None
        if message_type not in CLIENT_ALLOWED_TASKS:
            logger.warning(
                "Intento de ejecución de task no permitido: %r (user_id=%s)",
                message_type, self.scope["user"].id)
            return
        await self.dispatch(content)


class BackgroundTasksConsumerWorker(SyncConsumer, *BACKGROUND_TASKS_MIXINS):

    @database_sync_to_async
    def dispatch(self, message):
        handler = getattr(self, get_handler_name(message), None)
        if handler:
            try:
                handler(message)
            except Exception:
                logger.exception(message)
        else:
            raise ValueError("No handler for message type %s" % message["type"])

    async def __call__(self, scope, receive, send):
        try:
            send._is_coroutine = coroutines._is_coroutine
        except AttributeError:
            try:
                send.__func__._is_coroutine = coroutines._is_coroutine
            except AttributeError:
                pass
        await super().__call__(scope, receive, send)
