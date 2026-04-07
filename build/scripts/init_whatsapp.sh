#!/bin/bash

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"

set -e

echo "******** OMniLeads Whatsapp Django Command ********"
echo "Run django command compilemessages"
$COMMAND compilemessages

echo "Background Tasks Worker"
exec $COMMAND msgs-orchestrator
