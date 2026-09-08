#!/usr/bin/env bash
set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_PID=""
MOBILE_PID=""
GESTION_PID=""

limpiar() {
  trap - EXIT INT TERM
  echo
  echo "Cerrando Suite Juviar..."
  [[ -n "$GESTION_PID" ]] && kill "$GESTION_PID" 2>/dev/null || true
  [[ -n "$MOBILE_PID" ]] && kill "$MOBILE_PID" 2>/dev/null || true
  [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "$GESTION_PID" ]] && wait "$GESTION_PID" 2>/dev/null || true
  [[ -n "$MOBILE_PID" ]] && wait "$MOBILE_PID" 2>/dev/null || true
  [[ -n "$API_PID" ]] && wait "$API_PID" 2>/dev/null || true
}
trap limpiar EXIT INT TERM

if [[ ! -x "$RAIZ/.venv/bin/uvicorn" ]]; then
  echo "Error: falta .venv/bin/uvicorn. Instalá primero las dependencias de Python." >&2
  exit 1
fi
if ! command -v pnpm >/dev/null 2>&1; then
  echo "Error: pnpm no está instalado o no está disponible en PATH." >&2
  exit 1
fi

echo "Iniciando backend de prueba en http://127.0.0.1:8000 ..."
(
  cd "$RAIZ/apps/api"
  export SJ_ENTORNO=prueba
  export SJ_HMAC_DATOS_PERSONALES=00000000000000000000000000000000
  export SJ_CLAVE_CIFRADO_DATOS_PERSONALES=00000000000000000000000000000000
  exec "$RAIZ/.venv/bin/uvicorn" suite_juviar.main:app --host 127.0.0.1 --port 8000
) &
API_PID=$!

echo "Iniciando aplicación móvil en http://localhost:3001 ..."
(
  cd "$RAIZ"
  exec pnpm --filter @suite-juviar/mobile dev --hostname 127.0.0.1
) &
MOBILE_PID=$!

echo "Iniciando aplicación de gestión en http://localhost:3002 ..."
(
  cd "$RAIZ"
  export NEXT_PUBLIC_APP_VERSION=0.1.0
  export NEXT_PUBLIC_GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo local)"
  exec pnpm --filter @suite-juviar/gestion dev --hostname 127.0.0.1
) &
GESTION_PID=$!

echo
echo "Suite iniciada:"
echo "  Aplicación móvil: http://localhost:3001"
echo "  Gestión interna:  http://localhost:3002"
echo "  API interactiva:  http://127.0.0.1:8000/docs"
echo "  Usuario depósito: legajo 1210"
echo "  Trabajador prueba: legajo 1042"
echo
echo "Presioná Ctrl+C para cerrar todos los procesos."

while kill -0 "$API_PID" 2>/dev/null && kill -0 "$MOBILE_PID" 2>/dev/null && kill -0 "$GESTION_PID" 2>/dev/null; do
  sleep 1
done

echo "Uno de los procesos terminó inesperadamente." >&2
exit 1
