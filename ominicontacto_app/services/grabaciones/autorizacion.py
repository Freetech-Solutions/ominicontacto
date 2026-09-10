# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

# This file is part of OMniLeads

from __future__ import unicode_literals

import logging
import os
import re

from django.conf import settings

from reportes_app.models import InteractionsSummary

logger = logging.getLogger(__name__)

# YYYY-MM-DD o YYYYMMDD / <interaction_id>.<ext> — interaction_id puede contener puntos
_RECORDING_FILENAME_RE = re.compile(
    r'^/?(\d{4}-?\d{2}-?\d{2})/([^/]+)\.([a-zA-Z0-9]+)$'
)
_EXTRA_RECORDING_EXTENSIONS = frozenset({'json', 'txt'})


def obtener_interaccion_grabacion(callid):
    """Devuelve InteractionsSummary grabable o None."""
    if not callid:
        return None
    return InteractionsSummary.objects.filter(
        interaction_id=callid,
        status='EXIT_ANSWERED',
    ).first()


def usuario_puede_acceder_grabacion(user, interaction):
    """
    Reglas alineadas a la búsqueda WS de grabaciones:
    - Administrador: todas
    - Supervisor / Gerente / Referente: campañas asignadas
    - Agente: solo propias (agent_id) y de sus campañas/colas
    """
    if not user or not interaction:
        return False

    if user.get_is_administrador():
        return True

    supervisor = user.get_supervisor_profile()
    if supervisor is not None:
        return supervisor.campanas_asignadas().filter(
            id=interaction.campaign_id
        ).exists()

    if user.get_is_agente():
        agente = user.get_agente_profile()
        if not agente or interaction.agent_id != agente.id:
            return False
        campana_ids = agente.queue_set.values_list('campana_id', flat=True)
        return interaction.campaign_id in set(campana_ids)

    return False


def resolver_grabacion_autorizada(user, callid):
    """Interacción autorizada o None (404 uniforme)."""
    interaction = obtener_interaccion_grabacion(callid)
    if interaction is None:
        return None
    if not usuario_puede_acceder_grabacion(user, interaction):
        return None
    return interaction


def parsear_filename_grabacion(filename):
    """
    Valida y parsea un filename de grabación.
    Retorna (date_folder, interaction_id) o None si es inválido.
    """
    if not filename or '..' in filename or filename.startswith('\\'):
        return None

    # Normalizar: quitar query residual / espacios
    filename = filename.strip()
    match = _RECORDING_FILENAME_RE.match(filename)
    if not match:
        return None

    date_folder, interaction_id, ext = match.groups()
    monitor_ext = (getattr(settings, 'MONITORFORMAT', 'mp3') or 'mp3').lower()
    allowed_exts = {monitor_ext} | _EXTRA_RECORDING_EXTENSIONS
    if ext.lower() not in allowed_exts:
        return None

    return date_folder, interaction_id


def resolver_grabacion_desde_filename(user, filename):
    """
    Resuelve y autoriza una grabación a partir del path S3/archivo.
    Si el path no matchea el patrón de grabación o no hay permiso → None.
    """
    parsed = parsear_filename_grabacion(filename)
    if parsed is None:
        return None
    _, interaction_id = parsed
    return resolver_grabacion_autorizada(user, interaction_id)


def auditar_acceso_grabacion(user, filename=None, callid=None, granted=False):
    """Log estructurado de intentos de firma/acceso a grabaciones."""
    logger.info(
        'recording_access user_id=%s username=%s callid=%s filename=%s granted=%s',
        getattr(user, 'id', None),
        getattr(user, 'username', None),
        callid,
        filename,
        granted,
    )


def zip_filename_permitido(user, filename):
    """
    Valida que filename sea el ZIP propio del usuario bajo /zip/.
    Retorna el path relativo canónico (/zip/<user>-grabaciones.zip) o None.
    """
    if not filename or not user:
        return None
    if '..' in filename:
        return None

    expected = f'/zip/{user.username}-grabaciones.zip'
    # Aceptar con o sin slash inicial
    normalized = filename if filename.startswith('/') else f'/{filename}'
    if normalized != expected:
        return None
    return expected


def path_zip_canonico(filename):
    """
    Une SENDFILE_ROOT + filename y verifica que quede bajo SENDFILE_ROOT.
    Retorna path absoluto o None si hay traversal.
    """
    root = os.path.realpath(settings.SENDFILE_ROOT)
    candidate = os.path.realpath(
        os.path.join(settings.SENDFILE_ROOT, filename.lstrip('/'))
    )
    if candidate == root or not candidate.startswith(root + os.sep):
        return None
    return candidate
