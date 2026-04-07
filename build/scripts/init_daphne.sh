#!/bin/bash

set -e

echo "Init OMniLeads Daphne server"

echo "Iniciando Daphne ASGI"

if [[ $DJANGO_HOSTNAME == "app" ]]; then
    DJANGO_HOSTNAME=0.0.0.0
fi
exec daphne -p ${DAPHNE_PORT} -b ${DJANGO_HOSTNAME} --proxy-headers --verbosity=3 ominicontacto.asgi:application