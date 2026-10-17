#!/usr/bin/env bash
# Instala y configura en Ubuntu (WSL) todo lo que el proyecto necesita para
# correr en desarrollo: PostgreSQL 16 + PostGIS, Redis, nginx, uv y
# Python 3.12 con las dependencias del backend, las herramientas de geodatos
# (GDAL, tippecanoe y pmtiles), más el usuario y las bases de datos.
#
# Quién lo usa: `make bootstrap` (o directamente:
#   wsl bash scripts/dev/instalar_wsl.sh
# desde la carpeta del proyecto en PowerShell).
#
# Es idempotente: se puede correr varias veces; lo que ya está instalado o
# creado se deja como está. Por qué existe y por qué sin Docker: ADR-0006.
#
# Qué NO hace: no instala las dependencias del frontend (corren en Windows;
# `make bootstrap` las instala aparte con el npm de Windows), no arranca la
# API ni el worker (eso es `make up`) y no borra datos existentes.

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
# CLI de PMTiles (extraer el mapa base y verificar archivos, ADR-0008).
# Versión y SHA-256 publicados por GitHub para el binario de Linux x86_64:
# https://github.com/protomaps/go-pmtiles/releases/tag/v1.31.2
readonly PMTILES_VERSION=1.31.2
readonly PMTILES_SHA256="3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f"
readonly PMTILES_BIN="${HOME}/.local/bin/pmtiles"

# Mensajes, como_root, esperar_listo, cargar_env, ROOT_DIR y UV_BIN.
# shellcheck source=scripts/dev/comun.sh
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh"

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

instalar_herramientas_geodatos() {
  paso "Instalando herramientas de geodatos (GDAL, tippecanoe, pmtiles)"
  export DEBIAN_FRONTEND=noninteractive
  # GDAL (ogr2ogr) reproyecta y carga los shapefiles de INEGI a PostGIS;
  # tippecanoe genera los PMTiles. Ambos vienen en los repositorios de Ubuntu.
  como_root apt-get install -y -qq gdal-bin tippecanoe >/dev/null
  ok "$(ogr2ogr --version)"
  ok "tippecanoe $(dpkg-query -W -f='${Version}' tippecanoe)"

  if [[ -x "${PMTILES_BIN}" ]] && "${PMTILES_BIN}" version 2>/dev/null | grep -q "${PMTILES_VERSION}"; then
    ok "pmtiles ${PMTILES_VERSION} ya instalado"
    return
  fi
  local tmp
  tmp="$(mktemp -d)"
  curl -fsSL -o "${tmp}/pmtiles.tar.gz"     "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_Linux_x86_64.tar.gz"
  # Si el archivo no coincide con el hash publicado, no se instala.
  echo "${PMTILES_SHA256}  ${tmp}/pmtiles.tar.gz" | sha256sum --check --status     || fallo "El SHA-256 del binario de pmtiles no coincide con el publicado."
  tar -xzf "${tmp}/pmtiles.tar.gz" -C "${tmp}" pmtiles
  install -D -m 0755 "${tmp}/pmtiles" "${PMTILES_BIN}"
  rm -rf "${tmp}"
  ok "pmtiles $("${PMTILES_BIN}" version 2>&1 | head -1) (SHA-256 verificado)"
}

instalar_librerias_reportes() {
  paso "Instalando las librerías del sistema para los reportes PDF (WeasyPrint)"
  export DEBIAN_FRONTEND=noninteractive
  # WeasyPrint 70 dibuja el texto con Pango (>= 1.44) y HarfBuzz; su
  # documentación pide estos paquetes en Ubuntu (ADR-0018).
  como_root apt-get install -y -qq libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b >/dev/null
  ok "pango $(dpkg-query -W -f='${Version}' libpango-1.0-0)"
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

instalar_dependencias_python() {
  paso "Instalando dependencias de Python (versiones exactas de backend/uv.lock)"
  (cd "${ROOT_DIR}/backend" && "${UV_BIN}" sync --frozen --python "${PYTHON_VERSION}" --quiet)
  ok "Entorno virtual en ${UV_PROJECT_ENVIRONMENT}"
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
  ok "$(ogr2ogr --version)"
  ok "tippecanoe $(tippecanoe --version 2>&1 | head -1)"
  ok "pmtiles $("${PMTILES_BIN}" version 2>&1 | head -1)"
}

main() {
  verificar_sistema
  cargar_env
  ok ".env cargado"
  instalar_paquetes_base
  configurar_repositorio_postgres
  instalar_servicios
  instalar_herramientas_geodatos
  instalar_librerias_reportes
  instalar_uv_y_python
  instalar_dependencias_python
  arrancar_postgres
  crear_usuario_y_bases
  arrancar_redis
  resumen
}

main "$@"
