#!/bin/bash
# One-shot HA-safe bootstrap for shared Django runtime state.
# Must run on a single host (omlapp_db_bootstrap_host / compose django-commands),
# never from every uWSGI replica start.

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"
cd /opt/omnileads/ominicontacto

set -e

echo "******** OMniLeads Django runtime bootstrap (single host) ********"

echo "Run django command compilemessages"
$COMMAND compilemessages

echo "Run django command collectstatic"
$COMMAND collectstatic --noinput
$COMMAND collectstatic_js_reverse

echo "Run django command compress"
$COMMAND compress --force

echo "Run actualizar_permisos"
$COMMAND actualizar_permisos

echo "Run django command regenerar_asterisk"
$COMMAND regenerar_asterisk

echo "******** Django runtime bootstrap done ********"
