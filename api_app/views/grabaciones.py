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

from __future__ import unicode_literals

import os
import threading
import json

from django.conf import settings
from django_sendfile import sendfile
from django.utils.translation import gettext as _
from django.http import HttpResponseRedirect, HttpResponseNotFound

from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework import status

from api_app.services.storage_service import StorageService
from api_app.views.permissions import TienePermisoOML
from ominicontacto_app.services.grabaciones.autorizacion import (
    auditar_acceso_grabacion,
    path_zip_canonico,
    resolver_grabacion_autorizada,
    resolver_grabacion_desde_filename,
    zip_filename_permitido,
)
from ominicontacto_app.services.grabaciones.generacion_zip_grabaciones \
    import GeneracionZipGrabaciones


class ObtenerArchivoGrabacionView(APIView):
    """Servicio que devuelve un archivo de grabación según su nombre
    """
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, )
    http_method_names = ['get']

    def get(self, request):
        filename = request.query_params.get("filename")
        # # Si es el comprimido de grabaciones no se busca en S3
        # iszip = filename.find("/zip/", 0)

        # if (os.getenv('S3_STORAGE_ENABLED') and iszip == -1):
        #     s3_handler = StorageService()
        #     return HttpResponseRedirect(s3_handler.get_file_url(filename))

        # return sendfile(request, settings.SENDFILE_ROOT + filename)
        if not filename:
            return HttpResponseNotFound()

        # ZIP de exportación masiva: solo el del usuario autenticado
        if '/zip/' in filename:
            zip_rel = zip_filename_permitido(request.user, filename)
            if zip_rel is None:
                auditar_acceso_grabacion(
                    request.user, filename=filename, granted=False)
                return HttpResponseNotFound()
            zip_abs = path_zip_canonico(zip_rel)
            if zip_abs is None:
                auditar_acceso_grabacion(
                    request.user, filename=filename, granted=False)
                return HttpResponseNotFound()
            auditar_acceso_grabacion(
                request.user, filename=zip_rel, granted=True)
            return sendfile(request, zip_abs)

        llamada_log = resolver_grabacion_desde_filename(request.user, filename)
        if llamada_log is None:
            auditar_acceso_grabacion(
                request.user, filename=filename, granted=False)
            return HttpResponseNotFound()

        auditar_acceso_grabacion(
            request.user,
            filename=filename,
            callid=llamada_log.callid,
            granted=True,
        )

        if os.getenv('S3_STORAGE_ENABLED'):
            s3_handler = StorageService()
            signed_url = s3_handler.get_file_url(filename)
            if not signed_url:
                return HttpResponseNotFound()
            return HttpResponseRedirect(signed_url)
        return sendfile(request, settings.SENDFILE_ROOT + filename)


class ObtenerArchivosGrabacionView(APIView):
    # Servicio que genera Zip con grabaciones seleccionadas
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, )
    http_method_names = ['post']

    def _generar_zip(self, listado_archivos, username, key_task, mostrar_datos_contacto):

        zip_path = os.path.join(settings.SENDFILE_ROOT, 'zip')
        zip_grabaciones = GeneracionZipGrabaciones(listado_archivos, zip_path, key_task,
                                                   username, mostrar_datos_contacto)
        zip_grabaciones.genera_zip()

    def post(self, request):
        params = request.POST
        supervisor_id = request.user.id
        TASK_ID = 'zip'
        try:
            listado_archivos = json.loads(params.get('files') or '[]')
        except (TypeError, ValueError, json.JSONDecodeError):
            return Response(
                data={'status': 'ERROR', 'msg': _('Listado de archivos inválido')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(listado_archivos, list) or not listado_archivos:
            return Response(
                data={'status': 'ERROR', 'msg': _('Listado de archivos inválido')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for archivo in listado_archivos:
            path = archivo.get('archivo') if isinstance(archivo, dict) else None
            if not path or resolver_grabacion_desde_filename(request.user, path) is None:
                auditar_acceso_grabacion(
                    request.user, filename=path, granted=False)
                return Response(
                    data={'status': 'ERROR'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        mostrar_datos_contacto = params.get('mostrar_datos_contacto') == 'true'
        key_task = 'OML:STATUS_DOWNLOAD:RECORDINGS:{0}:{1}'.format(supervisor_id, TASK_ID)

        thread_zip = threading.Thread(
            target=self._generar_zip, args=[listado_archivos,
                                            request.user.username,
                                            key_task,
                                            mostrar_datos_contacto])
        thread_zip.setDaemon(True)
        thread_zip.start()

        return Response(data={
            'status': 'OK',
            'msg': _('Exportación de grabaciones Zip en proceso'),
        })


class ObtenerUrlGrabacionView(APIView):
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, )
    http_method_names = ['get']
    renderer_classes = (JSONRenderer, )

    def get(self, request, callid):
        obj = resolver_grabacion_autorizada(request.user, callid)
        if obj:
            return Response(data={
                'status': 'OK',
                'record': obj.url_archivo_grabacion
            })
        else:
            return Response(
                data={'status': 'ERROR'},
                status=status.HTTP_404_NOT_FOUND
            )
