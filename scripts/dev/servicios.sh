#!/usr/bin/env bash
# Arranca, detiene y muestra el estado de los servicios de desarrollo en WSL:
# PostgreSQL, Redis, la API (uvicorn), el worker y el reloj de Celery, nginx
# y, si está instalado, el módulo aparte God's Eye View (scripts/dev/gods_eye.sh).
#
# Quién lo usa: `make up`, `make down`, `make status` y `make logs`.
# Uso directo: bash scripts/dev/servicios.sh {up|down|status|logs}
#
# Sin systemd (ADR-0006), PostgreSQL, Redis y nginx se manejan con `service`,
# y la API, el worker y el reloj con archivos de PID (y sus logs) en RUN_DIR.
#
# Qué NO hace: no instala nada (eso es `make bootstrap`) ni aplica
# migraciones (eso es `make migrate`).

set -euo pipefail

# shellcheck source=scripts/dev/comun.sh
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh"

# PIDs y logs van en el disco de Linux y no en /mnt/d: leer un archivo de
# /mnt/d justo después de escribirlo llegó a devolver basura binaria (medido
# con el kernel 5.10 de WSL), y entonces un proceso vivo parecía detenido.
readonly RUN_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/monitor-noticias"
readonly BACKEND_DIR="${ROOT_DIR}/backend"
readonly NGINX_SITE="/etc/nginx/sites-available/monitor-noticias"
readonly NGINX_SITE_LINK="/etc/nginx/sites-enabled/monitor-noticias"
readonly NGINX_DEFAULT_LINK="/etc/nginx/sites-enabled/default"

# Puertos de desarrollo. La API escucha solo en localhost; nginx la expone en
# 8080 junto con el frontend (nginx/monitor-noticias.conf.template).
readonly API_PORT=8000
readonly NGINX_PORT=8080
# Procesos del worker: dos bastan en desarrollo; en F4 se ajusta según el
# límite de concurrencia por proveedor.
readonly WORKER_CONCURRENCY=2
# La API y el worker tardan más en arrancar cuando Ubuntu acaba de encender
# (Python lee sus librerías por primera vez): 15 s no alcanzaron tras un
# `wsl --shutdown`. Se les da más margen que a los servicios del sistema.
readonly APP_READY_TIMEOUT_SECONDS=90
# Segundos que se espera a que un proceso termine con SIGTERM antes de forzarlo.
readonly STOP_GRACE_SECONDS=10
# God's Eye View (módulo aparte, scripts/dev/gods_eye.sh): su servidor de Vite
# usa el puerto 4173, el de su README. Solo escucha en localhost; la pestaña
# «God's Eye» del monitor lo muestra en un iframe.
readonly GEV_DIR="${GEV_DIR:-${HOME}/gods-eye-view}"
readonly GEV_NODE_BIN="${HOME}/.local/node24/bin"
readonly GEV_PORT=4173

# --- Procesos propios (API, worker y reloj) ------------------------------------

pid_vivo() {
  local pid_file="$1"
  [[ -f "${pid_file}" ]] && kill -0 "$(cat "${pid_file}")" 2>/dev/null
}

arrancar_proceso() {
  local nombre="$1"; shift
  local pid_file="${RUN_DIR}/${nombre}.pid"
  local log_file="${RUN_DIR}/${nombre}.log"
  if pid_vivo "${pid_file}"; then
    ok "${nombre} ya estaba corriendo (PID $(cat "${pid_file}"))"
    return
  fi
  rm -f "${pid_file}"
  # setsid crea una sesión nueva: el proceso sigue vivo aunque se cierre la
  # terminal y queda como líder de su grupo, para detenerlo junto con sus
  # hijos. No se usa $! porque setsid puede hacer fork y $! apuntaría a un
  # proceso intermedio que termina de inmediato (pasó: PID guardado 10869,
  # real 10871). Por eso el propio proceso escribe su PID ($$) y luego se
  # reemplaza (exec) por el comando real, conservando ese PID.
  # Las redirecciones van sobre todo el subproceso y este se reemplaza con
  # exec: si quedara un bash intermedio con la salida original abierta,
  # `make up | ...` nunca terminaría (pasó al guardar la salida en un tubo).
  (
    cd "${BACKEND_DIR}" || exit 1
    exec setsid bash -c 'echo $$ > "$0"; exec "$@"' "${pid_file}" "$@"
  ) >"${log_file}" 2>&1 </dev/null &
  esperar_listo "El PID de ${nombre}" test -s "${pid_file}"
  ok "${nombre} arrancado (PID $(cat "${pid_file}"), log en ${log_file})"
}

