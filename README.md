# Monitor de Noticias Geolocalizadas

Módulo que busca noticias sobre temas definidos por el usuario (**conceptos**, como "Ciberseguridad" o "Secuestro"), decide cuáles son relevantes, las resume, detecta **dónde ocurrió** cada hecho y lo pinta sobre un globo 3D enfocado en México.

- **Qué se construye:** [docs/ESPECIFICACION.md](docs/ESPECIFICACION.md)
- **Cómo se trabaja:** [CLAUDE.md](CLAUDE.md)
- **Decisiones de arquitectura:** [docs/adr/](docs/adr/README.md)
- **Historial de cambios:** [CHANGELOG.md](CHANGELOG.md)
- **Consultar o migrar la base de datos:** [docs/base-de-datos.md](docs/base-de-datos.md)

> Estado actual: **Fase 2 (conceptos)**. Además de los cimientos (servicios, `/health`) y el catálogo geográfico de México (INEGI) con su globo 3D, ya existen los conceptos de búsqueda: se crean, editan y prueban desde la pestaña **Conceptos**, que muestra las consultas exactas que se enviarían a cada proveedor sin gastar créditos. La búsqueda real de noticias, la geolocalización y los reportes llegan en las fases siguientes.

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

Todo lo demás (PostgreSQL 16 + PostGIS, Redis, nginx, Python 3.12, GDAL, tippecanoe, pmtiles y las librerías) lo instala el paso 3.

Espacio: unos **2 GB en `D:`** (geodatos y mapas) y **3 GB en `C:`** (Ubuntu, base de datos y carpeta de trabajo).

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

Instala y configura PostgreSQL 16 + PostGIS, Redis, nginx, uv, Python 3.12, las herramientas de geodatos (GDAL, tippecanoe, pmtiles), las librerías del backend y las del frontend.
Crea el archivo `.env` a partir de `.env.example` y las bases de datos de desarrollo y de pruebas.
La primera vez tarda varios minutos (descarga unos cientos de MB). Se puede repetir sin romper nada.

### 4. Levantar el sistema

```powershell
wsl make up
```

Al terminar muestra el estado de cada servicio y la respuesta de `/health`. Debe decir `HTTP 200` y `"status": "ok"`.

### 5. Cargar los geodatos (una sola vez, unos 30 min)

```powershell
wsl make migrate       # crea las tablas
wsl make geo-download  # INEGI (249 MB) y Natural Earth
wsl make geo-inspect   # revisa proyección y encoding; muestra 5 nombres con Ñ
wsl make geo-load      # carga a PostGIS (7 min), valida y genera los mapas
wsl make geo-basemap   # mapa base de Protomaps (1.3 GB, 10 min)
```

`geo-inspect` muestra 5 nombres reales: revisa que la Ñ y los acentos se vean bien antes de `geo-load`. `geo-load` termina con **"Todas las revisiones pasaron"** (criterios de la especificación §12). Detalles en [geodata/README.md](geodata/README.md).

Carga también los conceptos de ejemplo (Ciberseguridad, Secuestro, Extorsión, Robo de vehículos y Desaparición de personas):

```powershell
wsl make seed      # solo crea los que falten; se puede repetir sin riesgo
```

Abre <http://localhost:8080>: verás el **globo** con México. Busca "Iztapalapa" o haz clic en un estado. En la pestaña **Conceptos** elige uno, busca "Jalisco" en "Probar concepto" y presiona **Ver consultas**. La pestaña **Estado del sistema** muestra los cuatro componentes en verde.

### 6. Comprobar que todo funciona

```powershell
wsl make test    # pruebas del backend (con cobertura) y del frontend
wsl make lint    # revisiones de estilo y de tipos
```

### 7. Activar las revisiones automáticas de cada commit

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
| Ver los logs de la API, del worker y del reloj de Celery | `wsl make logs` |
| Trabajar en el frontend con recarga automática | `cd frontend; npm run dev` → <http://localhost:5173> |
| Aplicar migraciones de base de datos | `wsl make migrate` |
| Consultar la base (psql) / respaldarla | `wsl make db-shell` / `wsl make db-dump` |
| Recargar los geodatos (por ejemplo, edición nueva de INEGI) | `wsl make geo-download geo-inspect geo-load` |
| Correr pruebas / revisiones | `wsl make test` / `wsl make lint` |
| Ver todos los comandos | `wsl make` |

Direcciones útiles con el sistema arriba:

| Dirección | Qué es |
|---|---|
| <http://localhost:8080> | La aplicación: globo de geodatos (nginx). |
| <http://localhost:8080/api/v1/regions/search?q=izta> | Búsqueda de regiones en JSON. |
| <http://localhost:8080/api/v1/health> | Diagnóstico en JSON. |
| <http://localhost:8080/api/v1/docs> | Documentación interactiva de la API (OpenAPI). |

---

## Proveedores de noticias

