#!/usr/bin/env bash
# Verificación local completa contra PostgreSQL instalado en la máquina.
# Crea las dos bases si no existen, aplica migraciones y corre las pruebas.
set -euo pipefail
cd "$(dirname "$0")/.."

export TEST_DSN_ADMIN_DMZ="${TEST_DSN_ADMIN_DMZ:-postgresql://localhost:5432/juviar_web_local}"
export TEST_DSN_SITIO="${TEST_DSN_SITIO:-postgresql://web_sitio:sitio_local@localhost:5432/juviar_web_local}"
export TEST_DSN_WORKER="${TEST_DSN_WORKER:-postgresql://web_worker:worker_local@localhost:5432/juviar_web_local}"
export TEST_DSN_SUITE="${TEST_DSN_SUITE:-postgresql://localhost:5432/juviar_suite_local}"

PID=""
limpiar() {
  if [[ -n "$PID" ]]; then
    kill "$PID" 2>/dev/null || true
  fi
  psql "$TEST_DSN_ADMIN_DMZ" -c "TRUNCATE web.bandeja_solicitudes;" >/dev/null 2>&1 || true
  psql "$TEST_DSN_SUITE" -c "TRUNCATE comercial.solicitud_muestra;" >/dev/null 2>&1 || true
}
trap limpiar EXIT

echo "==> 1/5 preparando PostgreSQL local"
pg_isready -h 127.0.0.1 -p 5432 >/dev/null
if ! psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'juviar_web_local'" | grep -q 1; then
  createdb juviar_web_local
fi
if ! psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'juviar_suite_local'" | grep -q 1; then
  createdb juviar_suite_local
fi

echo "==> 2/6 verificacion 1: permisos del rol del sitio"
python -m pytest -c apps/api/pyproject.toml tests/verificacion/test_1_permisos_rol_sitio.py -m local -q

echo "==> 3/6 verificacion 2: concurrencia del worker"
python -m pytest -c apps/api/pyproject.toml tests/verificacion/test_2_worker_concurrente.py -m local -q

echo "==> 4/6 verificacion 3: permisos aplicados en modulos internos"
python -m pytest -c apps/api/pyproject.toml tests/verificacion/test_4_permisos_modulos.py -m local -q

echo "==> 5/6 verificacion 4: rate limit CON --proxy-headers (debe pasar)"
export WEB_DSN_DMZ="$TEST_DSN_SITIO"
export WEB_LIMITE_HORA=10
export WEB_ENTORNO=local
uvicorn apps.web.main:app --host 127.0.0.1 --port 8080 --proxy-headers &
PID=$!
sleep 3
python -m pytest -c apps/api/pyproject.toml tests/verificacion/test_3_rate_limit_proxy.py -m local -q
kill $PID; wait $PID 2>/dev/null || true
PID=""

echo "==> 6/6 control negativo: SIN --proxy-headers (test_ip_distinta DEBE fallar)"
uvicorn apps.web.main:app --host 127.0.0.1 --port 8080 --no-proxy-headers &
PID=$!
sleep 3
if python -m pytest -c apps/api/pyproject.toml tests/verificacion/test_3_rate_limit_proxy.py::test_ip_distinta_no_consume_el_cupo_ajena -m local -q; then
  echo "!! ALERTA: paso sin --proxy-headers. La prueba no esta midiendo lo que dice."
  exit 1
else
  echo "   ok: falla como se espera, la prueba mide de verdad"
fi
kill $PID; wait $PID 2>/dev/null || true
PID=""

echo "==> verificacion local completa"
