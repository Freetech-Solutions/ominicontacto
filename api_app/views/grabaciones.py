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
from django.http import HttpResponseRedirect
from reportes_app.models import InteractionsSummary, SpeechAnalysis

from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework import status

from api_app.services.storage_service import StorageService
from api_app.views.permissions import TienePermisoOML
from api_app.authentication import ExpiringTokenAuthentication
from ominicontacto_app.services.grabaciones.generacion_zip_grabaciones \
    import GeneracionZipGrabaciones
from ominicontacto_app.services.grabaciones.speech_analysis import SpeechAnalysisService


class ObtenerArchivoGrabacionView(APIView):
    """Servicio que devuelve un archivo de grabación según su nombre
    """
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    http_method_names = ['get']

    def get(self, request):
        filename = request.query_params.get("filename")
        # Si es el comprimido de grabaciones no se busca en S3
        iszip = filename.find("/zip/", 0)

        if iszip == -1:
            s3_handler = StorageService()
            return HttpResponseRedirect(s3_handler.get_file_url(filename))

        return sendfile(request, settings.SENDFILE_ROOT + filename)


class ObtenerArchivosGrabacionView(APIView):
    # Servicio que genera Zip con grabaciones seleccionadas
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
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
        listado_archivos = json.loads(params.get('files'))
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
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    http_method_names = ['get']
    renderer_classes = (JSONRenderer, )

    def get(self, request, callid):
        obj = InteractionsSummary.objects.filter(
            interaction_id=callid,
            status='EXIT_ANSWERED',
        ).first()
        if obj and obj.url_archivo_grabacion:
            return Response(data={
                'status': 'OK',
                'record': obj.url_archivo_grabacion
            })
        return Response(
            data={'status': 'ERROR'},
            status=status.HTTP_404_NOT_FOUND
        )


class ProcessSpeechAnalisisTaskView(APIView):
    permission_classes = (TienePermisoOML, )
    authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication, )
    http_method_names = ['post']
    renderer_classes = (JSONRenderer, )

    def post(self, request, task, callid):
        if task not in ['transcription', 'sentiment', 'qa']:
            return Response(
                data={'status': 'ERROR'},
                status=status.HTTP_400_BAD_REQUEST
            )

        date, source_file = InteractionsSummary.objects.get_datos_grabacion(callid)
        if date is None:
            return Response(
                data={'status': 'ERROR'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not task == 'transcription':
            try:
                analysis = SpeechAnalysis.objects.get(callid=callid)
            except SpeechAnalysis.DoesNotExist:
                return Response(
                    data={'status': 'ERROR'},
                    status=status.HTTP_404_NOT_FOUND
                )

        if task == 'transcription':
            analysis, created = SpeechAnalysis.objects.get_or_create(callid=callid)
            if analysis.transcription_status not in [SpeechAnalysis.EMPTY, SpeechAnalysis.ERROR]:
                return Response(
                    data={'status': 'ERROR', 'msg': 'Transcription already exists',
                          'analysis': analysis.as_dict()}
                )
            service = SpeechAnalysisService()
            error = service.process_transcription(callid, date, source_file)
            if error:
                return Response(
                    data={'status': 'ERROR', 'msg': 'Error sending task',
                          'analysis': analysis.as_dict()}
                )
            analysis.transcription_status = SpeechAnalysis.PROCESSING
            analysis.save()
            return Response(data={
                'status': 'OK',
            })
        if task == 'sentiment':
            # TODO: Verificar analysis.transcription_status == SpeechAnalysis.COMPLETED y
            #       analysis.sentiment_status == SpeechAnalysis.EMPTY:
            return
        if task == 'qa':
            # TODO: Verificar analysis.transcription_status == SpeechAnalysis.COMPLETED y
            #       analysis.qa_status == SpeechAnalysis.EMPTY:
            return
