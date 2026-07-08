# Copyright (C) 2026 Freetech Solutions
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

from django.db import models


class QuerySet(models.QuerySet):
    pass


class CampaignAccount(models.Model):
    campaign = models.OneToOneField(
        to="ominicontacto_app.Campana",
        on_delete=models.PROTECT,
        related_name="email_account",
    )
    account = models.ForeignKey(
        to="email_app.Account",
        on_delete=models.PROTECT,
        related_name="campaign_accounts",
    )
    service_level = models.IntegerField(default=90)

    objects = QuerySet.as_manager()
