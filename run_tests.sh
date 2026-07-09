#!/bin/bash
# Ejecutar tests de Django en local (Postgres + Redis en localhost:5432 / localhost:6379).
#
# Uso:
#   ./run_tests.sh --up                    # solo levanta Postgres y Redis en localhost
#   ./run_tests.sh                         # suite completa (contenedor + código montado)
#   ./run_tests.sh reportes_app.tests...   # módulos concretos
#   ./run_tests.sh --down                  # baja Postgres y Redis
#
# El runner usa docker-compose.test.yml: el código del host se monta en el contenedor,
# así los cambios se ven sin reconstruir la imagen.

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.test.yml"
IMAGE_NAME="${IMAGE_NAME:-omnileads-django-test:latest}"
SETTINGS="${DJANGO_TEST_SETTINGS:-ominicontacto.settings.tests_docker}"

if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo -e "${RED}Error: docker compose no está instalado${NC}"
    exit 1
fi

compose_up() {
    echo -e "${GREEN}Levantando Postgres (127.0.0.1:5432) y Redis (127.0.0.1:6379)...${NC}"
    $COMPOSE_CMD -f "$COMPOSE_FILE" up -d postgres redis
    echo -e "${GREEN}Esperando Postgres...${NC}"
    $COMPOSE_CMD -f "$COMPOSE_FILE" exec -T postgres pg_isready -U omnileads
    echo -e "${GREEN}Dependencias listas en localhost.${NC}"
}

compose_down() {
    echo -e "${YELLOW}Deteniendo Postgres y Redis...${NC}"
    $COMPOSE_CMD -f "$COMPOSE_FILE" down
}

ensure_image() {
    if [ "${BUILD_IMAGE:-false}" = "true" ] || ! docker image inspect "$IMAGE_NAME" &> /dev/null; then
        echo -e "${YELLOW}Construyendo imagen Docker (primera vez o BUILD_IMAGE=true)...${NC}"
        $COMPOSE_CMD -f "$COMPOSE_FILE" build django-test
    fi
}

run_tests_in_container() {
    ensure_image
    compose_up
    echo -e "${GREEN}Ejecutando tests en contenedor (settings: ${SETTINGS})...${NC}"
    if [ $# -gt 0 ]; then
        $COMPOSE_CMD -f "$COMPOSE_FILE" run --rm django-test \
            python manage.py test --settings="$SETTINGS" --noinput "$@"
    else
        $COMPOSE_CMD -f "$COMPOSE_FILE" run --rm django-test \
            python manage.py test --settings="$SETTINGS" --noinput
    fi
}

case "${1:-}" in
    --up)
        compose_up
        ;;
    --down)
        compose_down
        ;;
    --help|-h)
        sed -n '2,12p' "$0"
        ;;
    *)
        echo -e "${GREEN}** [OMniLeads Django] Tests en local **${NC}"
        run_tests_in_container "$@"
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 0 ]; then
            echo -e "${GREEN}Tests OK${NC}"
        else
            echo -e "${RED}Tests fallaron (exit ${EXIT_CODE})${NC}"
        fi
        exit $EXIT_CODE
        ;;
esac
