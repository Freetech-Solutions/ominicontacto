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

from ominicontacto_app.models import AgendaContacto, CalificacionCliente, Campana
from ominicontacto_app.services.dialer import get_dialer_service


def guardar_agenda_contacto(agente, campana, contacto, fecha, hora, telefono,
                            tipo_agenda, observaciones=''):
    """
    Crea o actualiza una agenda de contacto (upsert por contacto+campana).

    Retorna (agenda, created, despausado).
    """
    agenda = AgendaContacto.objects.filter(contacto=contacto, campana=campana).first()
    created = agenda is None
    if created:
        agenda = AgendaContacto(
            agente=agente,
            contacto=contacto,
            campana=campana,
            fecha=fecha,
            hora=hora,
            telefono=telefono,
            tipo_agenda=tipo_agenda,
            observaciones=observaciones or '',
        )
    else:
        agenda.agente = agente
        agenda.fecha = fecha
        agenda.hora = hora
        agenda.telefono = telefono
        agenda.tipo_agenda = tipo_agenda
        agenda.observaciones = observaciones or ''

    if created and agenda.tipo_agenda == AgendaContacto.TYPE_GLOBAL and \
            campana.type == Campana.TYPE_DIALER:
        get_dialer_service().agendar_llamada(campana, agenda)

    agenda.save()

    calificaciones = CalificacionCliente.objects.filter(
        opcion_calificacion__campana=campana, contacto=contacto)
    if calificaciones.exists():
        if created:
            calificacion = calificaciones.first()
            calificaciones.update(agendado=True, tipo_agenda=agenda.tipo_agenda)
            ultima_calificacion_history = CalificacionCliente.history \
                .filter(id=calificacion.id).first()
            if ultima_calificacion_history:
                ultima_calificacion_history.agendado = True
                ultima_calificacion_history.tipo_agenda = agenda.tipo_agenda
                ultima_calificacion_history.save()
        else:
            primera_calificacion = calificaciones.first()
            if primera_calificacion.tipo_agenda != agenda.tipo_agenda:
                calificaciones.update(tipo_agenda=agenda.tipo_agenda)
                ultima_calificacion_history = CalificacionCliente.history \
                    .filter(id=primera_calificacion.id).first()
                if ultima_calificacion_history:
                    ultima_calificacion_history.tipo_agenda = agenda.tipo_agenda
                    ultima_calificacion_history.save()

    despausado = agente.forzar_despausa()
    return agenda, created, despausado
