#!/usr/bin/env bash
set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="$RAIZ/apps/api/.env.local"

read -r -s -p "Pegá la API key de DeepSeek (no se mostrará): " CLAVE
echo
if [[ "$CLAVE" != sk-* || ${#CLAVE} -lt 30 ]]; then
  echo "No se guardó: eso no parece una API key de DeepSeek. Debe comenzar con sk-." >&2
  exit 1
fi
umask 077
printf 'SJ_SALUD_IA_PROVEEDOR=deepseek\nSJ_SALUD_IA_MODELO=deepseek-flash\nSJ_SALUD_IA_API_KEY=%s\n' "$CLAVE" > "$DESTINO"
chmod 600 "$DESTINO"
unset CLAVE
echo "Configuración guardada fuera de Git. Reiniciá la API para activarla."
