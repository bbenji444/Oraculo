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
        geo-terms geo-basemap geo-places db-shell db-dump seed probar-proveedor gdelt-diagnostico ingesta \
        ingesta-historial ngramas-muestra buscar reubicar geo-earth extraer-entidades reparar-texto \
        limpiar-duplicados agrupar-historias comparar-fuentes clasificar

help: ## Muestra esta ayuda
	@echo "Uso (desde PowerShell, en la carpeta del proyecto): wsl make <comando>"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

bootstrap: ## Instala todo: servicios en Ubuntu y dependencias de backend y frontend
	bash scripts/dev/instalar_wsl.sh
	@echo
	@echo "==> Instalando dependencias del frontend con el npm de Windows"
	$(NPM) ci --no-fund --no-audit

up: ## Levanta PostgreSQL, Redis, API, worker, reloj de Celery y nginx (http://localhost:8080)
	bash scripts/dev/servicios.sh up

down: ## Detiene todos los servicios
	bash scripts/dev/servicios.sh down

status: ## Muestra qué servicios corren y el resultado de /health
	bash scripts/dev/servicios.sh status

logs: ## Sigue los logs de la API, del worker y del reloj (Ctrl+C para salir)
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

geo-terms: ## Aplica términos de búsqueda, alias y códigos de país sin recargar el catálogo (ADR-0009)
	$(UV_RUN) python -m app.geodata.aplicar_terminos $(ARGS)

geo-basemap: ## Descarga el mapa base de Protomaps (mundo z6 + México z14, ~1.35 GB)
	$(UV_RUN) python -m app.geodata.mapa_base

geo-earth: ## Texturas NASA de la Tierra (día y noche) y estrellas (ARGS=--muestra para solo 5 recortes)
	$(UV_RUN) python -m app.geodata.tierra $(ARGS)

geo-places: ## Colonias y barrios de OpenStreetMap desde el mapa base (ARGS=--muestra: solo ejemplos)
	$(UV_RUN) python -m app.geodata.lugares_osm $(ARGS)

# --- Base de datos (docs/base-de-datos.md) ---------------------------------------

gdelt-diagnostico: ## Reintento diario de D1 en GDELT (máximo una vez al día, ADR-0012)
	$(UV_RUN) python -m app.cli.diagnostico_gdelt

probar-proveedor: ## UNA consulta real a un proveedor, con confirmación (ARGS="--proveedor gdelt --nombre x")
	$(UV_RUN) python -m app.cli.probar_proveedor $(ARGS)

buscar: ## Búsqueda real de punta a punta, con costo y confirmación (ARGS="--concepto Extorsión --region 14")
	$(UV_RUN) python -m app.cli.buscar $(ARGS)

reubicar: ## Vuelve a ubicar las notas de una búsqueda sin pagar a la IA (ARGS="--busqueda <id>")
	$(UV_RUN) python -m app.cli.reubicar $(ARGS)

reparar-texto: ## Repara el Mojibake de las notas guardadas: sin ARGS solo muestra 5 ejemplos; ARGS=--aplicar guarda (pide "si")
	$(UV_RUN) python -m app.cli.reparar_texto $(ARGS)

limpiar-duplicados: ## Quita notas repetidas del índice local: sin ARGS solo muestra 5 ejemplos; ARGS=--aplicar borra (pide "si"; antes make db-dump)
	$(UV_RUN) python -m app.cli.limpiar_duplicados $(ARGS)

agrupar-historias: ## Junta en historias las notas guardadas: sin ARGS solo muestra 5 historias; ARGS=--aplicar guarda (pide "si")
	$(UV_RUN) python -m app.cli.agrupar_historias $(ARGS)

comparar-fuentes: ## Mide cuánto aporta SearchApi sobre Google News RSS: muestra costo y pide "si" (ARGS="--concepto X --dias 2")
	$(UV_RUN) python -m app.cli.comparar_fuentes $(ARGS)

clasificar: ## Clasifica por categoría las notas guardadas: sin ARGS 5 de ejemplo sin guardar; ARGS=--aplicar todas (pide "si")
	$(UV_RUN) python -m app.cli.clasificar $(ARGS)

extraer-entidades: ## La IA lee notas de un caso y muestra las entidades que propone; pide "si" (ARGS="--caso <id> --muestra 5")
	$(UV_RUN) python -m app.cli.extraer_entidades $(ARGS)

ingesta: ## Corre la ingesta al índice local una vez y muestra 5 ejemplos (ADR-0013)
	$(UV_RUN) python -m app.cli.ingesta

ingesta-historial: ## Historial de GDELT: vista previa con DIAS=N; baja todo solo con DESCARGAR=si
	$(UV_RUN) python -m app.cli.ingesta_historial --dias $(or $(DIAS),1) $(if $(filter si,$(DESCARGAR)),--descargar,)

ngramas-muestra: ## Prueba real de los ngramas de GDELT: consumo, espacio y 5 ejemplos (MINUTOS=60)
	$(UV_RUN) python -m app.cli.muestra_ngramas --minutos $(or $(MINUTOS),60)

seed: ## Carga los conceptos semilla que falten (nunca modifica los existentes)
	$(UV_RUN) python -m app.seed.cargar_conceptos

db-shell: ## Abre una consola SQL (psql) en la base de desarrollo
	bash scripts/dev/base_datos.sh shell

db-dump: ## Respalda la base de desarrollo en backups/ (para migrarla a otro servidor)
	bash scripts/dev/base_datos.sh dump
