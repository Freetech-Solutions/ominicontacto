# -*- coding: utf-8 -*-
# Settings para ejecutar tests en Docker (Postgres + Redis).
# Importa tests.py, define PASSWORD para Postgres y DEFENDER_REDIS_URL para django-defender.

import os

# Defender exige DEFENDER_REDIS_URL antes de que se carguen las URLs (defender.utils hace
# get_redis_connection() al importar). Debe estar definido en este módulo antes del import *.
DEFENDER_REDIS_URL = os.environ.get('DEFENDER_REDIS_URL', 'redis://redis:6379/0')

from .tests import *  # noqa: F401, F403

# Postgres en Docker exige contraseña
_DB_PASSWORD = os.environ.get('PGPASSWORD', 'omnileads')
DATABASES['default']['PASSWORD'] = _DB_PASSWORD
DATABASES['replica']['PASSWORD'] = _DB_PASSWORD
