#!/usr/bin/env bash
# Instala y habilita el servicio de systemd que levanta el monitor al encender
# el servidor (docs/migracion-proxmox.md, paso 6).
#
# Quién lo usa: `make instalar-servicio`, una sola vez en la VM.
# Qué NO hace: no sirve en WSL (no tiene systemd) ni arranca nada por sí solo:
# el servicio corre al siguiente encendido, o con
#   sudo systemctl start monitor-noticias

set -euo pipefail

# shellcheck source=scripts/dev/comun.sh
source "$(dirname "${BASH_SOURCE[0]}")/../dev/comun.sh"

readonly UNIT_PATH="/etc/systemd/system/monitor-noticias.service"

[[ -d /run/systemd/system ]] || fallo "Este sistema no usa systemd (¿es WSL?): no hace falta el servicio."
[[ ${EUID} -ne 0 ]] || fallo "Córrelo con el usuario del monitor, no como root."

paso "Instalando el servicio monitor-noticias"
sed -e "s|__PROJECT_ROOT__|${ROOT_DIR}|g" -e "s|__USER__|$(id -un)|g" \
  "${ROOT_DIR}/scripts/servidor/monitor-noticias.service.template" \
  | como_root tee "${UNIT_PATH}" >/dev/null
como_root systemctl daemon-reload
como_root systemctl enable monitor-noticias.service >/dev/null 2>&1
ok "Instalado en ${UNIT_PATH} y habilitado al encender"
ok "Para arrancarlo ya: sudo systemctl start monitor-noticias"
