#!/bin/bash

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"

set -e

echo "******** OMniLeads Actualizar Reporte Día Actual Agentes Scheduler ********"
echo "Run django command compilemessages"
$COMMAND compilemessages

echo "Starting Actualizar Reporte Día Actual Agentes Scheduler"
exec $COMMAND actualizar_reporte_dia_actual_agentes_scheduler
