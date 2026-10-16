#!/usr/bin/env bash
# Acceso a la base de datos de desarrollo: consola SQL y respaldos.
#
# Quién lo usa: `make db-shell` y `make db-dump`.
# Uso directo: bash scripts/dev/base_datos.sh {shell|dump}
#
# Se conecta con el usuario de la aplicación (el de .env), igual que lo haría
# DBeaver o pgAdmin desde Windows. Ver docs/base-de-datos.md.
#
# Qué NO hace: no restaura respaldos sobre la base de desarrollo (eso borra
# datos y se hace a mano, siguiendo docs/base-de-datos.md).

set -euo pipefail

# shellcheck source=scripts/dev/comun.sh
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh"

readonly BACKUP_DIR="${ROOT_DIR}/backups"

cmd_shell() {
  cargar_env
  # PGPASSWORD por variable de entorno: no aparece en la línea de comandos.
  PGPASSWORD="${POSTGRES_PASSWORD}" exec psql \
    -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
}

cmd_dump() {
  cargar_env
  mkdir -p "${BACKUP_DIR}"
  local stamp file
  stamp="$(date -u +%Y%m%dT%H%MZ)"
  file="${BACKUP_DIR}/${POSTGRES_DB}_${stamp}.dump"
  paso "Respaldando ${POSTGRES_DB} (formato personalizado de pg_dump, comprimido)"
  # Formato -Fc: comprimido y restaurable por partes con pg_restore. Incluye
  # tablas, índices, el esquema de Alembic y los datos geográficos.
  # spatial_ref_sys es la tabla interna de PostGIS: el servidor destino ya la
  # trae al instalar PostGIS, y copiarla daba errores de permisos al
  # restaurar. --no-comments: los únicos comentarios son los de las
  # extensiones, y el usuario de la aplicación no puede recrearlos en el
  # destino. Medido: 4 errores al restaurar sin estas opciones, 0 con ellas.
  PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump -Fc --no-owner --no-comments \
    --exclude-table-data=spatial_ref_sys \
    -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" -f "${file}"
  ok "Archivo: ${file} ($(du -h "${file}" | cut -f1))"
  local tables
  tables="$(pg_restore --list "${file}" | grep -c ' TABLE DATA ' || true)"
  ok "Tablas con datos en el respaldo: ${tables}"
}

case "${1:-}" in
  shell) cmd_shell ;;
  dump) cmd_dump ;;
  *) echo "Uso: $0 {shell|dump}" >&2; exit 2 ;;
esac
