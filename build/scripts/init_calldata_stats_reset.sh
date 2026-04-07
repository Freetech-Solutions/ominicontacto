#!/bin/bash

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"

set -e

echo "******** OMniLeads Calldata Stats Reset Scheduler ********"
echo "Run django command compilemessages"
$COMMAND compilemessages

echo "Starting Calldata Stats Reset Scheduler"
exec $COMMAND reiniciar_estadisticas_calldata_scheduler
