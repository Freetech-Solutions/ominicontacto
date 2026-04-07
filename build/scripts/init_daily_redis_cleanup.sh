#!/bin/bash

COMMAND="python3 /opt/omnileads/ominicontacto/manage.py"

set -e

echo "******** OMniLeads Daily Redis Cleanup ********"
echo "Run django command compilemessages"
$COMMAND compilemessages

echo "Starting Daily Redis Cleanup Scheduler"
exec $COMMAND daily_redis_cleanup
