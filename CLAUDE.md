# CLAUDE.md — Reglas permanentes del proyecto `monitor-noticias`

Lee este archivo al inicio de cada sesión. Aquí está **cómo** trabajamos.
**Qué** construimos está en `docs/ESPECIFICACION.md` (léelo completo antes de planear cualquier fase).
Si una petición puntual en el chat contradice algo de aquí, pregunta antes de actuar.

---

## 1. Contexto en 30 segundos

- Módulo de monitoreo de noticias geolocalizadas sobre un globo 3D, enfocado en México. Forma parte de un sistema mayor y se integrará después por API.
- Usuarios finales: analistas, no programadores. La UI tiene que ser clara sin capacitación.
- Responsable del proyecto: **Benji**. Él revisa y aprueba. Aprende haciendo: primero ejecuta y observa, luego entiende el porqué. Explícale en español claro, con analogías cuando ayuden y sin jerga innecesaria.
- **Idioma**:
  - En español: toda la comunicación, documentación, docstrings, comentarios, mensajes de commit y textos de la UI.
  - En inglés, sin acentos ni ñ: los identificadores de código (variables, funciones, clases, tablas, columnas, endpoints), con la convención de cada lenguaje.

---

## 2. Flujo de trabajo obligatorio

1. **Inicio de fase.** Usa modo plan. Lee la fase en `docs/ESPECIFICACION.md` y presenta un plan con lo siguiente, luego **espera aprobación**:
   - archivos a crear o modificar,
   - decisiones a tomar,
   - riesgos,
   - cómo vas a verificar cada entregable.
2. **Tareas pequeñas.** Cada tarea termina con código, pruebas, documentación, verificación ejecutada y commit, en ese orden.
3. **Nada está "terminado" sin ejecutarse.** Muestra la salida real (tests, `curl`, conteos de la base, capturas de consola). Si algo no se pudo verificar, dilo explícitamente y explica por qué.
4. **Cierre de fase.** Detente y entrega:
   - qué se hizo,
   - comandos exactos para que Benji lo verifique por su cuenta,
   - decisiones tomadas (con su ADR si aplica),
   - pendientes y riesgos.

   No empieces la siguiente fase sin aprobación.
5. **Problemas de fondo.** Esto incluye una especificación contradictoria, una API que no responde como se documentó o una librería deprecada. Detente y presenta causa raíz, evidencia (salida real, link a la documentación), opciones con pros y contras, y tu recomendación. No improvises un parche silencioso.
6. **Antes de procesar datos reales completos** (carga de geodatos, búsquedas reales que gasten créditos), muestra **5 ejemplos reales** del resultado y espera confirmación.
7. **No inventes APIs.** Antes de usar un endpoint o parámetro de un proveedor externo (SearchApi, GDELT, Google News RSS, Gemini, MapLibre, PMTiles), consulta su documentación vigente. Si no puedes confirmarlo, márcalo como `# VERIFICAR:` y avísale a Benji.

---

## 3. Permisos

| Acción | Permiso |
|---|---|
| Leer archivos, correr tests y linters, comandos de solo lectura | Libre |
| Levantar y bajar los servicios de desarrollo (`make up` / `make down`) | Libre |
| Commits locales en la rama de trabajo (con lint y tests pasando) | Libre |
| `git push`, merge a `develop` o `main`, crear tags | Requiere aprobación |
| Borrar archivos o datos, migraciones destructivas | Requiere aprobación |
| Instalar dependencias que no estén en la especificación | Requiere aprobación (justifica por qué) |
| Llamadas reales a APIs de pago fuera de los tests | Requiere aprobación (indica cuántos créditos) |
| Commitear secretos, `git push --force`, reescribir historial publicado | **Prohibido** |
| Desactivar, saltar o debilitar pruebas para que pasen | **Prohibido** |
| `# type: ignore`, `# noqa`, `eslint-disable` sin comentario que lo justifique | **Prohibido** |

---

## 4. Control de cambios (Git)

### 4.1 Ramas

- `main`: estable. Solo recibe merges de `develop` al cerrar una fase, con tag.
- `develop`: integración.
- Ramas de trabajo: `feat/f<N>-<descripcion-corta>`, `fix/<descripcion>`, `docs/<...>`, `chore/<...>`, `refactor/<...>`.
  - Ejemplo: `feat/f3-adaptador-searchapi`.

### 4.2 Mensajes de commit: Conventional Commits en español

```
<tipo>(<alcance>): <resumen en imperativo, minúsculas, máx. 72 caracteres, sin punto final>

<cuerpo: QUÉ cambió y POR QUÉ. El CÓMO ya lo dice el código.
Líneas de máx. 72 caracteres.>

Fase: F<N>
[BREAKING CHANGE: <descripción>]
```

**Tipos:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `build`, `ci`.

**Alcances:** `geo`, `concepts`, `providers`, `pipeline`, `llm`, `geocoding`, `api`, `db`, `frontend`, `globe`, `reports`, `auth`, `infra`, `docs`.

