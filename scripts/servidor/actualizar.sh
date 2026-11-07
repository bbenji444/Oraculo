#!/usr/bin/env bash
# Actualiza el monitor en el servidor con lo último de GitHub (rama develop).
#
# Quién lo usa: el temporizador de systemd monitor-noticias-actualizar, cada
# 5 minutos (lo instala `make instalar-servicio`). También se puede correr a
# mano: bash scripts/servidor/actualizar.sh
#
# Qué hace, solo si hay commits nuevos:
#   1. espera si hay una corrida o búsqueda en marcha (no la corta);
#   2. baja el código (git merge --ff-only, nunca reescribe nada);
#   3. instala dependencias si cambiaron (uv.lock, package-lock.json);
#   4. compila la pantalla en una carpeta aparte y la cambia de golpe, para
#      que nunca quede sin página;
#   5. aplica migraciones y reinicia el monitor;
#   6. revisa /health. Si falla, regresa al código anterior y reinicia.
#
# Qué NO hace: no instala programas del sistema (eso pide contraseña:
# make bootstrap) ni deshace migraciones al regresar.

set -euo pipefail

# shellcheck source=scripts/dev/comun.sh
source "$(dirname "${BASH_SOURCE[0]}")/../dev/comun.sh"

# Rama que se publica en el servidor (decisión de Benji, 07/11/2026: lo que
# entra a develop se ve en la VM). Se puede cambiar con DEPLOY_BRANCH en .env.
readonly DEFAULT_BRANCH="develop"
readonly STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/monitor-noticias"
readonly LOCK_FILE="${STATE_DIR}/actualizar.lock"
readonly HEALTH_URL="http://127.0.0.1:8000/api/v1/health"
# Tras reiniciar, la API y el worker tardan en cargar (servicios.sh espera
# hasta 90 s a cada uno); se da margen para el arranque completo.
readonly HEALTH_TIMEOUT_SECONDS=180

marca() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

corrida_en_marcha() {
  # Una búsqueda en cola o corriendo (manual o automática) se cortaría al
  # reiniciar el worker: se deja para la siguiente revisión.
  local n
  n="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -X -qtA -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "SELECT count(*) FROM searches WHERE status IN ('queued', 'running')" 2>/dev/null || echo 0)"
  [[ "${n}" != "0" ]]
}

monitor_sano() {
  local i
  for ((i = 0; i < HEALTH_TIMEOUT_SECONDS / 5; i++)); do
    if curl -fsS --max-time 10 "${HEALTH_URL}" 2>/dev/null | grep -q '"status": *"ok"'; then
      return 0
    fi
    sleep 5
  done
  return 1
}

compilar_frontend() {
  # Se compila en dist.nuevo y luego se cambia por dist: nginx nunca ve la
  # carpeta a medias.
  (cd "${ROOT_DIR}/frontend" && npm run build -- --outDir dist.nuevo --emptyOutDir >/dev/null)
  rm -rf "${ROOT_DIR}/frontend/dist.viejo"
  [[ -d "${ROOT_DIR}/frontend/dist" ]] && mv "${ROOT_DIR}/frontend/dist" "${ROOT_DIR}/frontend/dist.viejo"
  mv "${ROOT_DIR}/frontend/dist.nuevo" "${ROOT_DIR}/frontend/dist"
}

main() {
  mkdir -p "${STATE_DIR}"
  exec 9>"${LOCK_FILE}"
  flock -n 9 || exit 0   # otra actualización sigue en curso
  cargar_env >/dev/null
  local branch="${DEPLOY_BRANCH:-${DEFAULT_BRANCH}}"
  cd "${ROOT_DIR}"

  git fetch -q origin "${branch}"
  local viejo nuevo
  viejo="$(git rev-parse HEAD)"
  nuevo="$(git rev-parse "origin/${branch}")"
  [[ "${viejo}" != "${nuevo}" ]] || exit 0

  if corrida_en_marcha; then
    marca "Hay commits nuevos, pero una búsqueda está en marcha: se actualiza en la siguiente revisión."
    exit 0
  fi

  marca "Actualizando ${viejo:0:7} → ${nuevo:0:7} ($(git log -1 --format=%s "${nuevo}"))"
  git merge -q --ff-only "origin/${branch}"
  local cambios
  cambios="$(git diff --name-only "${viejo}" "${nuevo}")"

  if grep -q '^backend/uv.lock$' <<<"${cambios}"; then
    marca "Dependencias de Python nuevas"
    (cd backend && "${UV_BIN}" sync --frozen --quiet)
  fi
  if grep -q '^frontend/package-lock.json$' <<<"${cambios}"; then
    marca "Dependencias del frontend nuevas"
    (cd frontend && npm ci --no-fund --no-audit --silent)
  fi
  if grep -q '^frontend/' <<<"${cambios}"; then
    marca "Compilando la pantalla"
    compilar_frontend
  fi
  (cd backend && "${UV_BIN}" run --frozen alembic upgrade head >/dev/null)
  sudo -n /usr/bin/systemctl restart monitor-noticias

  if monitor_sano; then
    marca "Listo: el monitor corre ${nuevo:0:7}."
    return
  fi

  marca "ERROR: /health no respondió tras actualizar. Se regresa a ${viejo:0:7}."
  git reset -q --hard "${viejo}"
  if grep -q '^frontend/' <<<"${cambios}" && [[ -d frontend/dist.viejo ]]; then
    rm -rf frontend/dist && mv frontend/dist.viejo frontend/dist
  fi
  sudo -n /usr/bin/systemctl restart monitor-noticias
  monitor_sano && marca "Regresó a ${viejo:0:7} y responde." || marca "ERROR: tampoco responde ${viejo:0:7}; revisar a mano."
  exit 1
}

main "$@"
