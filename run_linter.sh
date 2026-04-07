#!/bin/bash
# Script para ejecutar flake8 linter en un contenedor Docker para Django

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

IMAGE_NAME="${IMAGE_NAME:-python:3.12-slim}"
CONTAINER_NAME="django-linter-$(date +%s)"

echo -e "${GREEN}** [OMniLeads Django] Ejecutando Flake8 Linter en Contenedor **${NC}"

# Verificar si Docker está disponible
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker no está instalado o no está en el PATH${NC}"
    exit 1
fi

# Verificar que estamos en el directorio correcto
if [ ! -f ".flake8" ]; then
    echo -e "${RED}Error: No se encontró el archivo .flake8 en el directorio actual${NC}"
    echo -e "${YELLOW}Por favor, ejecuta este script desde el directorio raíz de Django${NC}"
    exit 1
fi

# Verificar si la imagen existe
if ! docker image inspect "$IMAGE_NAME" &> /dev/null; then
    echo -e "${YELLOW}La imagen $IMAGE_NAME no existe localmente. Se descargará automáticamente.${NC}"
fi

# Crear contenedor temporal y ejecutar linter
echo -e "${BLUE}Ejecutando flake8 en contenedor...${NC}"

# Opciones adicionales de flake8
FLAKE8_OPTS="${FLAKE8_OPTS:---statistics --count}"

# Directorios a analizar (excluyendo los que están en .flake8)
PYTHON_DIRS="api_app configuracion_telefonia_app dashboard_camp_app notification_app \
             ominicontacto ominicontacto_app orquestador_app reciclado_app reportes_app \
             supervision_app whatsapp_app tests utiles_globales.py manage.py checks.py"

docker run --rm \
    --name "$CONTAINER_NAME" \
    -v "$(pwd):/opt/omnileads:ro" \
    -w /opt/omnileads \
    "$IMAGE_NAME" \
    bash -c "
        set -euo pipefail && \
        apt-get update -qq > /dev/null 2>&1 && \
        apt-get install -y -qq --no-install-recommends git > /dev/null 2>&1 && \
        pip install --no-cache-dir -q flake8 > /dev/null 2>&1 && \
        flake8 $PYTHON_DIRS --config=.flake8 $FLAKE8_OPTS
    "

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Linter ejecutado exitosamente - No se encontraron errores${NC}"
else
    echo -e "${RED}❌ Linter encontró errores (código de salida: $EXIT_CODE)${NC}"
fi

exit $EXIT_CODE
