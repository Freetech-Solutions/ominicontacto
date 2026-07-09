# -*- coding: utf-8 -*-
# Settings para ejecutar tests en la máquina local (Postgres + Redis en localhost).
# Requiere levantar dependencias: ./run_tests.sh --up
#
# Uso:
#   PGHOST=127.0.0.1 PGPASSWORD=omnileads python manage.py test \
#     --settings=ominicontacto.settings.tests_local

import os

DEFENDER_REDIS_URL = os.environ.get('DEFENDER_REDIS_URL', 'redis://127.0.0.1:6379/0')

from .tests import *  # noqa: F401, F403

_LOCALHOST = os.environ.get('PGHOST', '127.0.0.1')
_REDIS_HOST = os.environ.get('REDIS_HOSTNAME', '127.0.0.1')

DATABASES['default']['HOST'] = _LOCALHOST
DATABASES['replica']['HOST'] = _LOCALHOST
DATABASES['default']['PASSWORD'] = os.environ.get('PGPASSWORD', 'omnileads')
DATABASES['replica']['PASSWORD'] = os.environ.get('PGPASSWORD', 'omnileads')

REDIS_HOSTNAME = _REDIS_HOST
CONSTANCE_REDIS_CONNECTION['host'] = _REDIS_HOST
