#!/bin/bash

# Devenv hot path: only runserver. Shared-state work
# (collectstatic, permisos, regenerar_asterisk) lives in
# django_runtime_bootstrap.sh — run once via:
#   ./oml_manage.sh django-commands
#   ./oml_manage.sh up -d commands

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"
cd /opt/omnileads/ominicontacto

echo "Iniciando Django Server (devenv)"
exec $COMMAND runserver 0.0.0.0:8099
