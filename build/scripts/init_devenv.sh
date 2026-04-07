#!/bin/bash

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"

$COMMAND migrate --noinput
$COMMAND createsuperuser --noinput --username=admin --email=admin@example.com || true
$COMMAND populate_history
$COMMAND compilemessages
$COMMAND collectstatic --noinput
$COMMAND collectstatic_js_reverse
$COMMAND compress --force

$COMMAND regenerar_asterisk
$COMMAND actualizar_permisos
$COMMAND adicionar_perfil_supervisor_admin

echo "Iniciando Django Server"
exec $COMMAND runserver 0.0.0.0:8099