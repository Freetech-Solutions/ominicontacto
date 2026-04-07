#!/bin/bash

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"

set -e

echo "******** OMniLeads Background Tasks Worker ********"
echo "Run django command compilemessages"
$COMMAND compilemessages

echo "Background Tasks Worker"
exec $COMMAND runworker background-tasks
