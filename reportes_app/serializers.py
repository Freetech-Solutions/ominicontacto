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

from rest_framework import serializers


class CentroContactoTotalsSerializer(serializers.Serializer):
    """Contadores crudos para el reporte centro de contacto."""
    total = serializers.IntegerField(default=0)
    total_outbound = serializers.IntegerField(default=0)
    outbound_answered = serializers.IntegerField(default=0)
    total_inbound = serializers.IntegerField(default=0)
    inbound_answered = serializers.IntegerField(default=0)
    inbound_abandoned_gt5 = serializers.IntegerField(default=0)
    inbound_timeout = serializers.IntegerField(default=0)  # Entrantes expiradas (EXIT_TIMEOUT)
    attended_by_human = serializers.IntegerField(default=0)
    sales = serializers.IntegerField(default=0)
    answered_agent_gt10 = serializers.IntegerField(default=0)
    transferred = serializers.IntegerField(default=0)
    bot_only = serializers.IntegerField(default=0)
    count_agent_gt0 = serializers.IntegerField(default=0)
    count_asa = serializers.IntegerField(default=0)
    sum_agent_duration = serializers.DecimalField(
        max_digits=12, decimal_places=3, default=0, allow_null=True
    )
    sum_wait_conn_duration_asa = serializers.DecimalField(
        max_digits=12, decimal_places=3, default=0, allow_null=True
    )
    sum_bot_duration = serializers.DecimalField(
        max_digits=12, decimal_places=3, default=0, allow_null=True
    )


class CentroContactoKPISerializer(serializers.Serializer):
    """Respuesta plana con KPIs y objeto anidado totals."""
    contact_rate_pct = serializers.FloatField(required=False, allow_null=True)
    conversion_rate_pct = serializers.FloatField(required=False, allow_null=True)
    rpc_pct = serializers.FloatField(required=False, allow_null=True)
    aht = serializers.FloatField(required=False, allow_null=True)
    asa = serializers.FloatField(required=False, allow_null=True)
    abandon_rate_pct = serializers.FloatField(required=False, allow_null=True)
    expire_rate_pct = serializers.FloatField(required=False, allow_null=True)
    transfer_rate_pct = serializers.FloatField(required=False, allow_null=True)
    bot_containment_pct = serializers.FloatField(required=False, allow_null=True)
    bot_hours = serializers.FloatField(required=False, allow_null=True)
    totals = CentroContactoTotalsSerializer(required=False)
