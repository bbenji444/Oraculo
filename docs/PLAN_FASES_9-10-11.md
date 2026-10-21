# Plan — Fases 9, 10 y 11: Muro de investigación y capas vivas

Versión 1.0 · Octubre 2026 · Responsable: Benji

Este documento amplía `docs/ESPECIFICACION.md`. Las reglas de **cómo** se trabaja siguen en `CLAUDE.md` y aplican igual aquí. Este plan define **qué** se construye en tres fases nuevas:

- **Fase 9 — Tablero de investigación ("el muro"):** casos, entidades, vínculos y la visualización de todo eso sobre el globo 3D. No depende de ninguna fuente externa nueva. Es el núcleo.
- **Fase 10 — Capas vivas base:** sismos, incendios, vuelos y barcos en tiempo real sobre el globo (inspirado en God's Eye View). Fase de **desarrollo y evaluación**.
- **Fase 11 — Capas avanzadas y modo cine:** satélites, clima, cámaras, modos visuales (visión nocturna, térmico, cabina) y el orquestador que une casos + capas vivas. Fase de **desarrollo y evaluación**.

Las tres se construyen sobre lo ya existente (Fases 0–8) sin romperlo. Si algo de aquí contradice lo ya construido, se detiene y se consulta con Benji antes de actuar.

---

## Parte I — Principio rector: por qué esto es escalable

La decisión más importante de todo este plan es una sola:

> **Las entidades no pertenecen a las noticias. Son objetos independientes que tienen fuentes.**

Una persona, una organización, un vehículo o un lugar son objetos de primera clase. Hoy su única fuente es una noticia. Mañana otra fuente será una base de datos real del sistema Oráculo. El tablero de investigación **no sabe ni le importa de dónde salió cada entidad**: solo muestra entidades y cómo se conectan.

Consecuencia práctica: el día que se conecten las bases reales, **no se reescribe el tablero**. Se agrega un "proveedor de entidades" nuevo, exactamente igual que en la Fase 3 se agregó SearchApi como proveedor de noticias. El modelo de datos de la Fase 9 deja ese enchufe preparado (tabla `external_links`, sección 6), pero **no lo usa todavía**. En esta etapa, la única fuente de entidades son las noticias.

Esto también aplica a las capas vivas: cada fuente de God's Eye (vuelos, barcos, sismos…) es un "proveedor de capa", conectado por un puerto, igual que los proveedores de noticias. Agregar una capa nueva es escribir un adaptador, no tocar el globo.

---

## Parte II — Fase 9: El tablero de investigación

### 9.1 Visión

Un analista abre un **Caso** (por ejemplo "Homicidio estilista Polanco"). Dentro del caso va agregando noticias. El sistema, con el LLM que ya usa el proyecto (OpenAI), **propone** las personas, organizaciones, lugares y vehículos que aparecen en cada noticia. El analista **confirma** cuáles sirven y descarta el ruido. Con lo confirmado, el sistema arma un **grafo de vínculos**: quién aparece con quién, en qué lugares y en qué fechas, y lo dibuja **sobre el globo 3D** con una experiencia cinematográfica.

El valor: lo que un investigador no puede ver leyendo noticias una por una (que "Eduardo N" aparece en 4 notas de 3 municipios, conectado con la víctima y con una organización) aquí salta a la vista solo.

### 9.2 Glosario nuevo

| Término | Significado |
|---|---|
| **Caso** | Contenedor de una investigación: nombre, descripción, estado, nivel de sensibilidad. Agrupa noticias, entidades, vínculos y notas. |
| **Entidad** | Objeto de interés: persona, organización, lugar, vehículo, cuenta, teléfono u otro. Es independiente de la noticia. |
| **Mención** | Aparición concreta de una entidad en una noticia, con su texto exacto, su rol y su confianza. Una entidad tiene muchas menciones. |
| **Entidad resuelta** | Varias menciones de "la misma" persona fusionadas en una sola entidad (de-duplicación). La fusión de personas siempre la confirma un humano. |
| **Estatus legal** | Para personas: `mencionado`, `señalado`, `detenido`, `víctima`, `testigo`, `funcionario`. Refleja lo que dice la noticia, nunca una conclusión del sistema. |
| **Vínculo** | Relación entre dos entidades: aparecen juntas, mismo hecho, familiar, asociado, ubicado en, etc. Tiene origen (coocurrencia, LLM o humano) y confianza. |
| **Confirmado** | Una entidad o vínculo que un humano validó. Lo propuesto por el LLM empieza como "sugerido" hasta que alguien lo confirma. |
| **Enlace externo** | Conexión reservada (no usada en Fase 9) de una entidad hacia un registro de otra base del sistema Oráculo. Es el enchufe a futuro. |

### 9.3 Historias de uso

**H9.1 — Iniciar un caso y poblarlo.**
> Benji entra a la sección "Casos" y crea "Homicidio estilista Polanco". Vuelve a Explorar, corre su búsqueda de Homicidio en Miguel Hidalgo, y en cada noticia que le sirve presiona "Agregar al caso". Las 8 notas del hecho quedan dentro del caso.

**H9.2 — Confirmar entidades.**
> Al agregar las noticias, el sistema procesó su texto y propone entidades: la persona "Eduardo Ederly González (Eduardo N)" marcada como *señalado*, la persona "Miguel de la Mora (Micky Hair)" marcada como *víctima*, el lugar "Polanco", la organización "FGR". Benji revisa la lista, confirma las cuatro y descarta una mención basura ("Morena", que salió de una nota tangencial). Solo lo confirmado entra al muro.

**H9.3 — El muro sobre el globo.**
> Benji abre la vista "Muro" del caso. El globo vuela a la Ciudad de México. Sobre el mapa aparecen nodos que brillan: las personas, los lugares y las notas, conectados por **arcos de luz**. Eduardo N y Micky Hair están unidos por una línea (mismo hecho); de Eduardo N sale otra línea hacia Polanco. Benji da click en Eduardo N: el mundo se recorre suavemente a la izquierda, la cámara orbita el nodo, y por la derecha entra un panel con todo lo que se sabe de esa persona: sus 4 menciones, sus vínculos y su línea de tiempo.

**H9.4 — Línea de tiempo.**
> Benji arrastra la barra de tiempo del caso desde septiembre hasta hoy. Los nodos y arcos van apareciendo conforme avanzan las fechas: primero el homicidio, luego las detenciones de abril, luego la orden de aprehensión. Presiona "reproducir" y el caso se arma solo como una animación.

**H9.5 — Mano del investigador.**
> Benji conecta manualmente dos entidades que el sistema no relacionó, marca una como "línea de investigación", y escribe una nota anclada a Eduardo N: "verificar relación con caso previo". Su criterio queda guardado, distinguible de lo que propuso la IA.

### 9.4 Decisiones de arquitectura (ADRs de esta fase)

- **ADR-0101 — Entidades source-agnostic.** Las entidades y vínculos no dependen de la fuente. Tabla `external_links` reservada para el futuro enchufe a las bases de Oráculo, declarada pero sin uso en Fase 9.
- **ADR-0102 — Motor de visualización del muro.** *Primera tarea de la fase, a decidir con evidencia.* Evaluar si el globo actual (MapLibre GL) se potencia con una capa de efectos encima (por ejemplo deck.gl sobre el mismo mapa) o si conviene migrar a un motor con más control de efectos 3D. Criterio: lograr arcos, brillos y cámara cinematográfica **manteniendo 60 fps** en un equipo de oficina. Se prueban ambas con un prototipo mínimo antes de decidir.
- **ADR-0103 — Extracción de entidades sobre el pipeline existente.** La extracción se hace en la misma pasada del LLM que ya genera el resumen, no en un paso aparte, para no duplicar costo. Se versiona el prompt.
- **ADR-0104 — Confirmación humana obligatoria.** Ninguna entidad propuesta por el LLM entra al muro ni se fusiona con otra sin que un humano la confirme. La fusión de personas nunca es automática.
- **ADR-0105 — Estatus legal y procedencia como campos de primera clase.** Toda entidad-persona lleva estatus legal; toda entidad y todo vínculo llevan origen (LLM/humano/derivado) y confianza. Es requisito para que el módulo sea auditable y para la futura integración con datos reales.

### 9.5 Experiencia visual (el "modo videojuego")

Esto es lo que hace que parezca una obra y no una tabla. Todo vive **sobre el globo 3D existente**.

**Nodos**
- Cada entidad confirmada es un nodo con color por tipo (persona, lugar, organización, vehículo) y un segundo indicador por estatus legal (por ejemplo, borde rojo = señalado, azul = víctima).
- Las personas se colocan en la ubicación del hecho al que están ligadas; los lugares, en su coordenada; las organizaciones, cerca de sus menciones.
- Los nodos tienen brillo (bloom) suave y laten ligeramente. El seleccionado late más fuerte y atenúa a los demás.

**Arcos**
- Cada vínculo es un arco de luz que sigue la curva del globo (gran círculo) entre las dos ubicaciones. Si dos entidades comparten municipio, el arco es corto; si cruzan estados, se ve volar sobre el mapa.
- El grosor y el brillo del arco reflejan la confianza del vínculo. Los vínculos sugeridos (sin confirmar) se dibujan punteados.

**Cámara cinematográfica**
- Al abrir un caso: vuelo suave hasta encuadrar todos sus nodos.
- Al seleccionar una entidad: el globo se recorre a la izquierda, la cámara orbita el nodo y entra el panel lateral por la derecha (justo el comportamiento que pediste).
- Transiciones con aceleración/desaceleración (easing), nunca saltos secos.

**Modo constelación**
- Una vista alterna donde las noticias del caso flotan como puntos de luz sobre México y los vínculos las unen, como un cielo estrellado del caso. Ideal para ver el panorama completo de un vistazo.

**Línea de tiempo**
- Barra inferior con los hechos del caso ordenados por fecha. Al arrastrarla, nodos y arcos aparecen/desaparecen según el periodo. Botón "reproducir" que anima el crecimiento del caso en el tiempo.

**Rendimiento (obligatorio)**
- Límite de nodos visibles configurable (`CASE_MAX_VISIBLE_NODES`, por ejemplo 150); el resto se agrupa o se oculta tras un control.
- El cálculo de posiciones del grafo corre en un web worker o se precalcula en el servidor, nunca en cada frame.
- Niveles de detalle: con el globo lejos se ven clusters; al acercar, se despliegan los nodos.
- Meta: 60 fps al rotar y al animar en un equipo de oficina. Si un efecto no se puede sostener a 60 fps, se degrada con elegancia antes que trabarse.

### 9.6 Modelo de datos nuevo (PostgreSQL + PostGIS)

Todas con `created_at`/`updated_at`. Los nombres de persona guardan el original y un `name_norm` (mayúsculas, sin acentos, con Ñ) para comparar, igual que el resto del proyecto.

**`cases`** — id uuid · name · description · status(`open`/`closed`/`archived`) · sensitivity(`normal`/`reservado`/`confidencial`) · created_by · closed_at

**`entities`** — id bigserial · type(`person`/`org`/`place`/`vehicle`/`account`/`phone`/`other`) · canonical_label · label_norm · legal_status (solo personas; enum de 9.2) · is_confirmed bool · confirmed_by · merged_into (FK a entities, para resolución) · notes

**`entity_aliases`** — entity_id · alias · alias_norm

**`entity_mentions`** — id · entity_id · article_id · mention_text · role(`event`/`mentioned`) · legal_status_hint · confidence · extracted_by (modelo + prompt_version) · char_span · created_at
> Es la evidencia: de qué noticia salió cada entidad y con qué texto exacto.

**`relationships`** — id · entity_a · entity_b · type(`appears_with`/`same_event`/`family`/`associate`/`employer`/`located_in`/`owns`/`custom`) · custom_label · origin(`cooccurrence`/`llm`/`human`) · confidence · is_confirmed · confirmed_by · notes
> Las de origen `cooccurrence` se derivan solas (dos entidades en la misma noticia → `appears_with`). Las de la IA y las del humano se marcan como tal.

**`case_items`** — case_id · item_type(`article`/`entity`) · item_id · added_by · pinned · note

**`case_entities`** — case_id · entity_id · case_role (rol dentro de ESTE caso) · case_status · tag (etiqueta libre del analista) · added_by
> Permite que la misma persona tenga un rol distinto en casos distintos sin alterar la entidad global.

**`case_notes`** — id · case_id · body · anchor_type(`none`/`entity`/`article`/`relationship`) · anchor_id · author · created_at

**`external_links`** *(reservada, SIN uso en Fase 9)* — id · entity_id · external_system (`imss`/`banorte`/`repuve`/…) · external_ref · link_confidence · linked_by · created_at
> Este es el enchufe a las bases reales. Se crea la tabla y su migración, se documenta, y se deja vacía con una nota clara. Ninguna lógica de la Fase 9 la escribe ni la lee.

**`audit_log`** *(extender la existente)* — registrar además: crear/editar/cerrar caso, confirmar/descartar entidad, crear/confirmar vínculo manual, y **ver un caso** (quién abrió qué caso y cuándo). Para una herramienta de esta naturaleza, el registro de visualización es tan importante como el de edición.

### 9.7 Extracción de entidades con el LLM

Se amplía la salida del enriquecimiento que ya existe. En la misma llamada en que el LLM resume la noticia, devuelve también las entidades.

**Salida esperada (validada con Pydantic):**

```json
{
  "entities": [
    {
      "type": "person",
      "label": "Eduardo Ederly González",
      "aliases": ["Eduardo N", "Eduardo Ederly"],
      "role": "event",
      "legal_status_hint": "señalado",
      "confidence": 0.9,
      "evidence_span": "un juez emitió una orden de captura contra el empresario Eduardo Ederly González"
    },
    {
      "type": "person",
      "label": "Miguel de la Mora",
      "aliases": ["Micky Hair"],
      "role": "event",
      "legal_status_hint": "víctima",
      "confidence": 0.95,
      "evidence_span": "el asesinato del estilista Miguel de la Mora"
    },
    { "type": "place", "label": "Polanco", "role": "event", "confidence": 0.9 },
    { "type": "org", "label": "FGR", "role": "mentioned", "confidence": 0.7 }
  ]
}
```

**Reglas del prompt (estrictas, por ser herramienta policial):**
- **Solo lo que dice el texto.** Nada de inferir, deducir ni completar. Si no está escrito, no se extrae.
- **El estatus legal refleja lo que afirma la nota, no una conclusión.** "Orden de aprehensión" → `señalado`. "Fue detenido" → `detenido`. "La víctima" → `víctima`. **Nunca** `culpable`. Si la nota no lo dice, el campo va nulo.
- **Cada entidad trae su `evidence_span`:** el fragmento textual donde aparece, para que el analista verifique.
- **No se cruzan datos entre noticias ni con otras bases.** La extracción es por noticia, aislada.
- Todo lo extraído entra como **sugerido**, nunca confirmado.

### 9.8 Resolución de entidades (de-duplicación)

- Dentro de un caso, si dos entidades-persona tienen `name_norm` igual o muy parecido (trigram ≥ 0.9) y comparten alias, el sistema **sugiere** fusionarlas. No las fusiona solo.
- El analista ve las menciones de cada una lado a lado y decide. Al fusionar, una queda como `merged_into` de la otra; se conserva el historial.
- Las personas **nunca** se fusionan automáticamente a nivel global. El riesgo de unir a dos personas distintas con el mismo nombre, en una herramienta así, es inaceptable.

### 9.9 API nueva

| Método | Ruta | Descripción |
|---|---|---|
| GET/POST/PATCH | `/cases` | Listar, crear, editar casos |
| POST | `/cases/{id}/items` | Agregar noticia o entidad al caso |
| GET | `/cases/{id}/graph` | Grafo del caso: nodos, arcos, posiciones y fechas, listo para el globo |
| GET | `/cases/{id}/timeline` | Hechos ordenados por fecha |
| GET | `/entities/{id}` | Detalle: menciones, vínculos, casos donde aparece |
| POST | `/entities/{id}/confirm` · `/discard` | Confirmar o descartar una entidad sugerida |
| POST | `/entities/merge` | Fusionar dos entidades (requiere confirmación) |
| POST | `/relationships` | Crear vínculo manual |
| POST | `/relationships/{id}/confirm` | Confirmar vínculo sugerido |
| POST | `/cases/{id}/notes` | Nota del investigador |

### 9.10 Privacidad, control de acceso y auditoría

Primera clase desde el diseño, no un parche posterior:
- **Control de acceso por caso.** Un analista ve solo los casos a los que tiene acceso. Nivel de sensibilidad por caso.
- **Auditoría completa**, incluida la de **visualización** (quién vio qué caso).
- **Minimización.** La extracción toma solo lo publicado; no cruza con otras fuentes dentro de esta fase.
- **Estatus legal visible siempre**, para no confundir "señalado" con "culpable" en ninguna pantalla ni reporte.
- Conviene que Benji informe a su jefe que esta fase ya maneja datos personales de personas identificadas en noticias.

### 9.11 Sub-fases de la Fase 9

| Sub-fase | Entregable | Criterio de aceptación |
|---|---|---|
| **9.1** | Decisión de motor visual (ADR-0102) con prototipo de arcos y cámara | Prototipo a 60 fps; ADR escrito |
| **9.2** | Modelo de datos y migraciones (incluida `external_links` reservada) | Migraciones aplican; índices creados |
| **9.3** | CRUD de casos y agregar ítems | Historia H9.1 completa |
| **9.4** | Extracción de entidades por LLM + confirmación humana | Historia H9.2; prompt versionado; pruebas con fixtures |
| **9.5** | Vínculos (coocurrencia + manuales) y resolución de entidades | Sugerencia de fusión funciona; nunca fusiona sola |
| **9.6** | El muro sobre el globo: nodos, arcos, cámara, panel lateral, constelación | Historia H9.3 completa, fluida |
| **9.7** | Línea de tiempo, notas del investigador, auditoría de visualización | Historias H9.4 y H9.5 completas |

---

## Parte III — Fase 10: Capas vivas base (God's Eye, parte 1)

**Naturaleza: desarrollo y evaluación.** El objetivo es probar si estas capas aportan valor real al monitoreo antes de decidir cualquier uso definitivo.

### 10.1 Cómo se integra God's Eye View

God's Eye View es un proyecto aparte, con su propio motor 3D. **No se importa como librería.** La forma correcta y coherente es consumir **sus mismas fuentes de datos públicas** sobre tu propio globo, como capas encendibles. Así queda **una sola aplicación**, no dos globos pegados.

El código de God's Eye View es MIT (libre para inspirar y reutilizar código con su aviso de copyright). Sirve como **referencia de implementación**: cómo consultan cada fuente, cada cuánto, cómo la dibujan. Cada **fuente de datos**, en cambio, se consume directamente bajo sus propios términos.

### 10.2 Arquitectura de capas

Un puerto `LiveLayerPort` con un adaptador por capa, igual que los proveedores de noticias:
- cada capa se enciende/apaga de forma independiente desde la UI;
- cada una tiene su propia frecuencia de actualización;
- los datos vivos **no se mezclan** con los datos de investigación (casos). Comparten el globo como lienzo, nada más. Son datos efímeros, no se guardan como evidencia salvo que el analista los "capture" dentro de un caso (eso se diseña en Fase 11).

### 10.3 Fuentes de la Fase 10 (documentadas, no comerciales por ahora)

Se anota la licencia de cada una como dato, para tener la información lista cuando se decida la postura de producción. **Nada aquí afirma uso comercial.**

| Capa | Fuente | Cobertura MX | Licencia / términos (dato) |
|---|---|---|---|
| **Sismos** | USGS Earthquake API | Sí (global) | Dominio público (gobierno de EE. UU.) |
| **Incendios / focos de calor** | NASA FIRMS | Sí (global) | CC0 (dominio público) |
| **Vuelos** | OpenSky Network (ADS-B) | Sí (global) | Gratuito para uso de investigación/no comercial; registro recomendado para más cuota |
| **Barcos** | AISStream.io | Sí (global) | Gratuito; atribución de cortesía solicitada |

Recomendación de orden: **sismos primero** (la más simple y de dominio público), luego incendios, luego vuelos, luego barcos. Cada una, una sub-fase.

### 10.4 Sub-fases

| Sub-fase | Capa | Criterio |
|---|---|---|
| **10.1** | Puerto `LiveLayerPort` + capa de sismos (USGS) | Sismos recientes sobre México, con magnitud y epicentro, encendible/apagable |
| **10.2** | Incendios (NASA FIRMS) | Focos de calor activos sobre México |
| **10.3** | Vuelos (OpenSky) | Aeronaves sobre el espacio aéreo mexicano, actualizándose |
| **10.4** | Barcos (AISStream) | Embarcaciones en costas mexicanas |

Criterio transversal: cada capa respeta el límite de peticiones de su fuente, cachea lo razonable y no tira el rendimiento del globo.

---

## Parte IV — Fase 11: Capas avanzadas y modo cine

**Naturaleza: desarrollo y evaluación.**

### 11.1 Contenido

- **Satélites en órbita:** posiciones vía CelesTrak (TLE/SGP4). Licencia (dato): origen gubernamental de EE. UU., se solicita citación.
- **Clima:** viento y tormentas vía NOAA GFS. Licencia (dato): dominio público.
- **Cámaras públicas:** **pendiente de fuente para México.** God's Eye View trae cámaras de Caltrans (California) y TfL (Londres), que **no cubren México**. Para cámaras mexicanas haría falta gestionar acceso a fuentes de los C5/C4 estatales. Queda documentado como pendiente, sin implementar hasta tener una fuente legítima.
- **Modos visuales:** visión nocturna (filtro verde), térmico/infrarrojo (FLIR) y vista cabina (primera persona). Se implementan como efectos de post-procesado (shaders) sobre el globo. Son polish; no dependen de datos externos.
- **Orquestador:** la pieza que une todo. Permite "capturar" un dato vivo (un sismo, una embarcación) dentro de un caso del muro, convirtiendo un dato efímero en evidencia de investigación con su marca de tiempo y procedencia.

### 11.2 Nota de licencias para producción (dato, no restricción de desarrollo)

Cuando se decida la postura de producción, revisar con calma dos fuentes que en God's Eye View tienen términos especiales: **OpenSky** (su nivel gratuito es para uso no comercial/investigación) y el mapa de cables submarinos de **TeleGeography** (CC BY-NC-SA, no comercial; God's Eye lo trae como dato aparte). Para un sistema institucional conviene que el área legal defina esto. Durante el desarrollo y las pruebas no estorba; solo queda anotado.

---

## Parte V — Riesgos y decisiones abiertas

| Tema | Riesgo | Mitigación |
|---|---|---|
| Rendimiento del grafo sobre el globo | Muchos nodos + 3D puede bajar de 60 fps | Límite de nodos, LOD, cálculo en worker, degradación elegante. Se valida en 9.1 |
| Motor visual | MapLibre podría quedarse corto para los efectos | ADR-0102 con prototipo antes de comprometerse |
| Calidad de la extracción de entidades | El LLM puede inventar o malclasificar personas | Confirmación humana obligatoria; solo lo que dice el texto; estatus legal estricto |
| Datos personales | Herramienta policial que perfila personas | Acceso por caso, auditoría de visualización, estatus legal, minimización; informar al responsable |
| Licencias de capas vivas | Términos distintos por fuente | Documentadas fuente por fuente; postura de producción se define con legal tras las pruebas |
| Cámaras en México | God's Eye no cubre México | Marcado como pendiente; no se implementa sin fuente legítima |
| Enchufe a bases reales | Tentación de conectarlo antes de tiempo | `external_links` queda reservada y vacía; se diseña su integración como fase propia y aparte |
