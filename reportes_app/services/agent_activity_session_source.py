# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions
#
# This file is part of OMniLeads
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#

"""
Fuente de datos de sesión/pausa de agente basada en AgentActivityEventV2.
Proporciona el mapeo desde get_agent_activity_kpis_v2 al formato esperado
por ReporteEstadisticasDiariaAgente y ReporteAgentes.
"""

from datetime import timedelta

from django.utils.translation import gettext as _

from ominicontacto_app.models import Pausa

from reportes_app.services.agent_kpis_v2 import get_agent_activity_kpis_v2


# Mapeo aux_code -> nombre para pausas sin pause_id (ej. pausa_id inválido)
AUX_CODE_DISPLAY = {
    '0': _('ACW'),
    '00': _('Pausa-Supervisión'),
    'OW': _('On-Whatsapp'),
    'UNKNOWN': _('Desconocida'),
}


def _resolve_pause_display(pause_id, aux_code):
    """
    Resuelve nombre y tipo_de_pausa para un ítem de pause_breakdown.
    Retorna (nombre_str, tipo_de_pausa) donde tipo_de_pausa es Pausa.CHOICE_RECREATIVA
    o Pausa.CHOICE_PRODUCTIVA.
    """
    if pause_id is not None:
        pausa = Pausa.objects.filter(pk=pause_id).first()
        if pausa is not None:
            return pausa.nombre, pausa.get_tipo()
        # pause_id inválido, usar aux_code si existe
        aux = aux_code or 'UNKNOWN'
    else:
        aux = aux_code or 'UNKNOWN'

    nombre = AUX_CODE_DISPLAY.get(aux, aux)
    # Por defecto pausas sin Pausa OML se consideran productivas
    return nombre, Pausa.CHOICE_PRODUCTIVA


def get_agent_session_data_for_reports(date_start, date_end, agent_ids=None):
    """
    Obtiene sesión y pausas por agente desde AgentActivityEventV2, en formato
    compatible con ReporteEstadisticasDiariaAgente y ReporteAgentes.

    :param date_start: str 'YYYY-MM-DD'
    :param date_end: str 'YYYY-MM-DD'
    :param agent_ids: list[int] | None - si se pasa, filtra solo esos agentes
    :return: dict[agente_id, {
        'session': timedelta,
        'pause': timedelta,
        'ready_seconds': int,
        'acw_seconds': int,
        'pausas_list': [{'id': agente_id, 'nombre_agente': str, 'pausa': obj, 'pausa_id': ...,
                        'tiempo': timedelta, 'tipo_de_pausa': str}, ...]
    }]
    """
    agent_id_param = None
    if agent_ids is not None and len(agent_ids) == 1:
        agent_id_param = agent_ids[0]

    response = get_agent_activity_kpis_v2(
        date_start=date_start,
        date_end=date_end,
        agent_id=agent_id_param,
        group_by='agent',
    )

    results = {}
    for agent_data in response.get('agents', []):
        agente_id = agent_data.get('agente_id', agent_data.get('agent_id'))
        if agent_ids is not None and agente_id not in agent_ids:
            continue

        session_seconds = agent_data.get('session_seconds', 0) or 0
        pause_seconds = agent_data.get('pause_seconds', 0) or 0

        pausas_list = []
        for item in agent_data.get('pause_breakdown', []):
            pause_id = item.get('pause_id')
            aux_code = item.get('aux_code')
            seconds = item.get('seconds', 0) or 0

            nombre, tipo_de_pausa = _resolve_pause_display(pause_id, aux_code)

            # Objeto tipo Pausa para compatibilidad con devuelve_datos_pausa y ReporteAgentes
            # (necesita .nombre y .get_tipo())
            class PausaDisplay:
                def __init__(self, n, tipo):
                    self.nombre = n
                    self._tipo = tipo

                def get_tipo(self):
                    return self._tipo

            pausas_list.append({
                'id': agente_id,
                'nombre_agente': '',  # se llena donde se necesite
                'pausa': PausaDisplay(nombre, tipo_de_pausa),
                'pausa_id': pause_id,
                'aux_code': aux_code,
                'tiempo': timedelta(seconds=int(seconds)),
                'tipo_de_pausa': tipo_de_pausa,
            })

        ready_seconds = int(agent_data.get('ready_seconds', 0) or 0)
        acw_seconds = int(agent_data.get('acw_seconds', 0) or 0)

        results[agente_id] = {
            'session': timedelta(seconds=int(session_seconds)),
            'pause': timedelta(seconds=int(pause_seconds)),
            'ready_seconds': ready_seconds,
            'acw_seconds': acw_seconds,
            'pausas_list': pausas_list,
        }

    return results
