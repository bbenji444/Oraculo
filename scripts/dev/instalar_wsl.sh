#!/usr/bin/env bash
# Instala y configura en Ubuntu (WSL) todo lo que el proyecto necesita para
# correr en desarrollo: PostgreSQL 16 + PostGIS, Redis, nginx, uv y
# Python 3.12, más el usuario y las bases de datos de la aplicación.
#
# Quién lo usa: `make bootstrap` (o directamente:
#   wsl bash scripts/dev/instalar_wsl.sh
# desde la carpeta del proyecto en PowerShell).
#
# Es idempotente: se puede correr varias veces; lo que ya está instalado o
# creado se deja como está. Por qué existe y por qué sin Docker: ADR-0006.
#
# Qué NO hace: no instala Node ni el frontend (corren en Windows), no arranca
# la API ni el worker (eso es `make up`) y no borra datos existentes.

set -euo pipefail

# --- Constantes ----------------------------------------------------------------

# Versión mayor de PostgreSQL que pide la especificación (sección 5.4).
readonly PG_MAJOR=16
# Versión de uv fijada para que todos instalen la misma. Se eligió la última
# de la serie 0.12 (publicada el 2026-10-08) en lugar de la 0.13.x, recién
# salida, para no estrenar una versión mayor sin necesidad.
readonly UV_VERSION=0.12.24
# Versión de Python que exige CLAUDE.md §6.1.
readonly PYTHON_VERSION=3.12
# Llave y repositorio oficiales de PostgreSQL, según
# https://www.postgresql.org/download/linux/ubuntu/ (configuración manual).
readonly PGDG_KEY_URL="https://www.postgresql.org/media/keys/ACCC4CF8.asc"
readonly PGDG_KEY_PATH="/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc"
readonly PGDG_SOURCES_PATH="/etc/apt/sources.list.d/pgdg.sources"
# `service ... start` regresa antes de que el servicio acepte conexiones
# (medido: Redis tardó ~0.3 s). Se espera hasta este límite antes de fallar.
readonly READY_TIMEOUT_SECONDS=15

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly UV_BIN="${HOME}/.local/bin/uv"

# --- Utilidades ----------------------------------------------------------------

paso() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok() { printf '    \033[32m✔\033[0m %s\n' "$*"; }
aviso() { printf '    \033[33m!\033[0m %s\n' "$*"; }
fallo() { printf '\n\033[1;31m✘ %s\033[0m\n' "$*" >&2; exit 1; }

# Corre un comando como root: directo si ya somos root, con sudo si no.
como_root() {
  if [[ ${EUID} -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

# Corre un comando como el usuario `postgres`, dueño del servidor.
como_postgres() {
  if [[ ${EUID} -eq 0 ]]; then runuser -u postgres -- "$@"; else sudo -u postgres "$@"; fi
}

# Repite un comando cada medio segundo hasta que tenga éxito o se acabe el
# tiempo. Uso: esperar_listo "descripción" comando args...
esperar_listo() {
  local descripcion="$1"; shift
  local intentos=$((READY_TIMEOUT_SECONDS * 2))
  local i
  for ((i = 0; i < intentos; i++)); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  fallo "${descripcion} no estuvo listo en ${READY_TIMEOUT_SECONDS} s."
}

# Carga .env (o lo crea desde .env.example). Se quitan los \r por si alguien
# lo editó con un editor de Windows que guardó en CRLF.
cargar_env() {
  if [[ ! -f "${ROOT_DIR}/.env" ]]; then
    cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
    aviso "No existía .env: se creó a partir de .env.example."
  fi
  # Cuando el proyecto agrega variables a .env.example, un .env viejo no las
  # tiene y la aplicación no arranca. Se agregan las que falten con su valor
  # de ejemplo, sin tocar las que la persona ya configuró.
  local linea clave
  while IFS= read -r linea; do
    [[ "${linea}" =~ ^([A-Z][A-Z0-9_]*)= ]] || continue
    clave="${BASH_REMATCH[1]}"
    if ! grep -q "^${clave}=" "${ROOT_DIR}/.env"; then
      printf '%s\n' "${linea}" >> "${ROOT_DIR}/.env"
      aviso "Se agregó a .env la variable nueva ${clave}."
    fi
  done < <(tr -d '\r' < "${ROOT_DIR}/.env.example")
  set -a
  # shellcheck disable=SC1090  # la ruta se conoce solo en tiempo de ejecución
  source <(tr -d '\r' < "${ROOT_DIR}/.env")
  set +a
  ok ".env cargado"
}

# --- Pasos ---------------------------------------------------------------------

verificar_sistema() {
  paso "Verificando el sistema"
  [[ -r /etc/os-release ]] || fallo "No se encontró /etc/os-release; ¿esto es Ubuntu?"
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "${ID}" == "ubuntu" ]] || fallo "Este script es para Ubuntu; se detectó: ${ID}"
  ok "${PRETTY_NAME} (${VERSION_CODENAME})"
}

instalar_paquetes_base() {
  paso "Instalando paquetes base"
  export DEBIAN_FRONTEND=noninteractive
  como_root apt-get update -qq
  como_root apt-get install -y -qq curl ca-certificates gnupg make postgresql-common >/dev/null
  ok "curl, ca-certificates, gnupg, make, postgresql-common"
}

configurar_repositorio_postgres() {
  paso "Configurando el repositorio oficial de PostgreSQL"
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ -f "${PGDG_SOURCES_PATH}" ]]; then
    ok "Ya existía ${PGDG_SOURCES_PATH}"
    return
  fi
  como_root install -d "$(dirname "${PGDG_KEY_PATH}")"
  como_root curl -fsSL -o "${PGDG_KEY_PATH}" "${PGDG_KEY_URL}"
  como_root tee "${PGDG_SOURCES_PATH}" >/dev/null <<EOF
Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: ${VERSION_CODENAME}-pgdg
Architectures: $(dpkg --print-architecture)
Components: main
Signed-By: ${PGDG_KEY_PATH}
EOF
  como_root apt-get update -qq
  ok "Repositorio ${VERSION_CODENAME}-pgdg agregado"
}

