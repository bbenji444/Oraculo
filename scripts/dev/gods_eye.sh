#!/usr/bin/env bash
# God's Eye View: módulo aparte, copiado tal cual de GitHub (27/10/2026).
#
# Benji pidió verlo «tal cual como aparece en el proyecto de GitHub» desde una
# pestaña del monitor, para analizarlo antes de decidir cómo integrarlo. Por
# eso no se copia dentro de este repositorio ni se mezcla con su código: vive
# en GEV_DIR (disco de Linux de WSL, donde npm es rápido) con su propio Node.
#
# - Proyecto: https://github.com/bilawalsidhu/gods-eye-view (código MIT,
#   Bilawal Sidhu). Algunos datos incluidos NO son MIT (cables submarinos de
#   TeleGeography e imágenes de Vantor: no comerciales). Ver su LICENSE.
# - Se fija un commit para que la instalación sea repetible.
# - Pide Node 24.14 o mayor (su package.json); Windows tiene Node 22, así que
#   se instala Node 24 oficial de nodejs.org en NODE_DIR, verificado con
#   SHA-256, sin tocar el sistema.
#
# Uso: bash scripts/dev/gods_eye.sh {instalar|probar}
#   (o `make gev-instalar` y `make gev-probar`). Lo arranca `make up`.
#
# Qué NO hace: no pone llaves de API (el módulo funciona sin ellas; las
# opcionales se agregan en su panel «Provider Settings») ni lo integra al
# monitor.

set -euo pipefail

# shellcheck source=scripts/dev/comun.sh
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh"

readonly GEV_REPO="https://github.com/bilawalsidhu/gods-eye-view.git"
# Último commit de main al copiarlo (26/10/2026 16:54 PDT).
readonly GEV_COMMIT="15de9d738c4a85be1a96726c6114181caef87eeb"
readonly GEV_DIR="${GEV_DIR:-${HOME}/gods-eye-view}"
# Node 24 LTS más reciente al 27/10/2026 (publicado el 20/10/2026).
readonly NODE_VERSION="v24.22.1"
readonly NODE_DIR="${HOME}/.local/node24"

node_path() { printf '%s/bin:/usr/local/bin:/usr/bin:/bin' "${NODE_DIR}"; }

instalar_node() {
  if [[ -x "${NODE_DIR}/bin/node" ]] && [[ "$("${NODE_DIR}/bin/node" -v)" == "${NODE_VERSION}" ]]; then
    ok "Node ${NODE_VERSION} ya está en ${NODE_DIR}"
    return
  fi
  local tmp archivo="node-${NODE_VERSION}-linux-x64.tar.xz"
  tmp="$(mktemp -d)"
  curl -sSfL -o "${tmp}/${archivo}" "https://nodejs.org/dist/${NODE_VERSION}/${archivo}"
  curl -sSfL -o "${tmp}/SHASUMS256.txt" "https://nodejs.org/dist/${NODE_VERSION}/SHASUMS256.txt"
  (cd "${tmp}" && grep " ${archivo}\$" SHASUMS256.txt | sha256sum -c - >/dev/null) \
    || fallo "La suma SHA-256 de Node no coincide: no se instala."
  mkdir -p "${NODE_DIR}"
  tar -xJf "${tmp}/${archivo}" -C "${NODE_DIR}" --strip-components=1
  rm -rf "${tmp}"
  ok "Node $("${NODE_DIR}/bin/node" -v) instalado en ${NODE_DIR}"
}

cmd_instalar() {
  paso "Node 24 para God's Eye View"
  instalar_node

  paso "Código de God's Eye View (commit ${GEV_COMMIT:0:7})"
  if [[ ! -d "${GEV_DIR}/.git" ]]; then
    git clone --filter=blob:none --no-checkout "${GEV_REPO}" "${GEV_DIR}"
  fi
  git -C "${GEV_DIR}" fetch --depth 1 origin "${GEV_COMMIT}"
  git -C "${GEV_DIR}" checkout --detach "${GEV_COMMIT}"
  ok "Copia en ${GEV_DIR}"

  paso "Dependencias (npm ci, exactas a su package-lock)"
  # El Chrome de puppeteer (~150 MB) solo lo usan sus pruebas visuales.
  (cd "${GEV_DIR}" && PATH="$(node_path)" PUPPETEER_SKIP_DOWNLOAD=1 npm ci --no-audit --no-fund)
  (cd "${GEV_DIR}" && PATH="$(node_path)" npm run doctor)
}

cmd_probar() {
  [[ -d "${GEV_DIR}/node_modules" ]] || fallo "God's Eye View no está instalado: wsl make gev-instalar"
  paso "Pruebas unitarias de God's Eye View"
  (cd "${GEV_DIR}" && PATH="$(node_path)" npm test)
}

case "${1:-}" in
  instalar) cmd_instalar ;;
  probar) cmd_probar ;;
  *) fallo "Uso: $0 {instalar|probar}" ;;
esac
