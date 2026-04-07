# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

from django.core.management.base import BaseCommand, CommandError
from supervision_app.services.data_management import get_event_subscription_key
from ominicontacto_app.services.redis.connection import create_redis_connection


class Command(BaseCommand):

    help = 'Elimina subscripciones a eventos de wallboards'

    def _delete_event_subscriptions(self):
        redis_connection = create_redis_connection(db=2)
        finalizado = False
        index = 0
        while not finalizado:
            result = redis_connection.scan(index, get_event_subscription_key('*'))
            index = result[0]
            keys = result[1]
            for key in keys:
                redis_connection.delete(key)
            if index == 0:
                finalizado = True

    def handle(self, *args, **options):
        try:
            self._delete_event_subscriptions()
        except Exception as e:
            raise CommandError('Fallo del comando: {0}'.format(e))
