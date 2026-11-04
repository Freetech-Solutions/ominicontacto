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
Autorizacion de conexiones al servidor de websockets (/consumers).

El servidor de websockets llama a esta vista en cada handshake de navegador,
reenviando la cookie de sesion y el path original en el header X-Original-URI.
Responde 204 si el usuario puede suscribirse, 401 si no hay sesion y 403 en
cualquier otro caso.

IMPORTANTE: la tabla de reglas debe mantenerse alineada con la allowlist del
servidor de websockets (websocket-server/src/fts/oml/services/websockets/server/auth.py).
"""
import re

from django.http import HttpResponse
from django.views.decorators.http import require_GET

RULE_SUPERVISOR = 'supervisor'
RULE_DASHBOARD = 'dashboard'
RULE_ACD = 'acd'
RULE_AGENTE = 'agente'
RULE_CAMPANA = 'campana'
RULE_AUDITORIA = 'auditoria'
RULE_GRABACIONES = 'grabaciones'

RULES = (
    (RULE_SUPERVISOR, re.compile(
        r'^/consumers/stream/supervisor/(?P<id>\d+)/(agentes|entrantes|salientes|dialers)/?$')),
    (RULE_DASHBOARD, re.compile(
        r'^/consumers/stream/(auth|calification)_event_\d{4}-\d{2}-\d{2}/?$')),
    (RULE_ACD, re.compile(
        r'^/consumers/stream/asterisk/conf/updater/?$')),
    (RULE_AGENTE, re.compile(
        r'^/consumers/reporte_agente/estadisticas_dia_actual/(?P<id>\d+)/dashboard1/?$')),
    (RULE_CAMPANA, re.compile(
        r'^/consumers/(reporte_grafico_campana/'
        r'(contactados|calificados|no_atendidos|formulario_gestion)'
        r'|reporte_resultados_de_base_campana/'
        r'(resultados_de_base_contactados|resultados_de_base_contactados_todos))'
        r'/(?P<id>\d+)/\w{1,32}/?$')),
    (RULE_AUDITORIA, re.compile(
        r'^/consumers/genera_csv_auditoria/calificados/(?P<id>\d+)/csv/?$')),
    (RULE_GRABACIONES, re.compile(
        r'^/consumers/genera_zip_grabaciones/grabaciones/(?P<id>\d+)/zip/?$')),
)


def match_rule(path):
    """Devuelve (regla, id) para el path, o (None, None) si no esta en la allowlist"""
    for rule, regex in RULES:
        match = regex.match(path)
        if match:
            return rule, match.groupdict().get('id')
    return None, None


def is_authorized(user, rule, id):
    supervisor = user.get_supervisor_profile()
    if rule == RULE_SUPERVISOR:
        return supervisor is not None and supervisor.id == int(id)
    if rule == RULE_DASHBOARD:
        return supervisor is not None or user.get_is_administrador()
    if rule == RULE_AGENTE:
        agente = user.get_agente_profile()
        return agente is not None and agente.id == int(id)
    if rule == RULE_CAMPANA:
        if user.get_is_administrador():
            return True
        return supervisor is not None and \
            supervisor.campanas_asignadas().filter(pk=int(id)).exists()
    if rule in (RULE_AUDITORIA, RULE_GRABACIONES):
        return user.id == int(id)
    # RULE_ACD se autentica solo con el secret en el servidor de websockets
    return False


@require_GET
def ws_auth(request):
    rule, id = match_rule(request.headers.get('X-Original-URI', ''))
    if rule is None:
        return HttpResponse(status=403)
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    if not is_authorized(request.user, rule, id):
        return HttpResponse(status=403)
    return HttpResponse(status=204)
