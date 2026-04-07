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
Servicio para disparar speech analysis tasks
"""
from ominicontacto_app.services.gearman.gearman import send_task


class SpeechAnalysisService:
    TASK_CALLREC_TRANSCRIBER = b'tel-callrec-transcriber'

    def process_transcription(self, callid, date_folder, file_name):
        """
        Dispara el task en el worker.
        callid: ID de la llamada (para compatibilidad con SpeechAnalysis).
        date_folder: carpeta/fecha (ej: YYYY-MM-DD).
        file_name: nombre del archivo (con o sin .mp3).
        El worker espera callid = clave S3 completa del MP3.
        """
        if not date_folder or not file_name:
            return True  # error
        s3_key = f"{date_folder}/{file_name}"
        if not s3_key.endswith('.mp3'):
            s3_key = f"{s3_key}.mp3"
        job_data = {'callid': s3_key}
        return send_task(self.TASK_CALLREC_TRANSCRIBER, job_data)

    def process_sentiment_analysis(self, callid):
        # Verificar que Ya tenga transcripcion
        return

    def process_qa(self, callid):
        # Requiere permiso enterprise
        return
