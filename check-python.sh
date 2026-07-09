#!/bin/bash

# Valida archivos Python modificados en el MR o, en pipelines web/push,
# los del último commit (mismo criterio que check-js.sh).

set -euo pipefail

if [[ -n "${CI_MERGE_REQUEST_TARGET_BRANCH_NAME:-}" ]]; then
  TARGET_BRANCH_SHA=$(git rev-parse "origin/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}")
  STAGED_FILES=$(
    git diff "${TARGET_BRANCH_SHA}"...HEAD --name-only --diff-filter=ACM | grep '\.py$' || true
  )
elif git rev-parse HEAD~1 >/dev/null 2>&1; then
  echo "Pipeline sin MR: validando archivos Python del último commit."
  STAGED_FILES=$(
    git diff HEAD~1...HEAD --name-only --diff-filter=ACM | grep '\.py$' || true
  )
else
  echo "Pipeline sin MR ni commit anterior; se omite flake8."
  exit 0
fi

if [[ -z "${STAGED_FILES}" ]]; then
  echo "No hay archivos Python modificados; se omite flake8."
  exit 0
fi

PASS=true

echo -e "\nValidating Python code:\n"

if ! command -v flake8 >/dev/null 2>&1; then
  echo "flake8 no está instalado."
  exit 1
fi

for FILE in ${STAGED_FILES}; do
  if flake8 "${FILE}"; then
    echo "Flake8 passed: ${FILE}"
  else
    echo "Flake8 failed: ${FILE}"
    PASS=false
  fi
done

echo -e "\nPython validation completed!\n"

if ! ${PASS}; then
  echo "COMMIT FAILED: hay archivos Python que no pasan flake8. Corregí los errores e intentá de nuevo."
  exit 1
fi

echo "COMMIT SUCCEEDED"
exit 0
