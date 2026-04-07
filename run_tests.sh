#!/bin/bash
# Script para ejecutar tests de Django en contenedores Docker (Postgres + Django)
# Uso: ./run_tests.sh [opciones para manage.py test]
# Ejemplo: ./run_tests.sh ominicontacto_app.tests.services.tests_queue_member_service -v 2

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

COMPOSE_FILE="docker-compose.test.yml"
IMAGE_NAME="${IMAGE_NAME:-omnileads-django-test:latest}"

echo -e "${GREEN}** [OMniLeads Django] Ejecutando tests en Docker **${NC}"

# Verificar si Docker está disponible
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker no está instalado o no está en el PATH${NC}"
    exit 1
fi

# Verificar docker-compose (v2: docker compose, v1: docker-compose)
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo -e "${RED}Error: docker-compose no está instalado (usa 'docker compose' o 'docker-compose')${NC}"
    exit 1
fi

# Construir la imagen si no existe o si se fuerza
if [ "${BUILD_IMAGE:-false}" = "true" ] || ! docker image inspect "$IMAGE_NAME" &> /dev/null; then
    echo -e "${YELLOW}Construyendo imagen Docker...${NC}"
    $COMPOSE_CMD -f "$COMPOSE_FILE" build django-test
fi

# Ejecutar tests (postgres se levanta automáticamente; argumentos extra se pasan a manage.py test)
echo -e "${GREEN}Ejecutando tests en contenedor...${NC}"

if [ $# -gt 0 ]; then
    $COMPOSE_CMD -f "$COMPOSE_FILE" run --rm django-test python manage.py test --settings=ominicontacto.settings.tests_docker "$@"
else
    $COMPOSE_CMD -f "$COMPOSE_FILE" run --rm django-test
fi

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Tests ejecutados exitosamente${NC}"
else
    echo -e "${RED}❌ Tests fallaron con código de salida: $EXIT_CODE${NC}"
fi

exit $EXIT_CODE
