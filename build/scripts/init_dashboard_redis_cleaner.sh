#!/bin/bash

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"

set -e

echo "******** OMniLeads Dashboard Redis Cleaner ********"
echo "Run django command compilemessages"
$COMMAND compilemessages

echo "Starting Dashboard Redis Cleaner Scheduler"
exec $COMMAND clean_dashboard_redis
