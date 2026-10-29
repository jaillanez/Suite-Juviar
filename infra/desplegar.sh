#!/usr/bin/env bash
# Instala en el servidor una versión guardada en GitHub y la pone en marcha.
#
# Uso, como root en el servidor:
#   bash /opt/suite-juviar-releases/actual/infra/desplegar.sh            # instala main
#   bash /opt/suite-juviar-releases/actual/infra/desplegar.sh <commit>   # instala una versión puntual
#   bash /opt/suite-juviar-releases/actual/infra/desplegar.sh --volver   # vuelve a la versión anterior
#
# Se ejecuta desde la versión instalada (de root), nunca desde /opt/suite-juviar, que es
# del usuario «suite».
#
# Cada versión queda en su propia carpeta, /opt/suite-juviar-releases/<commit>,
# copiada tal cual de Git. Los servicios leen siempre /opt/suite-juviar-releases/actual,
# que apunta a una de esas carpetas. Si algún servicio no arranca, se vuelve solo a la
# versión que estaba antes. /opt/suite-juviar queda solo como copia de Git y entorno de
# Python: si alguien editó archivos a mano ahí, el script se niega a seguir.
#
# Gestión (pantallas internas con usuario y contraseña) corre aparte, en un contenedor de
# Docker que se arma con la misma versión. Solo se toca si está instalada, es decir, si
# existe /etc/suite/gestion.env.
#
# Como root solo se cambian enlaces, archivos de systemd y permisos. Todo lo que ejecuta
# código de /opt/suite-juviar (git, pip, python) corre como el usuario «suite», que es
# dueño de esa carpeta: así nadie que pueda escribir ahí consigue ejecutar como root.
set -Eeuo pipefail

FUENTE=/opt/suite-juviar
RELEASES=/opt/suite-juviar-releases
ACTUAL="$RELEASES/actual"
ANTERIOR="$RELEASES/anterior"
VENV="$FUENTE/.venv"
CONSERVAR=5
REPO_ESPERADO=https://github.com/jaillanez/Suite-Juviar.git
COMO_SUITE=(runuser -u suite --)
GIT=("${COMO_SUITE[@]}" git -C "$FUENTE")

# servicio | carpeta de trabajo | PYTHONPATH  (@ = carpeta de la versión activa)
SERVICIOS=(
  "consulta-publica|@|@/apps/consulta/src"
  "bot-whatsapp|@|@/apps/consulta/src"
  "bot-simulador|@|@:@/apps/consulta/src"
  "fila-web|@|@:@/apps/fila/src"
  "fila-worker|@|@:@/apps/fila/src"
  "contactos-publicador|@|@/apps/api/src"
  "recepcion-nocturna|@/apps/api|@/apps/api/src"
  "recepcion-ventana|@/apps/api|@/apps/api/src"
)
# Módulo que cada servicio carga al arrancar; se prueba antes de cambiar de versión.
declare -A MODULO=(
  [consulta-publica]=consulta_publica.main
  [bot-whatsapp]=consulta_publica.bot.worker
  [fila-web]=fila_app.main
  [fila-worker]=fila_app.worker
  [contactos-publicador]=suite_juviar.workers.contactos_worker
  [recepcion-ventana]=suite_juviar.modulos.recepcion.integracion_oracle.worker
)
# Direcciones que tienen que responder después del cambio, y qué respuesta vale.
# La consulta pública no tiene ruta de salud: alcanza con que la aplicación conteste.
declare -A URL=([consulta-publica]=http://172.18.0.1:8021/ [fila-web]=http://172.18.0.1:8022/health)
declare -A ESPERADO=([consulta-publica]='^[234][0-9][0-9]$' [fila-web]='^200$')

GESTION_ENV=/etc/suite/gestion.env
GESTION_IMAGEN=suite-juviar-gestion
GESTION_CONTENEDOR=suite-juviar-gestion

paso() { printf '\n==> %s\n' "$*"; }
falla() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || falla "correlo como root."
ESTE=$(readlink -f "${BASH_SOURCE[0]}")
[[ $ESTE == "$RELEASES/"* ]] || falla "corré el script desde $ACTUAL/infra/desplegar.sh, no desde $FUENTE."
[[ $(stat -c '%u %a' "$ESTE") =~ ^0\ [0-7][0-5][0-5]$ ]] || falla "el script no es de root o lo pueden modificar otros."
exec 9>/run/suite-juviar-desplegar.lock
flock -n 9 || falla "ya hay otra actualización en curso."

campo() { cut -d'|' -f"$2" <<<"$1"; }
ruta() { echo "${1//@/$2}"; }

escribir_dropins() {  # $1 = carpeta a la que apuntan los servicios
  local linea svc wd pp
  for linea in "${SERVICIOS[@]}"; do
    svc=$(campo "$linea" 1)
    wd=$(ruta "$(campo "$linea" 2)" "$1")
    pp=$(ruta "$(campo "$linea" 3)" "$1")
    mkdir -p "/etc/systemd/system/$svc.service.d"
    printf '[Service]\nWorkingDirectory=%s\nEnvironment=PYTHONPATH=%s\n' "$wd" "$pp" \
      >"/etc/systemd/system/$svc.service.d/release.conf"
  done
  systemctl daemon-reload
}

servicios_en_marcha() {
  local linea svc
  for linea in "${SERVICIOS[@]}"; do
    svc=$(campo "$linea" 1)
    if systemctl is-active -q "$svc" && [[ $(systemctl show -p Type --value "$svc") != oneshot ]]; then
      echo "$svc"
    fi
  done
}

comprobar() {  # $@ = servicios que tienen que quedar funcionando
  local svc codigo intento
  sleep 5
  for svc in "$@"; do
    systemctl is-active -q "$svc" || { echo "  $svc no quedó en marcha"; return 1; }
    if [[ -n ${URL[$svc]:-} ]]; then
      for intento in 1 2 3 4 5 6; do
        codigo=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "${URL[$svc]}") || codigo=000
        [[ $codigo =~ ${ESPERADO[$svc]} ]] && break
        sleep 2
      done
      [[ $codigo =~ ${ESPERADO[$svc]} ]] || { echo "  $svc respondió $codigo en ${URL[$svc]}"; return 1; }
    fi
    echo "  $svc: bien"
  done
}

