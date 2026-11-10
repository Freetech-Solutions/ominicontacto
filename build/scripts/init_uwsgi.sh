#!/bin/bash

# Hot path for every omlapp_web replica. Shared-state work (collectstatic,
# actualizar_permisos, regenerar_asterisk) lives in django_runtime_bootstrap.sh
# and must run once per deploy on the bootstrap host — not here.

cd "${INSTALL_PREFIX}/ominicontacto"

set -e

echo "******** OMniLeads UWSGI server ********"

echo "uwsgi.ini settings"
if [[ $UWSGI_CUSTOM == "True" ]]; then
  cat >> "${INSTALL_PREFIX}/run/oml_uwsgi.ini" << EOF
processes=${UWSGI_PROCESSES:-4}
threads=${UWSGI_THREADS:-1}
listen=${UWSGI_LISTEN_QUEUE_SIZE:-2048}
worker-reload-mercy=${UWSGI_WORKER_RELOAD_MERCY:-60}
max-worker-lifetime=${UWSGI_MAX_WORKER_LIFETIME:-7200}
max-worker-lifetime-delta=${UWSGI_MAX_WORKER_LIFETIME_DELTA:-300}
reload-on-rss=${UWSGI_RELOAD_ON_RSS:-1024}
reload-on-as=${UWSGI_RELOAD_ON_AS:-2048}
evil-reload-on-rss=${UWSGI_EVIL_RELOAD_ON_RSS:-3096}
max-requests=${UWSGI_MAX_REQUESTS:-2000}
EOF
fi

chown omnileads:omnileads "${INSTALL_PREFIX}/run/oml_uwsgi.ini"

echo "WA mkdir zip calrec dir with omnileads ownership"
mkdir -p /opt/omnileads/asterisk/var/spool/asterisk/
chown -R omnileads:omnileads /opt/omnileads/asterisk/var/spool/asterisk/ || true

echo "Init uWSGI"
exec uwsgi \
    --ini "${INSTALL_PREFIX}/run/oml_uwsgi.ini" \
    --http-socket "${DJANGO_HOSTNAME}:${UWSGI_PORT}" \
    --stats "${DJANGO_HOSTNAME}:9191" \
    --stats-http
