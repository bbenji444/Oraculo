#!/usr/bin/env bash
# Utilidades compartidas por los scripts de desarrollo en WSL y del servidor
# (la VM de Proxmox, docs/migracion-proxmox.md): mensajes, ejecución como root
# o como postgres, espera de servicios, el npm que toca y carga de .env.
#
# Quién lo usa: instalar_wsl.sh y servicios.sh, con
#   source "$(dirname "${BASH_SOURCE[0]}")/comun.sh"
#
# Qué NO hace: no ejecuta nada por sí solo; solo define funciones y
# constantes.

# `service ... start` regresa antes de que el servicio acepte conexiones
# (medido: Redis tardó ~0.3 s). Se espera hasta este límite antes de fallar.
readonly READY_TIMEOUT_SECONDS=15

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly ROOT_DIR
readonly UV_BIN="${HOME}/.local/bin/uv"
# El entorno virtual vive en el disco de Linux y no en /mnt/d: leer miles de
# archivos pequeños a través de /mnt/d es lento (ADR-0006).
export UV_PROJECT_ENVIRONMENT="${HOME}/.venvs/monitor-noticias"

# En WSL el frontend usa el npm de Windows (sus dependencias se instalaron
# para Windows); en un Linux sin Windows, como la VM, el npm de Linux.
npm_cmd() {
  if command -v cmd.exe >/dev/null 2>&1; then cmd.exe /c npm "$@"; else npm "$@"; fi
}

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
# El límite se puede ampliar para un caso puntual con
#   LIMITE_ESPERA=<segundos> esperar_listo ...
esperar_listo() {
  local descripcion="$1"; shift
  local limite="${LIMITE_ESPERA:-${READY_TIMEOUT_SECONDS}}"
  local intentos=$((limite * 2))
  local i
  for ((i = 0; i < intentos; i++)); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  fallo "${descripcion} no estuvo listo en ${limite} s."
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
}