detener_proceso() {
  local nombre="$1"
  local pid_file="${RUN_DIR}/${nombre}.pid"
  if ! pid_vivo "${pid_file}"; then
    rm -f "${pid_file}"
    ok "${nombre} no estaba corriendo"
    return
  fi
  local pid
  pid="$(cat "${pid_file}")"
  # El PID es líder de su propio grupo (setsid): se detiene el grupo completo
  # para incluir los procesos hijos (recargador de uvicorn, hijos de Celery).
  kill -TERM -- "-${pid}" 2>/dev/null || true
  local i
  for ((i = 0; i < STOP_GRACE_SECONDS * 2; i++)); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "${pid}" 2>/dev/null; then
    kill -KILL -- "-${pid}" 2>/dev/null || true
    aviso "${nombre} no terminó a tiempo; se forzó el cierre"
  fi
  rm -f "${pid_file}"
  ok "${nombre} detenido"
}

# --- nginx ---------------------------------------------------------------------

instalar_sitio_nginx() {
  # Se regenera en cada arranque para que los cambios a la plantilla apliquen.
  sed "s|__PROJECT_ROOT__|${ROOT_DIR}|g" "${ROOT_DIR}/nginx/monitor-noticias.conf.template" \
    | como_root tee "${NGINX_SITE}" >/dev/null
  como_root ln -sf "${NGINX_SITE}" "${NGINX_SITE_LINK}"
  # El sitio de ejemplo de nginx ocupa el puerto 80, que no usamos.
  como_root rm -f "${NGINX_DEFAULT_LINK}"
  como_root nginx -t -q || fallo "La configuración de nginx tiene errores (ver arriba)."
}

# --- Comandos ------------------------------------------------------------------

cmd_up() {
  cargar_env
  mkdir -p "${RUN_DIR}"
  [[ -x "${UV_BIN}" ]] || fallo "No se encontró uv. Ejecuta primero: wsl make bootstrap"

  paso "Base de datos y Redis"
  como_root service postgresql start >/dev/null
  esperar_listo "PostgreSQL" pg_isready -q -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}"
  ok "PostgreSQL listo"
  como_root service redis-server start >/dev/null
  esperar_listo "Redis" redis-cli ping
  ok "Redis listo"

  paso "API, worker y reloj de Celery"
  # --reload reinicia la API al guardar código. En /mnt/d no llegan avisos de
  # cambios de archivos desde Windows, así que watchfiles revisa por sondeo.
  arrancar_proceso api env WATCHFILES_FORCE_POLLING=true \
    "${UV_BIN}" run --frozen uvicorn app.main:app \
    --host 127.0.0.1 --port "${API_PORT}" --reload --reload-dir app --no-access-log
  arrancar_proceso worker "${UV_BIN}" run --frozen celery -A app.worker.celery_app worker \
    --loglevel=INFO --concurrency="${WORKER_CONCURRENCY}" --hostname="worker@%h"
  LIMITE_ESPERA="${APP_READY_TIMEOUT_SECONDS}" esperar_listo "La API" curl -fsS -o /dev/null "http://127.0.0.1:${API_PORT}/api/v1/openapi.json"
  ok "API respondiendo en el puerto ${API_PORT}"
  # Celery escribe "ready" un poco antes de contestar pings; se espera a que
  # /health ya lo vea para no reportar un falso error recién arrancado.
  LIMITE_ESPERA="${APP_READY_TIMEOUT_SECONDS}" esperar_listo "El worker" bash -c \
    "curl -s http://127.0.0.1:${API_PORT}/api/v1/health | grep -q '\"workers\"'"
  ok "Worker respondiendo"
  # El reloj (celery beat) encola la ingesta al índice local cada
  # INGEST_INTERVAL_MINUTES y la limpieza diaria (ADR-0013). Guarda cuándo
  # corrió cada tarea en RUN_DIR, no en el repositorio.
  arrancar_proceso beat "${UV_BIN}" run --frozen celery -A app.worker.celery_app beat \
    --loglevel=INFO --schedule="${RUN_DIR}/celerybeat-schedule"

  paso "God's Eye View (módulo aparte, sin integrar)"
  if [[ -d "${GEV_DIR}/node_modules" && -x "${GEV_NODE_BIN}/node" ]]; then
    arrancar_proceso godseye env PATH="${GEV_NODE_BIN}:/usr/local/bin:/usr/bin:/bin"       bash -c 'cd "$0" && exec npm run dev -- --host 127.0.0.1 --port "$1" --strictPort'       "${GEV_DIR}" "${GEV_PORT}"
    # La primera vez Vite prepara Cesium y tarda más.
    LIMITE_ESPERA="${APP_READY_TIMEOUT_SECONDS}" esperar_listo "God's Eye View"       curl -fsS -o /dev/null "http://127.0.0.1:${GEV_PORT}/"
    ok "God's Eye View en http://localhost:${GEV_PORT}"
  else
    aviso "God's Eye View no está instalado (wsl make gev-instalar): se omite."
  fi

  paso "nginx"
  if [[ ! -f "${ROOT_DIR}/frontend/dist/index.html" ]]; then
    aviso "No existe frontend/dist: se compila el frontend con el npm de Windows."
    (cd "${ROOT_DIR}/frontend" && cmd.exe /c "npm run build" >/dev/null) \
      || fallo "No se pudo compilar el frontend. ¿Corriste 'npm install' en frontend/?"
  fi
  instalar_sitio_nginx
  if como_root service nginx status >/dev/null 2>&1; then
    como_root service nginx reload >/dev/null
  else
    como_root service nginx start >/dev/null
  fi
  esperar_listo "nginx" curl -fsS -o /dev/null "http://127.0.0.1:${NGINX_PORT}/"
  ok "nginx sirviendo en http://localhost:${NGINX_PORT}"

  cmd_status
}

