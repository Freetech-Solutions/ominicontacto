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

import logging

from django.core.management.base import BaseCommand, CommandError
from django.contrib.sessions.models import Session
from django.utils.timezone import now

from ominicontacto_app.services.asterisk.agent_activity import AgentActivityAmiManager
from ominicontacto_app.models import AgenteProfile

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Comando que marca como Unavailable en Redis a los agentes cuya sesión ha expirado.
    No utiliza AMI; solo actualiza el estado en Redis.
    """

    help = (
        u"Comando que marca como Unavailable en Redis a los agentes cuya sesión ha expirado. "
        u"No utiliza AMI."
    )

    def set_agent_unavailable_state_redis(self):
        """Marca como Unavailable en Redis a los agentes con sesión expirada (sin usar AMI)."""
        agent_activity = AgentActivityAmiManager()
        hora_actual = now()
        agentes_marcados = []

        for agente_profile in AgenteProfile.objects.obtener_activos():
            session = None
            if agente_profile.user.last_session_key:
                try:
                    session = Session.objects.get(
                        session_key=agente_profile.user.last_session_key
                    )
                except Session.DoesNotExist:
                    pass

            if session is None or session.expire_date < hora_actual:
                agent_activity.set_agent_as_unavailable(agente_profile)
                agentes_marcados.append(str(agente_profile.id))

        if agentes_marcados:
            logger.info(
                "Agentes marcados como Unavailable en Redis (sesión expirada): %s",
                agentes_marcados,
            )

    def handle(self, *args, **options):
        try:
            self.set_agent_unavailable_state_redis()
        except Exception as e:
            logger.error("Fallo del comando: %s", e)
            raise CommandError("Fallo del comando: %s" % e)
