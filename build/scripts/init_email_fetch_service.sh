#!/bin/bash

COMMAND="python3 ${INSTALL_PREFIX}/ominicontacto/manage.py"

set -e

echo "******** OMniLeads email-fetch-service Django Command ********"

exec $COMMAND run-email-fetch-service