**Reglas:**
- Un commit es un cambio lógico que compila y pasa las pruebas por sí solo.
- No mezcles un refactor con una funcionalidad nueva.
- Si el resumen necesita la palabra "y", probablemente son dos commits.
- El cuerpo es obligatorio en `feat`, `fix`, `refactor` y `perf`.

**Ejemplo bueno:**

```
feat(providers): agregar adaptador de SearchApi para Google News

Implementa NewsProviderPort usando el motor google_news de SearchApi.
Se eligió SearchApi como fuente de resultados de Google porque la
Custom Search JSON API de Google está cerrada a clientes nuevos y se
descontinúa el 1 de enero de 2027 (ver ADR-0003).

Las respuestas se normalizan a RawArticle para que el pipeline no
dependa del formato de ningún proveedor.

Fase: F3
```

**Ejemplo bueno (fix):**

```
fix(geocoding): no asignar municipio cuando el nombre es ambiguo

"San Pedro" existe en varios estados. Antes se tomaba el primer
resultado de la consulta y se geolocalizaban notas en el estado
equivocado. Ahora, sin pista de estado, la mención se marca como
ambigua con confianza baja y no se pinta a nivel municipio.

Agrega prueba que reproduce el caso.

Fase: F4
```

**Ejemplos malos:** `cambios`, `fix`, `avance`, `wip`, `agregué cosas del mapa y arreglé un bug`.

### 4.3 Versionado

- Al cerrar cada fase se crea el tag `v0.<N>.0` (con aprobación).
- `CHANGELOG.md` se actualiza en formato *Keep a Changelog*, en español.

---

## 5. Documentación del código

**Objetivo:** que alguien que nunca vio el proyecto entienda qué hace cada pieza y por qué existe.

- **Cada archivo** abre con un docstring o comentario que diga qué responsabilidad tiene, quién lo usa y qué **no** hace.
- **Cada función o clase pública** lleva docstring estilo Google, en español, con descripción, `Args`, `Returns` y `Raises`. Agrega un `Example` cuando el uso no sea obvio.
- **Los comentarios en línea explican el PORQUÉ**, no el qué.
  - Malo: `# incrementa i`.
  - Bueno: `# GDELT devuelve máx. 250 resultados por llamada; partimos el rango de fechas para no perder notas`.
- **Sin números mágicos.** Toda constante lleva nombre y un comentario de origen (documentación, decisión, medición).
- **Cada carpeta principal** tiene un `README.md` corto: qué hay ahí y cómo se usa.
- **Decisiones de arquitectura** van en `docs/adr/NNNN-titulo.md`, con las secciones Contexto, Decisión, Alternativas consideradas y Consecuencias.
- **La documentación se actualiza en el mismo commit** que el cambio de código que la vuelve obsoleta.

**Ejemplo de docstring esperado:**

```python
def build_queries(concept: Concept, region: Region, window: DateWindow) -> list[PlannedQuery]:
    """Genera las consultas que se enviarán a cada proveedor de noticias.

    Combina las palabras clave del concepto con el nombre de la región en
    una sola consulta con operadores OR, para gastar un crédito por
    proveedor en lugar de uno por palabra clave. Si la consulta excede el
    límite de longitud del proveedor, las palabras clave se reparten en
    varios grupos.

    Args:
        concept: Concepto con palabras clave y términos de exclusión.
        region: Región seleccionada (país, estado, municipio o localidad).
        window: Rango de fechas de la búsqueda.

    Returns:
        Consultas planeadas, una o más por proveedor activo. Todavía no se
        ejecuta ninguna: sirven para estimar créditos antes de buscar.

    Raises:
        EmptyConceptError: Si el concepto no tiene palabras clave activas.

    Example:
        >>> build_queries(ciberseguridad, iztapalapa, DateWindow.last_days(7))
        [PlannedQuery(provider="searchapi", text='(ciberataque OR hackeo) Iztapalapa', ...)]
    """
```

---

## 6. Estándares de código

### 6.1 Backend (Python 3.12)

**Herramientas y tipado**
- Type hints obligatorios en todo el código.
- `ruff` para lint y formato.
- `mypy --strict` en `domain/` y `application/`.

**Arquitectura**
- Arquitectura hexagonal: las dependencias apuntan hacia adentro (`api` y `adapters` dependen de `application`, que depende de `domain`).
- `domain/` no importa nada de frameworks ni librerías externas.
- Sin lógica de negocio en routers ni en adaptadores.
- Configuración solo con `pydantic-settings` desde variables de entorno. Nada hardcodeado.

**Logs y errores**
- Logs estructurados en JSON, con `search_id` cuando aplique. Nunca `print`.
- Excepciones de dominio propias. Los adaptadores traducen los errores externos (HTTP, timeouts) a esas excepciones.
- Llamadas externas con timeout explícito, reintentos con backoff exponencial y límite de concurrencia.

### 6.2 Frontend (TypeScript)

- `strict: true`, ESLint y Prettier.
- Componentes pequeños, con una sola responsabilidad.
- Las llamadas HTTP viven en `src/services/`, nunca dentro de componentes.
- Estado global con Zustand; datos del servidor con TanStack Query.

