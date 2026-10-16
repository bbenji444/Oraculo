# Comandos del proyecto monitor-noticias (CLAUDE.md §9).
#
# Se ejecutan en Ubuntu (WSL). Desde PowerShell, en la carpeta del proyecto:
#   wsl make <comando>
# Sin argumentos muestra la ayuda. Por qué WSL y sin Docker: ADR-0006.
#
# Las tareas del frontend usan el npm de Windows (cmd.exe /c npm ...), porque
# sus dependencias están instaladas para Windows y no funcionan en Linux.

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BACKEND_DIR := $(ROOT_DIR)/backend
FRONTEND_DIR := $(ROOT_DIR)/frontend

UV := $(HOME)/.local/bin/uv
# Entorno virtual en el disco de Linux, no en /mnt/d (más rápido; ADR-0006).
export UV_PROJECT_ENVIRONMENT := $(HOME)/.venvs/monitor-noticias
UV_RUN := cd $(BACKEND_DIR) && $(UV) run --frozen
NPM := cd $(FRONTEND_DIR) && cmd.exe /c npm

# Cobertura mínima de domain/ y application/ (CLAUDE.md §7).
COVERAGE_MIN := 85

.PHONY: help bootstrap up down status logs migrate \
        test test-backend test-frontend lint lint-backend lint-frontend \
        format frontend-build geo-download geo-inspect geo-load geo-validate geo-tiles \
        geo-terms geo-basemap db-shell db-dump seed probar-proveedor

help: ## Muestra esta ayuda
	@echo "Uso (desde PowerShell, en la carpeta del proyecto): wsl make <comando>"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

bootstrap: ## Instala todo: servicios en Ubuntu y dependencias de backend y frontend
	bash scripts/dev/instalar_wsl.sh
	@echo
	@echo "==> Instalando dependencias del frontend con el npm de Windows"
	$(NPM) ci --no-fund --no-audit

up: ## Levanta PostgreSQL, Redis, API, worker y nginx (http://localhost:8080)
	bash scripts/dev/servicios.sh up

down: ## Detiene todos los servicios
	bash scripts/dev/servicios.sh down

status: ## Muestra qué servicios corren y el resultado de /health
	bash scripts/dev/servicios.sh status

logs: ## Sigue los logs de la API y del worker (Ctrl+C para salir)
	bash scripts/dev/servicios.sh logs

migrate: ## Aplica las migraciones de Alembic a la base de desarrollo
	$(UV_RUN) alembic upgrade head

test: test-backend test-frontend ## Pruebas de backend y frontend

test-backend: ## Pruebas del backend (unitarias + integración) con cobertura
	$(UV_RUN) pytest --cov=app.domain --cov=app.application --cov-fail-under=$(COVERAGE_MIN)

test-frontend: ## Pruebas del frontend (Vitest)
	$(NPM) run test

lint: lint-backend lint-frontend ## ruff + mypy + eslint + prettier + tipos de TypeScript

lint-backend: ## ruff (lint y formato) y mypy (estricto en domain/ y application/)
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .
	$(UV_RUN) mypy
	$(UV_RUN) mypy --strict app/domain app/application

lint-frontend: ## ESLint, Prettier y verificación de tipos de TypeScript
	$(NPM) run lint
	$(NPM) run typecheck

format: ## Aplica el formato de ruff y Prettier
	$(UV_RUN) ruff format .
	$(UV_RUN) ruff check --fix .
	$(NPM) run format

frontend-build: ## Compila el frontend en frontend/dist (lo sirve nginx)
	$(NPM) run build

# --- Geodatos (especificación §12, ADR-0008) ------------------------------------

geo-download: ## Descarga INEGI y Natural Earth a geodata/raw (con manifiesto)
	$(UV_RUN) python -m app.geodata.descargar

geo-inspect: ## Revisa proyección, encoding y conteos; muestra 5 nombres reales con Ñ
	$(UV_RUN) python -m app.geodata.inspeccionar

geo-load: ## Carga a PostGIS lo inspeccionado, valida y genera PMTiles (requiere geo-inspect)
	$(UV_RUN) python -m app.geodata.cargar
	$(UV_RUN) python -m app.geodata.validar
	$(UV_RUN) python -m app.geodata.generar_pmtiles

geo-validate: ## Criterios de aceptación del catálogo geográfico (§12)
	$(UV_RUN) python -m app.geodata.validar

geo-tiles: ## Genera los PMTiles de países, estados, municipios y localidades
	$(UV_RUN) python -m app.geodata.generar_pmtiles

geo-terms: ## Aplica términos de búsqueda y códigos de país sin recargar el catálogo (ADR-0009)
	$(UV_RUN) python -m app.geodata.aplicar_terminos $(ARGS)

geo-basemap: ## Descarga el mapa base de Protomaps (mundo z6 + México z14, ~1.35 GB)
	$(UV_RUN) python -m app.geodata.mapa_base

# --- Base de datos (docs/base-de-datos.md) ---------------------------------------

probar-proveedor: ## UNA consulta real a un proveedor, con confirmación (ARGS="--proveedor gdelt --nombre x")
	$(UV_RUN) python -m app.cli.probar_proveedor $(ARGS)

seed: ## Carga los conceptos semilla que falten (nunca modifica los existentes)
	$(UV_RUN) python -m app.seed.cargar_conceptos

db-shell: ## Abre una consola SQL (psql) en la base de desarrollo
	bash scripts/dev/base_datos.sh shell

db-dump: ## Respalda la base de desarrollo en backups/ (para migrarla a otro servidor)
	bash scripts/dev/base_datos.sh dump
