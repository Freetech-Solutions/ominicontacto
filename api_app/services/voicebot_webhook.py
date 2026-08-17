# -*- coding: utf-8 -*-
# Copyright (C) 2026 Freetech Solutions

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
Helpers compartidos por los webhooks entrantes de voicebots
(VerloopWebhookView, VoicebotWebhookView, VoicebotAgendaWebhookView).
"""

from __future__ import unicode_literals

import json
import logging

from ominicontacto_app.models import AgendaContacto, AgenteProfile, CalificacionCliente

logger = logging.getLogger(__name__)

# Canal Redis donde el CommandDispatcher del ACD escucha comandos globales.
ACD_GLOBAL_COMMANDS_CHANNEL = 'acd:commands:global'


def sanitize_headers_for_log(headers):
    """Devuelve un dict de headers con Authorization enmascarado para logs."""
    safe = {}
    for key, value in headers.items():
        if key.lower() == 'authorization':
            safe[key] = '***'
        else:
            safe[key] = value
    return safe


def anexar_summary_a_agenda(agenda, summary):
    """Concatena `summary` a `AgendaContacto.observaciones`.

    Idempotente: si el summary ya está al final de las observaciones, no duplica.
    Usa QuerySet.update para no re-ejecutar las reglas de negocio de AgendaContacto.save().
    Devuelve True si se escribió un cambio.
    """
    summary = (summary or '').strip()
    if not summary:
        return False
    actual = (agenda.observaciones or '').strip()
    if actual.endswith(summary):
        return False
    nuevo = '{0}\n\n{1}'.format(actual, summary) if actual else summary
    AgendaContacto.objects.filter(pk=agenda.pk).update(observaciones=nuevo)
    agenda.observaciones = nuevo
    return True


def intentar_anexar_summary_a_agenda_previa(contacto, campana, call_summary, log_label):
    """Si ya hay agenda para contacto+campaña, anexa el summary y no transfiere.

    Devuelve el payload de respuesta (dict) o None si no hay agenda previa.
    """
    agenda = AgendaContacto.objects.filter(contacto=contacto, campana=campana).first()
    if agenda is None:
        return None
    appended = anexar_summary_a_agenda(agenda, call_summary)
    logger.info(
        '%s: agenda previa id=%s contacto=%s campaña=%s; summary %s '
        '(sin transfer ACD)',
        log_label, agenda.id, contacto.id, campana.id,
        'anexado' if appended else 'omitido',
    )
    calificacion_id = CalificacionCliente.objects.filter(
        contacto=contacto,
        opcion_calificacion__campana=campana,
    ).values_list('id', flat=True).first()
    return {
        'agenda_id': agenda.id,
        'calificacion_id': calificacion_id,
        'appended': appended,
        'observations': agenda.observaciones,
    }


def extract_call_summary(body_data):
    """Extrae call_summary buscando en raíz y luego en analysis.user_defined.

    Acepta tanto `call_summary` como `Call_Summary`.
    """
    candidate_keys = ('call_summary', 'Call_Summary')

    def _read(container):
        if not isinstance(container, dict):
            return None
        for k in candidate_keys:
            value = container.get(k)
            if value is not None:
                return str(value)
        return None

    call_summary = _read(body_data)
    if not call_summary:
        analysis = body_data.get('analysis') if isinstance(body_data, dict) else None
        user_defined = analysis.get('user_defined') if isinstance(analysis, dict) else None
        call_summary = _read(user_defined)

    return call_summary


def construir_observaciones(body_data, excluded_keys):
    """Construye observaciones aplanando body_data.

    Reglas:
      - Excluye cualquier clave con prefijo 'X-' en cualquier nivel.
      - Excluye en raíz 'call_id' y 'callid'.
      - Excluye en cualquier nivel las claves de `excluded_keys`.
      - Aplana dicts anidados usando '.' como separador de ruta.
      - Listas se serializan como JSON compacto.
      - Valores None o '' se omiten.
    """
    EXCLUDED_TOP = {'call_id', 'callid'}

    def _flatten(node, prefix=''):
        pares = []
        if not isinstance(node, dict):
            return pares
        for key, value in node.items():
            if not isinstance(key, str):
                continue
            if key.startswith('X-'):
                continue
            if key in excluded_keys:
                continue
            if prefix == '' and key in EXCLUDED_TOP:
                continue
            ruta = f"{prefix}{key}"
            if isinstance(value, dict):
                pares.extend(_flatten(value, prefix=f"{ruta}."))
            elif isinstance(value, list):
                if value:
                    try:
                        rendered = json.dumps(value, ensure_ascii=False, default=str)
                    except (TypeError, ValueError):
                        rendered = repr(value)
                    pares.append((ruta, rendered))
            else:
                if value not in (None, ''):
                    pares.append((ruta, value))
        return pares

    if not isinstance(body_data, dict):
        body_data = {}
    return " | ".join(f"{k}: {v}" for k, v in _flatten(body_data))


def read_required_field(body_data, headers, field_name):
    """Lee un campo obligatorio buscando con el nombre EXACTO en body y header.

    Prioridad: body > header. No se aceptan variaciones de nombre
    (case-insensitive, guion-bajo, etc.). Devuelve el valor en str o None.
    """
    value = None
    if isinstance(body_data, dict):
        value = body_data.get(field_name)
    if value is None:
        value = headers.get(field_name)
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
    return value if value not in (None, '') else None


def publicar_voicebot_transfer_proceed(call_id):
    """Publica el comando voicebot_transfer_proceed en Redis para el ACD."""
    try:
        from ominicontacto_app.services.redis.connection import create_redis_connection

        r_client = create_redis_connection(db=0)
        payload = {
            'action': 'voicebot_transfer_proceed',
            'call_id': call_id,
        }
        r_client.publish(ACD_GLOBAL_COMMANDS_CHANNEL, json.dumps(payload))
        logger.info(
            'Voicebot webhook: comando voicebot_transfer_proceed publicado en %s para call_id=%s',
            ACD_GLOBAL_COMMANDS_CHANNEL, call_id,
        )
    except Exception:
        logger.exception(
            'Voicebot webhook: error publicando voicebot_transfer_proceed para call_id=%s',
            call_id,
        )


def resolver_agente_fallback(request, campana, bot_username, log_label):
    """
    Selecciona el agente a asociar a la calificación, en este orden:
      1. request.user.agenteprofile (si el usuario autenticado es agente).
      2. Agente activo con username `bot_username` (setting del integrador).
      3. Primer agente de la campaña.
      4. Primer AgenteProfile activo del sistema.
    Lanza ValueError si no se encuentra ninguno.
    """
    try:
        return request.user.agenteprofile
    except AttributeError:
        pass

    if bot_username:
        agente = AgenteProfile.objects.filter(
            user__username=bot_username, user__is_active=True
        ).first()
        if agente:
            logger.info(
                '%s: usando agente BOT configurado "%s" (id=%s)',
                log_label, bot_username, agente.id,
            )
            return agente
        logger.warning(
            '%s: bot_agent_username="%s" no corresponde a un agente activo',
            log_label, bot_username,
        )

    agentes_campana = campana.obtener_agentes()
    if agentes_campana.exists():
        agente = agentes_campana.first()
        logger.info(
            '%s: usando primer agente de la campaña %s (id=%s)',
            log_label, campana.id, agente.id,
        )
        return agente

    agente = AgenteProfile.objects.filter(user__is_active=True).first()
    if agente:
        logger.warning(
            '%s: sin agentes en la campaña %s, usando primer agente activo (id=%s)',
            log_label, campana.id, agente.id,
        )
        return agente

    raise ValueError('No agent available for creating disposition')


def resolver_agente_voicebot(campana):
    """Devuelve el agente voicebot asignado a la campaña o None si no tiene."""
    return campana.obtener_agentes().filter(voicebot=True).first()


def parse_positive_int(value):
    """Convierte a int positivo; lanza ValueError en caso contrario."""
    result = int(value)
    if result <= 0:
        raise ValueError('Value must be a positive integer')
    return result


def parse_callback_valid(value):
    """Interpreta el flag callback_valid aceptando representaciones comunes."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'si')
    return False