### 6.3 Base de datos (PostgreSQL + PostGIS)

**Migraciones e índices**
- Cambios de esquema solo con migraciones Alembic. Nunca cambios manuales.
- Toda columna que se use para filtrar, unir o paginar lleva su índice **en la misma migración** que la crea.

**Consultas y cargas**
- Paginación por cursor (`WHERE id > :last_id ORDER BY id LIMIT :n`). **Nunca `OFFSET`.**
- Cargas masivas en lotes de 10,000 a 50,000 registros, con commit por lote. Usa `COPY` cuando aplique.
- Fechas en UTC (`timestamptz`); se muestran en `America/Mexico_City`.

**Nombres**
- El nombre original se guarda intacto para mostrarlo.
- Para comparar se usa una columna aparte `name_norm`: mayúsculas, sin acentos, **conservando la Ñ**, sin espacios repetidos.

### 6.4 Archivos de texto externos

Antes de cargar shapefiles, CSV o DBF, detecta el encoding (probar `utf-8`, `cp1252`, `latin1`, `cp850`) y valida con 5 ejemplos que contengan Ñ y acentos.

---

## 7. Pruebas

- Toda la lógica de `domain/` y `application/` lleva pruebas unitarias. Cobertura mínima del 85% en esas capas.
- Los adaptadores externos se prueban con respuestas grabadas en `tests/fixtures/`, usando `httpx2.MockTransport` (ADR-0010). **Las pruebas nunca llaman a internet ni gastan créditos.**
- Las pruebas de integración corren contra el PostGIS local de WSL, en una base de pruebas separada (`monitor_noticias_test`), nunca contra la base de desarrollo (ver ADR-0006).
- Todo bug corregido lleva primero una prueba que lo reproduce.
- El frontend usa `vitest` para la lógica, más una prueba de humo del flujo principal.

---

## 8. Seguridad

- Secretos solo en `.env`, que está en `.gitignore`.
- `.env.example` lista todas las variables, con un comentario de para qué sirve cada una.
- Las llaves de APIs **nunca** llegan al frontend: todo pasa por el backend.
- Cada búsqueda queda en la bitácora de auditoría: usuario, parámetros, fecha, consultas ejecutadas y créditos consumidos.
- De cada noticia se guardan metadatos, resumen generado y link a la fuente. Los reportes **nunca** reproducen el artículo completo.

---

## 9. Comandos del proyecto

Mantén esta sección actualizada conforme se creen los comandos.

Se ejecutan en Ubuntu (WSL). Desde PowerShell, en la carpeta del proyecto: `wsl make <comando>` (ADR-0006).

```
make bootstrap       # instala servicios y dependencias (se puede repetir)
make up              # levanta PostgreSQL, Redis, API, worker, reloj de Celery (ingesta) y nginx (http://localhost:8080)
make down            # los detiene
make status          # qué corre y resultado de /health
make logs            # sigue los logs de la API, del worker y del reloj
make test            # pruebas backend (con cobertura) + frontend
make lint            # ruff + mypy + eslint + prettier + tipos de TypeScript
make format          # aplica el formato de ruff y Prettier
make migrate         # aplica migraciones Alembic
make frontend-build  # compila el frontend que sirve nginx
make geo-download    # descarga INEGI y Natural Earth (con manifiesto)
make geo-inspect     # proyección, encoding, conteos y 5 nombres reales con Ñ
make geo-load        # carga a PostGIS, valida (§12) y genera PMTiles
make geo-validate    # solo los criterios de aceptación del catálogo
make geo-tiles       # solo los PMTiles de las capas de INEGI
make geo-terms       # términos de búsqueda, alias y códigos de país (ARGS=--muestra para ver sin escribir)
make geo-basemap     # mapa base de Protomaps (mundo z6 + México z14)
make seed            # carga los conceptos semilla que falten (no pisa ediciones)
make probar-proveedor ARGS="--proveedor gdelt --nombre x"  # UNA consulta real, pide confirmar
make buscar ARGS="--concepto Extorsión --region 14 --dias 7"  # búsqueda real de punta a punta: muestra costo, pide "si" y enseña 5 notas (--aqui sin worker)
make reubicar          # vuelve a ubicar las notas de la última búsqueda sin pagar a la IA (ARGS="--busqueda <id>"; --con-ia las vuelve a pasar por la IA desde su texto guardado, pide "si")
make gdelt-diagnostico  # reintento diario de D1 en GDELT (ADR-0012); avisa si se cumple el criterio
make ingesta           # corre la ingesta al índice local una vez y muestra 5 ejemplos (ADR-0013)
make ingesta-historial DIAS=7  # mide días anteriores de GDELT y muestra 5 ejemplos; DESCARGAR=si baja todo
make ngramas-muestra   # prueba real de una hora de ngramas de GDELT: consumo, espacio y 5 ejemplos
make db-shell        # consola SQL (psql) en la base de desarrollo
make db-dump         # respaldo para migrar la base (docs/base-de-datos.md)
```
