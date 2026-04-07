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
import os
import django

# Patch para django-easy-audit: convertir index_together a indexes para Django 6
# Parcheamos ModelBase.__new__ para modificar la clase Meta antes de Options.__init__
from django.db.models.base import ModelBase

# Guardar el método original
original_new = ModelBase.__new__

def patched_new(cls, name, bases, namespace, **kwargs):
    # Interceptar antes de que se cree la clase del modelo
    # Modificar la clase Meta si tiene index_together
    if 'Meta' in namespace:
        meta_class = namespace['Meta']
        # Verificar si es una clase (type) y tiene index_together
        if isinstance(meta_class, type) and hasattr(meta_class, 'index_together'):
            from django.db import models
            index_together_value = getattr(meta_class, 'index_together', None)
            if index_together_value:
                # Obtener o crear la lista de indexes
                if not hasattr(meta_class, 'indexes'):
                    meta_class.indexes = []
                elif getattr(meta_class, 'indexes', None) is None:
                    meta_class.indexes = []
                
                # Convertir cada grupo de index_together a un Index
                for fields in index_together_value:
                    if isinstance(fields, (list, tuple)):
                        index_name = '_'.join(['idx'] + [str(f) for f in fields])
                        meta_class.indexes.append(
                            models.Index(fields=list(fields), name=index_name)
                        )
                
                # Eliminar index_together para evitar el error de validación
                delattr(meta_class, 'index_together')
    
    # Llamar al __new__ original
    return original_new(cls, name, bases, namespace, **kwargs)

# Aplicar el parche
ModelBase.__new__ = staticmethod(patched_new)

from channels.routing import ProtocolTypeRouter
from channels.routing import ChannelNameRouter
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()

from ominicontacto_app.bgtasks import BackgroundTasksConsumerClient  # noqa: E402
from ominicontacto_app.bgtasks import BackgroundTasksConsumerWorker  # noqa: E402
import notification_app.routing  # noqa: E402

if not os.getenv('WALLBOARD_VERSION', '') == '':
    import wallboard_app.routing

django.setup()

websocket_urlpatterns = [
    path(
        "channels/background-tasks",
        BackgroundTasksConsumerClient.as_asgi(),
        kwargs={"viewname": "channels-background-tasks"}
    ),
]
websocket_urlpatterns.extend(notification_app.routing.websocket_urlpatterns)
if not os.getenv('WALLBOARD_VERSION', '') == '':
    websocket_urlpatterns.extend(wallboard_app.routing.websocket_urlpatterns)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    "channel": ChannelNameRouter({
        "background-tasks": BackgroundTasksConsumerWorker.as_asgi(),
    }),
})
