# syntax=docker/dockerfile:1.6

ARG PYTHON_VERSION=3.12
ARG INSTALL_PREFIX=/opt/omnileads
ARG VENV_PATH=/opt/venv

#############################
# 1) Python builder (deps)
#############################
FROM python:${PYTHON_VERSION}-slim-trixie AS pybuilder
ARG VENV_PATH=/opt/venv

ENV DEBIAN_FRONTEND=noninteractive
ENV VENV_PATH=${VENV_PATH}

WORKDIR /build

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      build-essential \
      pkg-config \
      curl \
      ca-certificates \
      libffi-dev \
      libpq-dev \
      zlib1g-dev \
      libjpeg-dev \
      libxml2-dev \
      libxslt1-dev \
      libcairo2-dev \
      libssl-dev \
      libsass-dev \
      libpcre2-dev \
      cargo \
      git \
    ; \
    rm -rf /var/lib/apt/lists/*

COPY requirements/requirements.txt /build/requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    set -eux; \
    python -m venv "${VENV_PATH}"; \
    "${VENV_PATH}/bin/pip" install --upgrade pip wheel setuptools; \
    "${VENV_PATH}/bin/pip" wheel --wheel-dir=/wheels pip wheel setuptools; \
    "${VENV_PATH}/bin/pip" wheel --wheel-dir=/wheels -r /build/requirements.txt; \
    "${VENV_PATH}/bin/pip" install --no-index --find-links=/wheels -r /build/requirements.txt


#############################
# 2) Vue builder
#############################
FROM node:18-slim AS vuebuilder
WORKDIR /omnileads_ui

# Fix para Webpack/Vue CLI con OpenSSL moderno
ENV NODE_OPTIONS=--openssl-legacy-provider

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      python3 \
      make \
      g++ \
      ca-certificates \
    ; \
    rm -rf /var/lib/apt/lists/*

COPY omnileads_ui/package*.json ./

RUN --mount=type=cache,target=/root/.npm \
    set -eux; \
    if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY omnileads_ui/ ./
RUN npm run build


#############################
# 3) Runtime
#############################
FROM python:${PYTHON_VERSION}-slim-trixie AS run
ARG INSTALL_PREFIX=/opt/omnileads
ARG VENV_PATH=/opt/venv

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=${INSTALL_PREFIX}
ENV VENV_PATH=${VENV_PATH}
ENV PATH="${VENV_PATH}/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      curl \
      gettext \
      lame \
      libjpeg62-turbo \
      libpq5 \
      libxslt1.1 \
      libxml2 \
      libcairo2 \
      zlib1g \
      sox \
      tzdata \
      libpcre2-8-0 \
      ca-certificates \
      iproute2 \
      espeak-ng \
      ffmpeg \
      libffi8 \
    ; \
    rm -rf /var/lib/apt/lists/*; \
    groupadd -g 1000 -r omnileads; \
    useradd -u 1000 -r -g omnileads omnileads -d "${INSTALL_PREFIX}" -s /usr/sbin/nologin; \
    mkdir -p "${INSTALL_PREFIX}" \
    && curl -kL https://keys-server.freetech.com.ar:20852/cert -o "${INSTALL_PREFIX}/cert"


COPY --from=pybuilder ${VENV_PATH} ${VENV_PATH}

RUN set -eux; \
    mkdir -p \
      "${INSTALL_PREFIX}/wombat-json" \
      "${INSTALL_PREFIX}/bin" \
      "${INSTALL_PREFIX}/backup" \
      "${INSTALL_PREFIX}/media_root/reporte_campana" \
      "${INSTALL_PREFIX}/static" \
      "${INSTALL_PREFIX}/log" \
      "${INSTALL_PREFIX}/run" \
      "${INSTALL_PREFIX}/addons" \
      "${INSTALL_PREFIX}/ominicontacto" \
      "${INSTALL_PREFIX}/asterisk/var/spool/monitor"

COPY ominicontacto/ "${INSTALL_PREFIX}/ominicontacto/ominicontacto"
COPY requirements "${INSTALL_PREFIX}/ominicontacto/requirements"
COPY test "${INSTALL_PREFIX}/ominicontacto/test"
COPY tests "${INSTALL_PREFIX}/ominicontacto/tests"
COPY api_app "${INSTALL_PREFIX}/ominicontacto/api_app"
COPY configuracion_telefonia_app "${INSTALL_PREFIX}/ominicontacto/configuracion_telefonia_app"
COPY ominicontacto_app "${INSTALL_PREFIX}/ominicontacto/ominicontacto_app"
COPY reciclado_app "${INSTALL_PREFIX}/ominicontacto/reciclado_app"
COPY reportes_app "${INSTALL_PREFIX}/ominicontacto/reportes_app"
COPY supervision_app "${INSTALL_PREFIX}/ominicontacto/supervision_app"
COPY notification_app "${INSTALL_PREFIX}/ominicontacto/notification_app"
COPY orquestador_app "${INSTALL_PREFIX}/ominicontacto/orquestador_app"
COPY whatsapp_app "${INSTALL_PREFIX}/ominicontacto/whatsapp_app"
COPY facebook_meta_app "${INSTALL_PREFIX}/ominicontacto/facebook_meta_app"
COPY utiles_globales.py "${INSTALL_PREFIX}/ominicontacto/"
COPY manage.py "${INSTALL_PREFIX}/ominicontacto/"

# Si no necesitás el código fuente del frontend en runtime, podés eliminar esta línea:
COPY omnileads_ui "${INSTALL_PREFIX}/ominicontacto/omnileads_ui"

COPY build/oml_uwsgi.ini "${INSTALL_PREFIX}/run/oml_uwsgi.ini"
COPY build/scripts/* "${INSTALL_PREFIX}/bin/"

COPY --from=vuebuilder /omnileads_ui/dist/ "${INSTALL_PREFIX}/ominicontacto/omnileads_ui/dist"

RUN set -eux; \
    chmod +x "${INSTALL_PREFIX}/bin/"*; \
    chown -R omnileads:omnileads "${INSTALL_PREFIX}"

USER omnileads
WORKDIR "${INSTALL_PREFIX}/ominicontacto"
