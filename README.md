# Monitor de Noticias Geolocalizadas

Módulo que busca noticias sobre temas definidos por el usuario (**conceptos**, como "Ciberseguridad" o "Secuestro"), decide cuáles son relevantes, las resume, detecta **dónde ocurrió** cada hecho y lo pinta sobre un globo 3D enfocado en México.

- **Qué se construye:** [docs/ESPECIFICACION.md](docs/ESPECIFICACION.md)
- **Cómo se trabaja:** [CLAUDE.md](CLAUDE.md)
- **Decisiones de arquitectura:** [docs/adr/](docs/adr/README.md)
- **Historial de cambios:** [CHANGELOG.md](CHANGELOG.md)

> Estado actual: **Fase 0 (cimientos)**. Funcionan los servicios, el diagnóstico `/health` y una página que muestra el estado del sistema. El globo, la búsqueda y los reportes llegan en las fases siguientes.

---

## Arranque desde cero (Windows + WSL)

El proyecto se desarrolla en Windows, pero sus servicios corren en **Ubuntu dentro de WSL**, sin Docker ([ADR-0006](docs/adr/0006-entorno-desarrollo-sin-docker.md)).
El código vive en Windows; Ubuntu funciona como un "servidor de desarrollo" dentro de tu PC.

### 1. Requisitos (una sola vez)

| Necesitas | Cómo comprobarlo en PowerShell | Si no lo tienes |
|---|---|---|
| WSL2 con **Ubuntu** | `wsl -l -v` muestra `Ubuntu` con versión `2` | `wsl --install -d Ubuntu` (como administrador) |
| **Git** | `git --version` | <https://git-scm.com/download/win> |
| **Node.js 22** (≥ 22.12) | `node --version` | <https://nodejs.org> (versión LTS 22) |
| **Python** para pre-commit | `py --version` | <https://www.python.org/downloads/windows/> |

Todo lo demás (PostgreSQL 16 + PostGIS, Redis, nginx, Python 3.12 y las librerías) lo instala el paso 3.

### 2. Obtener el código

```powershell
cd D:\Proyectos\Oraculo
git clone <url-del-repositorio> monitor-noticias
cd monitor-noticias
```

Todos los comandos siguientes se ejecutan **en esta carpeta**. `wsl make ...` corre el comando dentro de Ubuntu, en la misma carpeta.

### 3. Instalar todo

```powershell
wsl make bootstrap
```

Instala y configura PostgreSQL 16 + PostGIS, Redis, nginx, uv, Python 3.12, las librerías del backend y las del frontend.
Crea el archivo `.env` a partir de `.env.example` y las bases de datos de desarrollo y de pruebas.
La primera vez tarda varios minutos (descarga unos cientos de MB). Se puede repetir sin romper nada.

### 4. Levantar el sistema

```powershell
wsl make up
```

Al terminar muestra el estado de cada servicio y la respuesta de `/health`. Debe decir `HTTP 200` y `"status": "ok"`.

Abre <http://localhost:8080>: verás la página **Estado del sistema** con los cuatro componentes en verde.

### 5. Comprobar que todo funciona

```powershell
wsl make test    # pruebas del backend (con cobertura) y del frontend
wsl make lint    # revisiones de estilo y de tipos
```

### 6. Activar las revisiones automáticas de cada commit

```powershell
py -m pip install --user pre-commit==4.7.0
py -m pre_commit install
```

### Para detener todo

```powershell
wsl make down
```

---

## Uso diario

| Quiero... | Comando (PowerShell, en la carpeta del proyecto) |
|---|---|
| Levantar o detener los servicios | `wsl make up` / `wsl make down` |
| Ver qué está corriendo | `wsl make status` |
| Ver los logs de la API y del worker | `wsl make logs` |
| Trabajar en el frontend con recarga automática | `cd frontend; npm run dev` → <http://localhost:5173> |
| Aplicar migraciones de base de datos | `wsl make migrate` |
| Correr pruebas / revisiones | `wsl make test` / `wsl make lint` |
| Ver todos los comandos | `wsl make` |

Direcciones útiles con el sistema arriba:

| Dirección | Qué es |
|---|---|
| <http://localhost:8080> | La aplicación (nginx). |
| <http://localhost:8080/api/v1/health> | Diagnóstico en JSON. |
| <http://localhost:8080/api/v1/docs> | Documentación interactiva de la API (OpenAPI). |

---

## Problemas comunes

| Síntoma | Causa probable y solución |
|---|---|
| `/health` responde 503 | El JSON dice qué componente falló y por qué. `wsl make status` muestra qué servicio está detenido; `wsl make up` lo vuelve a levantar. |
| La página no carga (después de reiniciar Windows o de `wsl --shutdown`) | Al apagarse Ubuntu se detienen los servicios. Corre `wsl make up` de nuevo. (Con los servicios corriendo, Ubuntu siguió encendido sin ninguna terminal abierta en la prueba de la Fase 0.) |
| Errores de librerías de Node (`esbuild`, `rollup`) | Se instalaron dependencias del frontend desde Ubuntu. Borra `frontend/node_modules` y corre `npm ci` en PowerShell dentro de `frontend/`. |
| `/bin/bash^M: bad interpreter` | Un script quedó con finales de línea de Windows. `.gitattributes` lo evita; si editaste a mano, guárdalo con LF. |
| La aplicación dice que falta una variable de entorno | Corre `wsl make bootstrap`: agrega a `.env` las variables nuevas de `.env.example`. |

---

## Estructura del repositorio

| Carpeta | Qué hay |
|---|---|
| [`backend/`](backend/README.md) | API FastAPI y worker Celery (Python 3.12, arquitectura hexagonal). |
| [`frontend/`](frontend/README.md) | Interfaz web (React 18 + TypeScript + Vite + Tailwind). |
| [`nginx/`](nginx/README.md) | Servidor web que une frontend, API y teselas en <http://localhost:8080>. |
| [`scripts/`](scripts/README.md) | Instalación y arranque de servicios en WSL. |
| [`geodata/`](geodata/README.md) | Pipeline de geodatos INEGI (Fase 1). |
| [`docs/`](docs/) | Especificación, ADRs y documentación. |
