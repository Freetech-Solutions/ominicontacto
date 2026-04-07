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
from ominicontacto_app.services.redis.connection import create_redis_connection

# Manejo las suscripciones por servicio
SUBSCRIBERS_KEY = "OML:SUPERVISION:SUBSCRIBERS:{0}"
# Available services: [supervisor_notification, ]


class SupervisorNotificationSubscriptionManager():
    _redis_connection = None

    def __init__(self, redis_connection=None):
        self._redis_connection = redis_connection

    @property
    def redis_connection(self):
        if self._redis_connection is None:
            self._redis_connection = create_redis_connection(db=2)
        return self._redis_connection

    def add_subscription(self, user, service):
        subscribers_key = SUBSCRIBERS_KEY.format(service)
        self.redis_connection.sadd(subscribers_key, user.id)

    def remove_subscription(self, user, service):
        subscribers_key = SUBSCRIBERS_KEY.format(service)
        self.redis_connection.srem(subscribers_key, user.id)
