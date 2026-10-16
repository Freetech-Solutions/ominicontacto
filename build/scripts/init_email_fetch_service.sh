#!/bin/bash

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"

set -e

echo "******** OMniLeads Email Fetch Service ********"
echo "Run django command compilemessages"
$COMMAND compilemessages

echo "Starting Email Fetch Service"
exec $COMMAND run-email-fetch-service