cmd_down() {
  paso "Deteniendo servicios"
  detener_proceso godseye
  detener_proceso beat
  detener_proceso worker
  detener_proceso api
  como_root service nginx stop >/dev/null 2>&1 || true
  ok "nginx detenido"
  como_root service redis-server stop >/dev/null 2>&1 || true
  ok "Redis detenido"
  como_root service postgresql stop >/dev/null 2>&1 || true
  ok "PostgreSQL detenido"
}

linea_estado() {
  local nombre="$1" vivo="$2" extra="$3"
  if [[ "${vivo}" == "si" ]]; then ok "${nombre}: corriendo ${extra}"; else aviso "${nombre}: detenido"; fi
}

cmd_status() {
  cargar_env
  mkdir -p "${RUN_DIR}"
  paso "Estado de los servicios"
  linea_estado "PostgreSQL" "$(pg_isready -q -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" && echo si || echo no)" "(puerto ${POSTGRES_PORT})"
  linea_estado "Redis" "$(redis-cli ping >/dev/null 2>&1 && echo si || echo no)" "(puerto 6379)"
  linea_estado "API" "$(pid_vivo "${RUN_DIR}/api.pid" && echo si || echo no)" "(PID $(cat "${RUN_DIR}/api.pid" 2>/dev/null || echo -), puerto ${API_PORT})"
  linea_estado "Worker" "$(pid_vivo "${RUN_DIR}/worker.pid" && echo si || echo no)" "(PID $(cat "${RUN_DIR}/worker.pid" 2>/dev/null || echo -))"
  linea_estado "Reloj (beat)" "$(pid_vivo "${RUN_DIR}/beat.pid" && echo si || echo no)" "(PID $(cat "${RUN_DIR}/beat.pid" 2>/dev/null || echo -), ingesta cada ${INGEST_INTERVAL_MINUTES:-15} min)"
  linea_estado "nginx" "$(como_root service nginx status >/dev/null 2>&1 && echo si || echo no)" "(puerto ${NGINX_PORT})"
  linea_estado "God's Eye View" "$(pid_vivo "${RUN_DIR}/godseye.pid" && echo si || echo no)" "(PID $(cat "${RUN_DIR}/godseye.pid" 2>/dev/null || echo -), puerto ${GEV_PORT})"

  paso "Puertos escuchando"
  ss -ltnH "( sport = :5432 or sport = :6379 or sport = :${API_PORT} or sport = :${NGINX_PORT} or sport = :${GEV_PORT} )" \
    | awk '{print "    " $4}' | sort -u

  paso "GET /api/v1/health (a través de nginx)"
  local codigo
  # Se borra la respuesta anterior: si esta petición falla, no debe mostrarse
  # un estado viejo como si fuera el actual.
  rm -f "${RUN_DIR}/health.json"
  codigo="$(curl -s -o "${RUN_DIR}/health.json" -w '%{http_code}' "http://127.0.0.1:${NGINX_PORT}/api/v1/health" || true)"
  echo "    HTTP ${codigo}"
  if [[ -s "${RUN_DIR}/health.json" ]]; then
    "${UV_BIN}" run --frozen --project "${BACKEND_DIR}" python -m json.tool --no-ensure-ascii \
      "${RUN_DIR}/health.json" | sed 's/^/    /'
  fi
}

cmd_logs() {
  mkdir -p "${RUN_DIR}"
  tail -n 30 -F "${RUN_DIR}"/api.log "${RUN_DIR}"/worker.log "${RUN_DIR}"/beat.log
}

case "${1:-}" in
  up) cmd_up ;;
  down) cmd_down ;;
  status) cmd_status ;;
  logs) cmd_logs ;;
  *) echo "Uso: $0 {up|down|status|logs}" >&2; exit 2 ;;
esac