cambiar_a() {  # $1 = carpeta de la versión nueva
  local nueva=$1 previa en_marcha
  previa=$(readlink -f "$ACTUAL" 2>/dev/null || true)
  mapfile -t en_marcha < <(servicios_en_marcha)
  [[ ${#en_marcha[@]} -gt 0 ]] || falla "no hay ningún servicio de la suite en marcha; revisá el servidor antes de actualizar."

  paso "Cambiando a $(basename "$nueva")"
  ln -sfn "$nueva" "$ACTUAL.nuevo" && mv -Tf "$ACTUAL.nuevo" "$ACTUAL"
  escribir_dropins "$ACTUAL"
  systemctl restart "${en_marcha[@]}"

  paso "Comprobando que todo quedó funcionando"
  if comprobar "${en_marcha[@]}"; then
    if [[ -n $previa && $previa != "$nueva" ]]; then
      ln -sfn "$previa" "$ANTERIOR.nuevo" && mv -Tf "$ANTERIOR.nuevo" "$ANTERIOR"
    fi
    return 0
  fi

  [[ -n $previa ]] || falla "la versión nueva no arrancó y no hay una anterior a la que volver."
  paso "Algo falló: volviendo a $(basename "$previa")"
  ln -sfn "$previa" "$ACTUAL.nuevo" && mv -Tf "$ACTUAL.nuevo" "$ACTUAL"
  systemctl restart "${en_marcha[@]}"
  comprobar "${en_marcha[@]}" || true
  falla "la versión $(basename "$nueva") no arrancó; quedó funcionando $(basename "$previa"). Revisá: journalctl -u <servicio> -n 50"
}

gestion_instalada() { [[ -f $GESTION_ENV ]]; }
gestion_version() { docker inspect -f '{{.Config.Image}}' "$GESTION_CONTENEDOR" 2>/dev/null | sed 's/.*://'; }

construir_gestion() {  # $1 = carpeta de la versión, $2 = commit corto
  gestion_instalada || return 0
  [[ -f $1/infra/gestion/Dockerfile ]] || falla "la versión $2 no trae infra/gestion/Dockerfile."
  docker image inspect "$GESTION_IMAGEN:$2" >/dev/null 2>&1 && return 0
  paso "Armando Gestión $2 (tarda unos minutos)"
  docker build -q -f "$1/infra/gestion/Dockerfile" --build-arg "COMMIT=$2" \
    -t "$GESTION_IMAGEN:$2" "$1" >/dev/null || falla "Gestión $2 no se pudo armar. No se cambió nada en marcha."
}

poner_gestion() {  # $1 = carpeta con el compose, $2 = versión de la imagen
  VERSION=$2 docker compose -f "$1/infra/gestion/compose.yaml" up -d >/dev/null 2>&1
}

gestion_responde() {
  local intento
  for intento in $(seq 1 30); do
    docker exec "$GESTION_CONTENEDOR" python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ingreso/estado',timeout=3)" \
      >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

cambiar_gestion() {  # $1 = carpeta de la versión, $2 = commit corto
  gestion_instalada || return 0
  local previa
  previa=$(gestion_version)
  [[ $previa == "$2" ]] && return 0
  paso "Cambiando Gestión a $2"
  if poner_gestion "$1" "$2" && gestion_responde; then
    echo "  gestión: bien"
    return 0
  fi
  if [[ -n $previa ]] && docker image inspect "$GESTION_IMAGEN:$previa" >/dev/null 2>&1; then
    paso "Gestión no respondió: volviendo a $previa"
    poner_gestion "$1" "$previa" && gestion_responde || true
    falla "Gestión $2 no arrancó; quedó funcionando $previa. Revisá: docker logs $GESTION_CONTENEDOR"
  fi
  falla "Gestión $2 no arrancó. Revisá: docker logs $GESTION_CONTENEDOR"
}

if [[ ${1:-} == --volver ]]; then
  [[ -L $ANTERIOR ]] || falla "no hay versión anterior registrada."
  VUELTA=$(readlink -f "$ANTERIOR")
  cambiar_a "$VUELTA"
  if gestion_instalada && docker image inspect "$GESTION_IMAGEN:$(basename "$VUELTA")" >/dev/null 2>&1; then
    cambiar_gestion "$VUELTA" "$(basename "$VUELTA")"
  fi
  paso "Listo: quedó funcionando $(basename "$(readlink -f "$ACTUAL")")."
  exit 0
fi
REF=${1:-main}
[[ $REF =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || falla "nombre de versión no válido: '$REF'."

paso "Revisando que nadie haya editado archivos a mano en $FUENTE"
if [[ -n $("${GIT[@]}" status --porcelain --untracked-files=no) ]]; then
  "${GIT[@]}" status --short --untracked-files=no
  falla "hay archivos modificados a mano en $FUENTE. Guardalos en Git o descartalos antes de actualizar."
fi

paso "Trayendo la versión '$REF' desde GitHub"
# La dirección va fija acá: no se toma de la configuración de la copia, que es de «suite».
"${GIT[@]}" fetch -q --prune "$REPO_ESPERADO" "+refs/heads/*:refs/remotes/origin/*"
if [[ $REF =~ ^[0-9a-f]{7,40}$ ]]; then
  # Un commit suelto solo vale si ya está en alguna rama de GitHub.
  SHA=$("${GIT[@]}" rev-parse --verify -q "$REF^{commit}") || falla "no encontré la versión '$REF'."
  [[ -n $("${GIT[@]}" for-each-ref --contains "$SHA" refs/remotes/origin/) ]] \
    || falla "la versión '$REF' no está en GitHub."
else
  SHA=$("${GIT[@]}" rev-parse --verify -q "refs/remotes/origin/$REF^{commit}") || falla "no encontré la rama '$REF' en GitHub."
fi
CORTO=${SHA:0:7}
NUEVA="$RELEASES/$CORTO"
echo "  $CORTO $("${GIT[@]}" log -1 --format='%ad %s' --date=short "$SHA")"

if [[ ! -d $NUEVA ]]; then
  paso "Copiando la versión a $NUEVA"
  # Se extrae como root en una carpeta que «suite» no puede tocar mientras tanto.
  # La versión instalada queda de root: los servicios la leen pero no la pueden cambiar.
  TMP=$(mktemp -d "$RELEASES/.tmp-$CORTO-XXXX")
  trap 'rm -rf "$TMP"' EXIT
  "${GIT[@]}" archive "$SHA" | (umask 022 && tar -x --no-same-owner --no-same-permissions -C "$TMP")
  # El contenido sale de una copia de «suite»: nada de dispositivos ni permisos especiales.
  if [[ -n $(find "$TMP" \( -type b -o -type c -o -type p -o -type s -o -perm /6000 \) -print -quit) ]]; then
    falla "la versión $CORTO trae archivos especiales; no se instala."
  fi
  chown -R root:root "$TMP"
  chmod -R u=rwX,go=rX "$TMP"
  mv -T "$TMP" "$NUEVA"
  trap - EXIT
fi

paso "Instalando las dependencias de Python que falten"
mapfile -t DEPENDENCIAS < <("${COMO_SUITE[@]}" "$VENV/bin/python" - "$NUEVA" <<'PY'
import sys, tomllib, pathlib
raiz = pathlib.Path(sys.argv[1])
vistas = set()
# Solo las aplicaciones que corren como servicio con sus propias dependencias. Las de
# apps/api (gestión) no se instalan acá: piden versiones distintas (p. ej. reportlab<5)
# y los procesos de fondo que usan su código se validan con la prueba de carga.
for app in ("consulta", "fila"):
    archivo = raiz / "apps" / app / "pyproject.toml"
    if archivo.exists():
        for dep in tomllib.loads(archivo.read_text())["project"].get("dependencies", []):
            if dep not in vistas:
                vistas.add(dep)
                print(dep)
PY
)
for dep in "${DEPENDENCIAS[@]}"; do
  [[ $dep =~ ^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?[[:space:]]*([=<>!~]=?[[:space:]]*[A-Za-z0-9.*+-]+[[:space:]]*,?[[:space:]]*)*$ ]] \
    || falla "dependencia con formato inesperado: '$dep'."
done
"${COMO_SUITE[@]}" "$VENV/bin/pip" install -q --disable-pip-version-check -- "${DEPENDENCIAS[@]}"

paso "Probando que cada servicio cargue con la versión nueva"
for linea in "${SERVICIOS[@]}"; do
  svc=$(campo "$linea" 1)
  [[ -n ${MODULO[$svc]:-} ]] || continue
  # Mismas claves que el servicio, pero sin red y sin poder escribir en el sistema.
  propiedades=(-p User=suite -p Group=suite -p "WorkingDirectory=$(ruta "$(campo "$linea" 2)" "$NUEVA")"
    -p NoNewPrivileges=yes -p ProtectSystem=strict -p PrivateTmp=yes -p PrivateNetwork=yes
    -p RuntimeMaxSec=60 -E PYTHONDONTWRITEBYTECODE=1 -E MPLCONFIGDIR=/tmp)
  while read -r archivo _; do
    [[ -n $archivo ]] && propiedades+=(-p "EnvironmentFile=$archivo")
  done < <(systemctl show -p EnvironmentFiles --value "$svc.service" | tr ';' '\n')
  if ! systemd-run --quiet --wait --pipe --collect "${propiedades[@]}" \
      -E "PYTHONPATH=$(ruta "$(campo "$linea" 3)" "$NUEVA")" \
      "$VENV/bin/python" -c "import importlib; importlib.import_module('${MODULO[$svc]}')"; then
    falla "$svc no carga con la versión $CORTO. No se cambió nada en marcha."
  fi
  echo "  $svc: bien"
done

construir_gestion "$NUEVA" "$CORTO"

cambiar_a "$NUEVA"
cambiar_gestion "$NUEVA" "$CORTO"

paso "Dejando la copia de Git en la misma versión"
"${GIT[@]}" checkout -q -f --detach "$SHA"

paso "Borrando versiones viejas (se conservan las últimas $CONSERVAR)"
mantener=("$(readlink -f "$ACTUAL")" "$(readlink -f "$ANTERIOR" 2>/dev/null || true)")
mapfile -t VIEJAS < <(find "$RELEASES" -mindepth 1 -maxdepth 1 -type d ! -name '.*' -printf '%T@ %p\n' \
  | sort -rn | tail -n +$((CONSERVAR + 1)) | cut -d' ' -f2-)
for vieja in "${VIEJAS[@]}"; do
  [[ " ${mantener[*]} " == *" $vieja "* ]] && continue
  rm -rf -- "$vieja" && echo "  borrada $(basename "$vieja")"
  docker image rm -f "$GESTION_IMAGEN:$(basename "$vieja")" >/dev/null 2>&1 || true
done

paso "Listo: quedó funcionando $CORTO."