instalar_servicios() {
  paso "Instalando PostgreSQL ${PG_MAJOR} + PostGIS, Redis y nginx"
  export DEBIAN_FRONTEND=noninteractive
  como_root apt-get install -y -qq \
    "postgresql-${PG_MAJOR}" "postgresql-${PG_MAJOR}-postgis-3" redis-server nginx >/dev/null
  ok "postgresql-${PG_MAJOR} $(dpkg-query -W -f='${Version}' "postgresql-${PG_MAJOR}")"
  ok "postgis $(dpkg-query -W -f='${Version}' "postgresql-${PG_MAJOR}-postgis-3")"
  ok "redis-server $(dpkg-query -W -f='${Version}' redis-server)"
  ok "nginx $(dpkg-query -W -f='${Version}' nginx)"
}

instalar_uv_y_python() {
  paso "Instalando uv ${UV_VERSION} y Python ${PYTHON_VERSION}"
  if [[ -x "${UV_BIN}" ]] && "${UV_BIN}" --version | grep -q " ${UV_VERSION}"; then
    ok "uv ${UV_VERSION} ya instalado"
  else
    # Instalador oficial con versión fijada en la URL, según
    # https://docs.astral.sh/uv/getting-started/installation/
    # UV_NO_MODIFY_PATH evita que toque los archivos de perfil de la shell.
    curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | env UV_NO_MODIFY_PATH=1 sh >/dev/null
    ok "$("${UV_BIN}" --version)"
  fi
  "${UV_BIN}" python install "${PYTHON_VERSION}" >/dev/null 2>&1
  ok "$("$("${UV_BIN}" python find "${PYTHON_VERSION}")" --version)"
}

arrancar_postgres() {
  paso "Arrancando PostgreSQL ${PG_MAJOR}"
  # Sin systemd (WSL integrado de Windows), los servicios se manejan con
  # `service`, que usa los scripts clásicos de /etc/init.d.
  como_root service postgresql start >/dev/null
  esperar_listo "PostgreSQL" pg_isready -q -h localhost -p "${POSTGRES_PORT}"
  local puerto
  puerto="$(como_postgres pg_conftool "${PG_MAJOR}" main show port | awk -F' = ' '{print $2}')"
  [[ "${puerto}" == "${POSTGRES_PORT}" ]] \
    || fallo "El clúster ${PG_MAJOR}/main escucha en ${puerto}, pero .env dice POSTGRES_PORT=${POSTGRES_PORT}."
  ok "Clúster ${PG_MAJOR}/main en el puerto ${puerto}"
}

crear_usuario_y_bases() {
  paso "Creando usuario y bases de datos de la aplicación"
  # Variables de psql (:'nombre') para que los valores se citen de forma
  # segura aunque la contraseña tenga caracteres especiales.
  como_postgres psql -X -q -v ON_ERROR_STOP=1 \
    -v db_user="${POSTGRES_USER}" -v db_password="${POSTGRES_PASSWORD}" \
    -v db_name="${POSTGRES_DB}" -v db_test_name="${POSTGRES_TEST_DB}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'db_user') \gexec
-- Se reasigna siempre para que la contraseña coincida con la de .env.
SELECT format('ALTER ROLE %I PASSWORD %L', :'db_user', :'db_password') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db_test_name', :'db_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_test_name') \gexec
SQL
  ok "Usuario ${POSTGRES_USER}; bases ${POSTGRES_DB} y ${POSTGRES_TEST_DB}"

  # PostGIS no es una extensión "confiable": solo un superusuario la puede
  # crear. Por eso se crean aquí y no en las migraciones, que corren con el
  # usuario de la aplicación (la migración inicial solo verifica que existan).
  local base
  for base in "${POSTGRES_DB}" "${POSTGRES_TEST_DB}"; do
    # client_min_messages=warning calla los avisos "already exists" de las
    # corridas repetidas; los errores reales sí se muestran.
    como_postgres psql -X -q -v ON_ERROR_STOP=1 -d "${base}" \
      -c "SET client_min_messages = warning; CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF NOT EXISTS unaccent;"
    ok "Extensiones postgis, pg_trgm y unaccent en ${base}"
  done
}

arrancar_redis() {
  paso "Arrancando Redis"
  como_root service redis-server start >/dev/null
  esperar_listo "Redis" redis-cli ping
  ok "Redis responde $(redis-cli ping)"
}

resumen() {
  paso "Listo"
  ok "$(como_postgres psql -X -qtA -d "${POSTGRES_DB}" -c 'SELECT version()' | cut -d',' -f1)"
  ok "PostGIS $(como_postgres psql -X -qtA -d "${POSTGRES_DB}" -c 'SELECT postgis_lib_version()')"
  ok "$(redis-server --version | cut -d' ' -f1-3)"
  ok "$(nginx -v 2>&1)"
  ok "$("${UV_BIN}" --version)"
}

main() {
  verificar_sistema
  cargar_env
  instalar_paquetes_base
  configurar_repositorio_postgres
  instalar_servicios
  instalar_uv_y_python
  arrancar_postgres
  crear_usuario_y_bases
  arrancar_redis
  resumen
}

main "$@"
