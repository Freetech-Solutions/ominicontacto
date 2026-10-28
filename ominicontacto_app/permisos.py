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

from collections import ChainMap
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from django.db import models


class PermisoOMLManager(models.Manager):
    def get_queryset(self):
        return super(PermisoOMLManager, self).\
            get_queryset().filter(content_type__model='permiso_oml')


class PermisoOML(Permission):
    """No esta asociado a ningun Model"""

    objects = PermisoOMLManager()

    class Meta:
        proxy = True
        verbose_name = "permiso_oml"
        app_label = "permiso_oml"

    def save(self, *args, **kwargs):
        ct, created = ContentType.objects.get_or_create(
            model=self._meta.verbose_name, app_label=self._meta.app_label,
        )
        self.content_type = ct
        super(PermisoOML, self).save(*args)

    @property
    def descripcion(self):
        return DESCRIPCIONES.get(self.codename, self.codename)

    @property
    def version(self):
        return VERSIONES.get(self.codename, '1.0.0')

    def __str__(self):
        return self.codename


def cargar_descripciones():
    # Iterar por todas las apps instaladas.
    descripciones_de_apps = []
    for app in apps.get_app_configs():
        if hasattr(app, 'descripciones'):
            descripciones_de_apps.append(app.descripciones)
    return dict(ChainMap(*descripciones_de_apps))


def cargar_descripciones_y_versiones():
    # Iterar por todas las apps instaladas.
    descripciones = {}
    versiones = {}
    for app in apps.get_app_configs():
        if hasattr(app, 'informacion_de_permisos'):
            for nombre, informacion in app.informacion_de_permisos.items():
                descripciones[nombre] = informacion.get('descripcion', nombre)
                versiones[nombre] = informacion.get('version', '1.0.0')
    return descripciones, versiones


DESCRIPCIONES, VERSIONES = cargar_descripciones_y_versiones()


# Política de permisos sobre URLs: Deny-by-Default.
# Toda URL a la que accede un usuario autenticado debe estar registrada como PermisoOML
# (ver `configuraciones_de_permisos` de cada AppConfig) y el usuario debe tener ese permiso.
# Las únicas excepciones son las URLs de esta lista blanca, que debe mantenerse mínima.
# Se compara contra el nombre completo de la URL (con namespace, si lo tuviera).
PUBLIC_URL_NAMES = frozenset([
    # Autenticación y navegación común a todos los roles
    'index',
    'login',
    'logout',
    'acerca',
    'view_blanco',
    'javascript-catalog',
    'set_language',
    # Identidad del usuario para el frontend webui (lo usan todas sus pantallas)
    'email:api:v1:self-login',
    'email:api:v1:self-payload',
    # Endpoints sin usuario OML o con autenticación propia (firma, token, AllowAny)
    'api_login',
    'api_asterisk_queues_data',
    'api_notify_attended_multinum_call',
    'signed_whatsapp_media',
    'media_serve',
    'webhook-meta',
    'webhook-gupshup',
    'webhook-facebook-messenger',
    'webhook-instagram',
    'confirmar_turno',
    'cancelar_turno',
    # Vistas de django-defender bajo /admin/ (exigen is_staff)
    'defender_blocks_view',
    'defender_unblock_ip_view',
    'defender_unblock_username_view',
])

# Namespaces con control de acceso propio, excluidos del chequeo de PermisoOML.
PUBLIC_URL_NAMESPACES = frozenset([
    'admin',    # Django admin: exige is_staff
    'djdt',     # Django Debug Toolbar: sólo disponible con DEBUG
])


def es_url_publica(resolver_match):
    if resolver_match.namespaces and resolver_match.namespaces[0] in PUBLIC_URL_NAMESPACES:
        return True
    return resolver_match.view_name in PUBLIC_URL_NAMES


def nombres_de_permiso_de_url(resolver_match, basename=None):
    """ Nombres con los que puede estar registrado el PermisoOML de una URL:
        nombre con namespace, nombre de la URL y basename (rutas de routers de DRF) """
    if basename is None:
        basename = getattr(resolver_match.func, 'initkwargs', {}).get('basename')
    nombres = (resolver_match.view_name, resolver_match.url_name, basename)
    return set(nombre for nombre in nombres if nombre)
