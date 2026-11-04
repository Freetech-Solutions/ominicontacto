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

from types import ModuleType

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.urls import URLPattern, URLResolver, ResolverMatch, get_resolver

from ominicontacto_app.permisos import es_url_publica, nombres_de_permiso_de_url

# URLs que quedan denegadas a propósito para todos los usuarios
URLS_DENEGADAS = frozenset([
    'api-root',  # Raíz navegable del router de DRF
])


class Command(BaseCommand):
    help = ('Verifica que toda URL sea pública o tenga un permiso configurado (Deny-by-Default), '
            'que ninguna URL esté controlada por un permiso configurado en otra app, '
            'y que el viewname de las rutas websocket corresponda a un permiso configurado')

    def handle(self, *args, **options):
        configurados = self._obtener_permisos_configurados()
        urls_sin_permiso = set()
        permisos_usados = set()

        colisiones = set()

        for pattern, resolver_match, app in self._recorrer_urls(get_resolver().url_patterns):
            if es_url_publica(resolver_match) or resolver_match.view_name in URLS_DENEGADAS:
                continue
            nombres = nombres_de_permiso_de_url(resolver_match)
            registrados = nombres & set(configurados)
            if registrados:
                permisos_usados |= registrados
            else:
                urls_sin_permiso.add(resolver_match.view_name or str(pattern.pattern))
            # Un permiso de otra app que coincide con la URL (ej: un basename genérico como
            # 'transfer') la controla por accidente: cambiarlo afectaría a las dos apps.
            for nombre in registrados:
                if configurados[nombre] != app:
                    colisiones.add('{0} (urls de {1}) <- {2} (configurado en {3})'.format(
                        resolver_match.view_name, app, nombre, configurados[nombre]))

        websockets_sin_viewname = set()
        websockets_sin_permiso = set()
        for pattern in self._obtener_rutas_websocket():
            ruta = str(pattern.pattern)
            # El consumer chequea con tiene_permiso_oml() el viewname recibido en kwargs
            viewname = pattern.default_args.get('viewname')
            if viewname is None:
                websockets_sin_viewname.add(ruta)
            elif viewname in configurados:
                permisos_usados.add(viewname)
            else:
                websockets_sin_permiso.add('{0} (viewname: {1})'.format(ruta, viewname))

        permisos_sin_url = set(configurados) - permisos_usados

        if websockets_sin_viewname:
            self.stdout.write('Rutas websocket sin PermisoOML (el consumer controla el acceso):')
            for ruta in sorted(websockets_sin_viewname):
                self.stdout.write('  ' + ruta)
        if permisos_sin_url:
            self.stdout.write('Permisos configurados que no corresponden a ninguna URL:')
            for nombre in sorted(permisos_sin_url):
                self.stdout.write('  {0} ({1})'.format(nombre, configurados[nombre]))

        errores = []
        if urls_sin_permiso:
            self.stderr.write('URLs sin permiso configurado (quedan denegadas para todos):')
            for nombre in sorted(urls_sin_permiso):
                self.stderr.write('  ' + nombre)
            errores.append(
                'Hay {0} URLs sin permiso. Configurarlas en configuraciones_de_permisos o, '
                'si son públicas, agregarlas a PUBLIC_URL_NAMES.'.format(len(urls_sin_permiso)))
        if websockets_sin_permiso:
            self.stderr.write('Rutas websocket con viewname sin permiso configurado '
                              '(el consumer rechaza toda conexión):')
            for ruta in sorted(websockets_sin_permiso):
                self.stderr.write('  ' + ruta)
            errores.append(
                'Hay {0} rutas websocket sin permiso. Configurar su viewname en '
                'configuraciones_de_permisos.'.format(len(websockets_sin_permiso)))
        if colisiones:
            self.stderr.write('URLs controladas por permisos configurados en otra app:')
            for colision in sorted(colisiones):
                self.stderr.write('  ' + colision)
            errores.append(
                'Hay {0} colisiones de permisos entre apps. Configurar en la app que declara '
                'la URL un permiso con namespace (ej: "whatsapp:transfer-agents").'.format(
                    len(colisiones)))
        if errores:
            raise CommandError(' '.join(errores))
        self.stdout.write('Todas las URLs y rutas websocket con viewname tienen permiso '
                          'configurado o son públicas.')

    def _obtener_permisos_configurados(self):
        configurados = {}
        for app in apps.get_app_configs():
            if hasattr(app, 'configuraciones_de_permisos'):
                for configuracion in app.configuraciones_de_permisos():
                    configurados[configuracion['nombre']] = app.name
        return configurados

    def _obtener_rutas_websocket(self):
        # Las rutas websocket se definen en asgi.py para que sólo las carguen los servicios ASGI
        from ominicontacto.asgi import websocket_urlpatterns
        return websocket_urlpatterns

    def _recorrer_urls(self, url_patterns, namespaces=(), app=None):
        """ Devuelve cada URL con la app cuyo módulo urls la declara """
        for pattern in url_patterns:
            if isinstance(pattern, URLResolver):
                sub_namespaces = namespaces
                if pattern.namespace:
                    sub_namespaces = namespaces + (pattern.namespace, )
                sub_app = app
                # Los include() de listas (ej: urls de routers) heredan la app que los incluye
                if isinstance(pattern.urlconf_module, ModuleType):
                    config = apps.get_containing_app_config(pattern.urlconf_module.__name__)
                    if config:
                        sub_app = config.name
                yield from self._recorrer_urls(pattern.url_patterns, sub_namespaces, sub_app)
            elif isinstance(pattern, URLPattern):
                yield pattern, ResolverMatch(
                    pattern.callback, (), {}, url_name=pattern.name,
                    namespaces=list(namespaces)), app