| Proveedor | Estado | Cómo se activa |
|---|---|---|
| **SearchApi** (Google News) | Principal, de pago (1 crédito por búsqueda) | Tu llave en `.env`: `SEARCHAPI_API_KEY=…`. Tope mensual: `SEARCHAPI_MONTHLY_CREDIT_LIMIT` (100 por defecto). |
| **GDELT** | Gratuito. ⚠️ **Desactivado por defecto**: respondió 429 de forma persistente ([ADR-0012](docs/adr/0012-gdelt-desactivado-por-limite.md)) | `GDELT_ENABLED=false`. `wsl make gdelt-diagnostico` reintenta una consulta de prueba una vez al día y avisa cuando hay evidencia para proponer reactivarlo. |
| **Google News RSS** | ⚠️ **Fuera de producción** | Desactivado (`NEWS_RSS_ENABLED=false`). Ver la advertencia. |
| **Índice local** (`indice_local`) | Gratuito y activo. Busca en las notas que el sistema junta solo cada 15 minutos mientras `make up` corre ([ADR-0013](docs/adr/0013-ingesta-periodica-e-indice-local.md)) | Nada que activar. Fuentes: archivos de GDELT (`GDELT_GKG_ENABLED=true`, ~760 MB de descarga al día) y RSS de medios (`MEDIA_RSS_ENABLED=false` hasta revisar sus términos). `wsl make ingesta` corre una vez y muestra 5 ejemplos. |

**Cómo funciona el índice local.** Es como una hemeroteca propia: cada 15 minutos el reloj de Celery baja el archivo más reciente de GDELT, se queda con las notas en español que mencionan México y guarda solo título, fragmento, medio, fecha y link (nunca el artículo completo). Al buscar, una nota responde si contiene alguna palabra clave **completa** (sin acentos, conservando la Ñ), ninguna exclusión y el lugar en su texto; si la región es un estado, también cuenta que GDELT la haya ubicado ahí. Ojo: "hackeo" no encuentra "hackeos"; pon las dos formas en el concepto si importan. Las ubicaciones de GDELT tienen errores, así que son solo pistas.

> ⚠️ **Google News RSS no se usa en producción.** El propio feed declara que solo puede usarse en un lector de noticias personal y no comercial, y que cualquier otro uso está prohibido (cita exacta en [ADR-0011](docs/adr/0011-google-news-rss-fuera-de-produccion.md)). Está desactivado por defecto; solo se habilita a propósito en desarrollo con `NEWS_RSS_ENABLED=true`, y deja una advertencia en el registro. La revisión legal está pendiente.

Para probar un proveedor con **una** consulta real, que pide confirmación antes de enviarla:

```powershell
wsl make probar-proveedor ARGS="--proveedor gdelt --concepto Ciberseguridad --region 09 --dias 7 --nombre prueba"
```

Las pruebas automáticas nunca llaman a internet: usan las respuestas grabadas en `backend/tests/fixtures/providers/`.

---

## Problemas comunes

| Síntoma | Causa probable y solución |
|---|---|
| `/health` responde 503 | El JSON dice qué componente falló y por qué. `wsl make status` muestra qué servicio está detenido; `wsl make up` lo vuelve a levantar. |
| La página no carga (después de reiniciar Windows o de `wsl --shutdown`) | Al apagarse Ubuntu se detienen los servicios. Corre `wsl make up` de nuevo. (Con los servicios corriendo, Ubuntu siguió encendido sin ninguna terminal abierta en la prueba de la Fase 0.) |
| Errores de librerías de Node (`esbuild`, `rollup`) | Se instalaron dependencias del frontend desde Ubuntu. Borra `frontend/node_modules` y corre `npm ci` en PowerShell dentro de `frontend/`. |
| `/bin/bash^M: bad interpreter` | Un script quedó con finales de línea de Windows. `.gitattributes` lo evita; si editaste a mano, guárdalo con LF. |
| La aplicación dice que falta una variable de entorno | Corre `wsl make bootstrap`: agrega a `.env` las variables nuevas de `.env.example`. |
| El globo sale gris o sin fronteras | Faltan los mapas: corre `wsl make geo-load` y `wsl make geo-basemap`. Si acabas de actualizar, recarga con Ctrl+Mayús+R. |
| DBeaver no conecta | Usa `127.0.0.1` y no `localhost` (ver [docs/base-de-datos.md](docs/base-de-datos.md)). |

---

## Estructura del repositorio

| Carpeta | Qué hay |
|---|---|
| [`backend/`](backend/README.md) | API FastAPI y worker Celery (Python 3.12, arquitectura hexagonal). |
| [`frontend/`](frontend/README.md) | Interfaz web (React 18 + TypeScript + Vite + Tailwind). |
| [`nginx/`](nginx/README.md) | Servidor web que une frontend, API y teselas en <http://localhost:8080>. |
| [`scripts/`](scripts/README.md) | Instalación y arranque de servicios en WSL. |
| [`geodata/`](geodata/README.md) | Datos geográficos: descargas, mapas generados y alias. La lógica del pipeline está en `backend/app/geodata/`. |
| [`docs/`](docs/) | Especificación, ADRs y documentación. |
