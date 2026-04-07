#!/bin/bash

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"

set -e

echo "******** OMniLeads Actualizar Reporte Supervisores Scheduler ********"
echo "Run django command compilemessages"
$COMMAND compilemessages

echo "Starting Actualizar Reporte Supervisores Scheduler"
exec $COMMAND actualizar_reporte_supervisores_scheduler
