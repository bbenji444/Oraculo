# Plan — Monitor automatizado FGR (fase activa)

Versión 1.0 · Octubre 2026 · Responsable: Benji

Esta es la fase prioritaria actual del proyecto. El "muro" (9.6–9.7) y las capas vivas (Fases 10–11) quedan en pausa. Las reglas de trabajo de `CLAUDE.md` siguen vigentes: plan antes de construir, ADR por decisión, pruebas, commits en español, nada destructivo sin respaldo y aprobación.

---

## 0. Qué pidió Benji (en sus palabras)

Estos son sus mensajes tal como los dio, para que entiendas la intención completa antes de leer el plan. El plan de abajo es la traducción técnica de esto; si algo del plan se aleja de la intención, gana la intención y se consulta con Benji.

> **(1)** "Ya voy en una etapa muy avanzada del proyecto, solo que ahora necesito darle un giro un poco distinto. Ya hace búsquedas, ya las geolocaliza, ya está la sección de casos. Ahora necesito un reporte mucho más dinámico en cuanto al PDF. También necesito que me catalogue las noticias de acuerdo al tipo de noticia que es. Y muy importante: vamos a priorizar las búsquedas automatizadas para la Fiscalía General de la República (FGR). Cada intervalo de tiempo el sistema hace una búsqueda, genera un reporte. La búsqueda debe ser de todo México y fraccionarnos por estados donde hay más noticias de la fiscalía, que saque el listado, lo catalogue por tipo de noticia (la IA fracciona en conceptos, y si hay alguno distinto, a 'otros'), me dé un resumen general, me geolocalice en el PDF los puntos con más noticias, con gráficas, muy visual y dinámico, que yo pueda seleccionar y contraer información para que no sea un desorden visual."

> **(2)** "Las noticias que cuentan como 'de la FGR' son donde la FGR actúa (detenciones, cateos, órdenes, carpetas). El reporte dinámico lo quiero como un PDF interactivo, con división de noticias por estado, muy visual, y las noticias con flecha de despliegue tipo chevron (▸ / ▼), con gráficas y muy formal."

> **(3)** "Prefiero que los horarios de los reportes sean fijos y automatizados y que TODO se vaya guardando en nuestra base de datos de Postgres. Este proyecto lo vamos a migrar después a una máquina virtual de Proxmox donde trabajamos todo el sistema; ese servidor está funcionando las 24 horas. El PDF que comparto es de uso interno y es solo para diseño y homologación; lo único que le gustó a mis jefes fue la representación visual de México con porcentajes, me pidieron más cosas así y más dinámicas. Muy importante: la representación con líneas del tiempo; que exista la manera de llevar el orden de fecha y hora de cada noticia para un orden cronológico, visualmente atractivo, tanto en el monitor como en el PDF. Ya integramos Google News RSS y un nuevo motor de búsqueda gratuito creado por nosotros."

> **(4)** "Los reportes automatizados mejor que sean a las 7 am, 3 pm y 11 pm. Quita lo del Mojibake, aparece tanto en el sistema como en los reportes. De momento haz que funcione; después, con base en un análisis de resultados, catalogamos las categorías más frecuentes con colores y símbolos, y el resto a 'otros'. El PDF lo dejamos al final, cuando el sistema esté al 100%. Primero va 100% enfocado en la FGR y sus afines: que se dé el reporte, se guarden las noticias individuales en la base, el reporte, y después, si queremos, automatizamos los envíos (por ejemplo a WhatsApp), pero eso hasta el final. Borra todos los conceptos actuales y que lo nuevo se relacione con lo que ya tenemos. Pon mis prompts en el plan."

> **(5)** "Integra ya todo con BrowserWork de una vez, que nosotros podamos activar y desactivar mediante switches qué queremos buscar en cada búsqueda no automatizada, por ejemplo SearchApi, o 'Google 2' si hablamos de BrowserWork, etc."

**Tarea para Claude Code antes de planear:** lee esta sección y el plan completo, y dime en no más de 15 líneas cómo lo entendiste, qué encaja con lo ya construido y qué de mi plan cambiarías o no te convence. Ahí ajustamos antes de escribir código.

---

## 1. Qué se construye

Un monitor que, **solo con lo que ya existe** (búsqueda, geolocalización, fuentes, enriquecimiento con IA), hace esto:

1. **Corre automáticamente** a las 07:00, 15:00 y 23:00 (hora CDMX), en el servidor 24/7, sin que nadie lo dispare.
2. Busca noticias **donde actúa la FGR** en **todo México**, fraccionando por estado.
3. **Clasifica** cada noticia por tipo (y lo que no encaje, a "Otros").
4. **Guarda todo en PostgreSQL:** cada corrida, cada noticia individual, su clasificación y el reporte generado.
5. Ordena las noticias en una **línea de tiempo cronológica**, visible en el monitor.
6. Permite, en las **búsquedas manuales**, elegir con **switches** qué fuentes usar (SearchApi, Google News RSS, índice local, BrowserWork→Bing, BrowserWork→"Google opción 2", etc.).

El **PDF rediseñado** y los **envíos automáticos (WhatsApp)** se construyen **al final**, cuando lo anterior funcione al 100%. Este plan los documenta pero no los implementa todavía.

---

## 2. Decisiones ya tomadas (no volver a preguntar)

- **Horarios:** 07:00, 15:00, 23:00 (CDMX). Esto **reemplaza** la idea previa de "cada 6 horas".
- **Relevancia FGR:** cuentan las noticias donde actúa la **FGR federal** (detenciones, cateos, órdenes, carpetas, sentencias, decomisos federales). **No** cuentan las fiscalías **estatales** (ver sección 4.5).
- **Clasificación:** la IA asigna un tipo de una lista provisional; lo que no encaje va a "Otros". Los colores y símbolos definitivos se deciden **después**, con datos reales. Por ahora, que funcione.
- **Enfoque:** 100% FGR primero; la arquitectura queda lista para generalizar a otros temas luego.
- **Persistencia:** todo en PostgreSQL. Las notas individuales se guardan, no solo el reporte.
- **BrowserWork:** se integra **ahora**, como fuente con switches.
- **Conceptos actuales:** ver sección 4.8 (se **desactivan**, no se borran en seco, salvo respaldo previo).
- **PDF y WhatsApp:** al final.

---

## 3. Pre-requisitos antes de construir

**3.1 Seguridad — rotar la credencial del servidor del jefe.** La contraseña del usuario `apis` de BrowserWork (192.168.0.37) quedó expuesta en un chat. Antes de integrar BrowserWork, esa contraseña debe cambiarse, y la nueva va solo en `.env`, nunca en el código ni en un chat. Claude Code debe detenerse y pedir confirmación de que ya se rotó antes de guardar cualquier credencial de BrowserWork.

**3.2 Migración a Proxmox.** El programador automático y el recolector del índice local **deben** correr en la VM de Proxmox 24/7, no en la PC de Benji. Hoy el índice local se queda con huecos cuando la PC se apaga (el 22/10 solo entraron 769 notas). Mover la recolección al servidor resuelve ese hueco. La migración se trata como una sub-fase con su checklist, no como un "copiar y pegar".

---

## 4. Arquitectura

Todo se apoya en la arquitectura hexagonal existente: cada fuente es un proveedor detrás de un puerto. Lo nuevo encaja sin romper lo anterior.

### 4.1 Selección de fuentes con switches

- Se introduce el concepto de **perfil de fuentes**: qué proveedores/motores están activos en una búsqueda.
- **Búsqueda manual:** la UI muestra switches, uno por fuente disponible: SearchApi (Google News), Google News RSS, Índice local, BrowserWork→Bing, BrowserWork→"Google opción 2", etc. El analista enciende las que quiera.
- **Búsqueda automática FGR:** usa un **perfil fijo** definido en configuración (no switches en pantalla), para que el costo y la cobertura sean constantes entre corridas.
- Cada búsqueda guarda **qué fuentes se usaron** y **de qué fuente vino cada nota** (esto último ya se guarda en la base; falta mostrarlo).

### 4.2 BrowserWork como proveedor nuevo

- Se crea un adaptador `BrowserWorkProvider` que habla con la API de BrowserWork (FastAPI, 192.168.0.37:8787) y normaliza los resultados al contrato `RawArticle`, como cualquier otro proveedor.
- Cada "motor" de BrowserWork (Bing, "Google opción 2", etc.) es un sub-proveedor seleccionable por switch.
- **Criterios ya acordados que se respetan:**
  - Para Google News se usa el RSS, **no** BrowserWork.
  - Yahoo y DuckDuckGo repiten mucho a Bing; **se empieza solo con Bing** y se mide cuánto aporta antes de sumar otros.
  - **No** se porta el disfraz de navegador (User-Agent ni Client Hints falsos).
  - Entra con su ADR propio y requiere aprobación para instalar Zendriver si hiciera falta.
- Timeout, reintentos con backoff y registro en `provider_queries`, igual que los demás proveedores. Si BrowserWork no responde, la búsqueda no se cae: queda `partial`.

### 4.3 Programador automático

- Tareas programadas (Celery beat o APScheduler; decidir en ADR) a las 07:00, 15:00 y 23:00 CDMX, **en la VM de Proxmox**.
- Cada corrida: busca FGR en los 32 estados con el perfil fijo de fuentes, clasifica, deduplica contra corridas anteriores, geolocaliza, guarda y genera el registro de reporte.
- **Ventana:** cada corrida cubre las notas nuevas desde la corrida anterior. Deduplicación global para no reclasificar ni volver a cobrar lo ya visto. (Ajustable; confirmar con Benji al llegar.)
- **Costo:** 32 estados × 3 corridas = 96 consultas/día. Para no dispararse, el perfil automático se apoya en las fuentes gratuitas (índice local, RSS, BrowserWork→Bing) y usa SearchApi de forma medida. Se muestra el costo estimado por corrida y hay tope de presupuesto.

### 4.4 Clasificación por tipo de noticia

- Se agrega a la pasada del LLM que ya enriquece cada nota un campo de **categoría**, elegido de una **lista configurable en base de datos** (no quemada en código). "Otros" es el destino por defecto.
- Lista provisional de arranque (se afina después con datos reales): Narcotráfico y delitos contra la salud, Delincuencia organizada, Secuestro, Desaparición de personas, Homicidio, Armas y explosivos, Huachicol y delitos contra hidrocarburos, Lavado de dinero y delitos fiscales, Corrupción, Trata de personas, Extorsión, Ciberdelitos, Delitos electorales, y **Otros**.
- Se guarda también la **etiqueta cruda** que propone la IA, para que el análisis posterior (frecuencias) permita definir las categorías finales con sus colores y símbolos.
- Colores/símbolos definitivos: **no ahora**.

### 4.5 Relevancia FGR (federal vs estatal)

- Regla estricta en el prompt: es relevante solo si actúa la **FGR federal** (FGR, Ministerio Público Federal, Agencia de Investigación Criminal, fiscalías especializadas federales, o un hecho puesto "a disposición de la FGR").
- **No** es relevante si solo actúa una **fiscalía estatal** ("Fiscalía General del Estado", "fiscalía de Jalisco", etc.). Esas notas se marcan como no relevantes o se separan.
- Se valida con 5 ejemplos reales del reporte actual antes de la primera corrida completa (por ejemplo, la nota de la fosa común de SLP, que es fiscalía estatal, debe quedar fuera; los cateos de la FGR en Nuevo León, dentro).

### 4.6 Línea de tiempo cronológica (pieza central)

- Cada noticia ya trae fecha y hora de publicación y, cuando la IA la detecta, la **fecha del hecho**. Se asegura que ambos campos se guarden y se indexen.
- **En el monitor:** una vista de línea de tiempo que ordena las noticias por fecha y hora, con los picos del día marcados, filtrable por estado y por categoría, sincronizada con el mapa.
- **En el reporte (al final):** la misma línea de tiempo como gráfica.
- Diferencia clara entre "cuándo se publicó" y "cuándo ocurrió el hecho"; para el orden cronológico de investigación manda la fecha del hecho cuando existe.

### 4.7 Persistencia en PostgreSQL

Se guarda todo, con índices en las columnas de filtro, orden y paginación (en la misma migración que las crea):
- **`scheduled_runs`:** cada corrida automática (hora, perfil de fuentes, ventana, estados cubiertos, conteos, créditos usados, estado).
- **`articles`** (ya existe): se amplía con `category` y `category_raw`.
- **`run_articles`:** qué notas entraron en cada corrida.
- **`reports`:** cada reporte generado (corrida asociada, resumen, agregados, ruta del archivo cuando exista el PDF).
- Nada se borra por corrida; la limpieza por retención sigue las reglas que ya tiene el índice local.

### 4.8 Conceptos actuales: desactivar, no borrar

- Benji pidió borrar todos los conceptos. El camino seguro, que logra lo mismo (que solo quede la FGR visible), es **desactivarlos con el borrado lógico que el sistema ya tiene**, dejando activo únicamente el concepto de la FGR.
- Motivo: los casos, búsquedas y reportes ya generados están ligados a esos conceptos; borrarlos en seco puede dejar historial huérfano, y el rumbo ya cambió una vez.
- Si Benji confirma que quiere **borrado físico total**, Claude Code primero hace un **respaldo de la base**, revisa qué referencias se romperían, lo reporta, y solo entonces borra. Nunca un `DELETE` masivo sin respaldo.

### 4.9 Corrección del Mojibake

- El problema: títulos como `"Liberen a JÃ¡uregui"` y `ChihuahuaðŸŽ¦` son texto UTF-8 leído con el encoding equivocado (el mismo tipo de bug que los DBF).
- **Dos frentes:**
  1. **Entrada:** detectar y normalizar el encoding al ingerir de cada fuente (RSS, BrowserWork, SearchApi), de modo que ya no entren notas corruptas.
  2. **Histórico:** una pasada de reparación por lotes (con CHECKPOINT, cursor por id) que arregle las notas ya guardadas con mojibake, con 5 ejemplos de muestra antes de correrla completa.
- Aplica al monitor **y** a los reportes, porque ambos leen de la misma base.

---

## 5. Sub-fases

Cada una cierra con pruebas, commits y su criterio verificable. No se avanza sin aprobación.

| Sub-fase | Entregable | Criterio de aceptación |
|---|---|---|
| **F12.0** | Pre-requisitos: rotar credencial `apis`, confirmar acceso a BrowserWork, decidir programador (ADR) | Credencial rotada y en `.env`; BrowserWork responde a una llamada de prueba |
| **F12.1** | Corrección de Mojibake (entrada + histórico) | 5 ejemplos reales sin corrupción; pasada histórica aplicada; títulos limpios en monitor |
| **F12.2** | Switches de fuentes en búsqueda manual + mostrar fuente de cada nota | El analista enciende/apaga fuentes; cada nota muestra de dónde vino |
| **F12.3** | Proveedor BrowserWork (solo Bing primero) con su ADR | Una búsqueda manual con BrowserWork→Bing trae notas reales normalizadas |
| **F12.4** | Clasificación por categoría (+ Otros) sobre la pasada del LLM | 5 ejemplos reales clasificados, con `category` y `category_raw` guardados |
| **F12.5** | Relevancia FGR federal vs estatal | Los 5 casos de prueba de 4.5 se clasifican bien |
| **F12.6** | Conceptos: dejar activo solo FGR (desactivar el resto) | Solo FGR visible; historial intacto |
| **F12.7** | Línea de tiempo cronológica en el monitor | Vista ordenada por fecha/hora, filtrable por estado y categoría, sincronizada con el mapa |
| **F12.8** | Programador automático (07:00/15:00/23:00) + persistencia completa | Una corrida automática real guarda corrida, notas y reporte en Postgres |
| **F12.9** | Migración a la VM de Proxmox (app + recolector + programador) | El sistema corre en la VM 24/7; el índice local ya no depende de la PC de Benji |
| **F12.10** | (Al final) Reporte PDF/HTML rediseñado | Ver sección 6 |
| **F12.11** | (Al final) Envío automático (WhatsApp/correo) | A definir con Benji al llegar |

---

## 6. El reporte (se construye al final, F12.10)

Documentado ahora para que la arquitectura no lo impida. Se arma cuando el sistema funcione al 100%.

- **Lo que ya gustó y se conserva:** el mapa de México con porcentajes por estado, las barras por estado y por medio.
- **Lo nuevo que pidió el jefe ("más cosas así, más dinámicas"):**
  - mapa con cada estado coloreado por su categoría dominante;
  - barras apiladas por categoría;
  - la línea de tiempo cronológica como gráfica;
  - tarjetas de resumen por categoría.
- **Cuerpo dinámico con chevrons:** organización Estado ▸ Categoría ▸ Noticias, con árbol de marcadores navegable (funciona en cualquier lector) y, si en la FGR usan Adobe Reader, secciones desplegables dentro de la página (confirmar lector).
- **Lenguaje visual homologado** con el reporte de persona "Oráculo 2.0": portada de red de nodos, banda de confidencialidad, insignias de confianza. Para esto, al llegar a F12.10, pedir a Benji los PDFs de muestra otra vez.
- **Legal:** el reporte guarda resumen propio + link a la fuente, nunca el texto completo del artículo (ya es la práctica actual).

---

## 7. Riesgos y decisiones abiertas

| Tema | Riesgo | Mitigación |
|---|---|---|
| Credencial expuesta | Acceso al servidor del jefe comprometido | Rotarla en F12.0 antes de tocar BrowserWork |
| Costo de SearchApi | 96 consultas/día pueden acumular | Perfil automático con fuentes gratis; SearchApi medido; tope de presupuesto |
| Dependencia de la PC | El índice local se queda con huecos | Migrar recolector y programador a Proxmox (F12.9) |
| Fiscalía estatal vs FGR | Ensuciar el reporte con notas que no son FGR | Regla estricta + 5 casos de prueba |
| Borrado de conceptos | Historial huérfano | Desactivar, no borrar; respaldo si se insiste en físico |
| BrowserWork inestable | Un Chrome real puede fallar o ser lento | Timeout, degradación a `partial`, empezar solo con Bing |
| Migración | Romper algo al mover a Proxmox | Sub-fase con checklist y verificación |

---

## 8. Prompt para arrancar (para pegar en Claude Code)

```
Vamos a construir la fase de monitor automatizado FGR. El plan está en docs/PLAN_MONITOR_FGR.md.

1. Lee el plan completo, incluida la sección 0 (los mensajes de Benji en sus palabras) y CLAUDE.md. La sección 0 es la intención; si el plan se aleja de ella, gana la intención.
2. En no más de 15 líneas, en español, dime: cómo entendiste lo que se quiere, cómo encaja con lo ya construido (fuentes actuales, enriquecimiento con IA, geolocalización), y qué de mi plan cambiarías o no te convence. Si ves algo que choca con lo existente, dímelo ahora.
3. Empezamos por F12.0 (pre-requisitos). Lo primero y bloqueante: confírmame que la credencial del usuario apis de BrowserWork ya se rotó; sin eso no guardes ninguna credencial. Luego propón el programador (Celery beat vs APScheduler) con un ADR.
4. Preséntame el plan de F12.0 con archivos, commits con su mensaje exacto (CLAUDE.md 4.2), riesgos y cómo verificar. Espera mi aprobación antes de escribir código.
5. Reglas de esta fase que no debes saltarte:
   - Nada destructivo sin respaldo: los conceptos se DESACTIVAN, no se borran (sección 4.8). Si pido borrado físico, respaldas primero.
   - Toda columna de filtro/orden/paginación lleva índice en su migración.
   - Las credenciales van en .env, nunca en código ni en el chat.
   - Antes de la primera corrida automática real y antes de clasificar en masa, muéstrame 5 ejemplos reales y espera confirmación.
   - BrowserWork entra solo con Bing primero; no se porta el disfraz de navegador.
   - El PDF y los envíos (WhatsApp) son hasta el final; no los empieces ahora.
6. Trabaja en ramas feat/f12-N-<descripcion>, una sub-fase por sesión. No hagas merge ni tag sin mi aprobación.
```

---

## 9. Ajustes acordados el 24/10/2026

Las secciones 0 a 8 son el plan original de Benji y no se reescriben. Esta sección registra lo que se ajustó en la conversación con Claude Code antes de escribir código. **Donde choque con lo anterior, manda esta sección.**

### 9.1 Decisiones

| Tema | Plan original | Ajuste acordado | Por qué |
|---|---|---|---|
| Fraccionar por estado | 32 consultas por corrida (96 al día) | **Una búsqueda nacional por corrida** (3 al día). La geolocalización que ya existe reparte las notas por estado. | Menos consultas y menos repetidas. Benji: «me gusta más y gasta menos». |
| Fuentes de la corrida automática | Fuentes gratis más SearchApi medido | **Solo Google News RSS e índice local**: 0 créditos y sin captchas | El RSS ya está autorizado (ADR-0021) y da hasta ~100 notas por consulta. Pagar SearchApi encima sería pagar sobre todo por repetidas. |
| SearchApi | Parte del perfil automático | **Switch en la búsqueda manual.** Una medición única RSS vs SearchApi (~3 créditos, con permiso) decide si se deja encendido por defecto. | Misma fuente (Google Noticias); SearchApi da el link del medio y un fragmento, el RSS da más notas gratis. |
| BrowserWork | Solo Bing al inicio | **Bing y Google 2 como switches**, solo en la búsqueda manual al principio | Google 2 pasa de página con clic y casi no pide captchas, pero puede pedir alguno y entonces espera a una persona hasta 10 min. Entra a las corridas automáticas solo si una semana de mediciones muestra que no se bloquea. |
| Credencial de `apis` (3.1) | Rotarla antes de integrar | **No se rota por ahora** (decisión de Benji) | La API de BrowserWork (`:8787`) no pide llave; la integración nunca usa ni guarda la contraseña de SSH. Queda como riesgo aceptado en el ADR-0023. |
| Programador (4.3) | Celery beat o APScheduler | **Celery beat** (ADR-0022) | Ya corre la ingesta y la purga con `crontab`; no suma procesos ni dependencias. |
| `category_raw` (4.4) | Campo nuevo | Sale del `event_type` que la IA ya devuelve | Evita pedirle a la IA dos veces lo mismo. |
| Orden de sub-fases | Proxmox (F12.9) después de corridas | Se mantiene: **corridas (F12.8) antes de Proxmox (F12.9)** | La PC de Benji está siempre prendida. |
| Diseño | No especificado | **Homologar con OSINT Oráculo**: fondo oscuro, cian `#00d2ff`, títulos en Orbitron y texto en Roboto, fuentes autoalojadas. Sub-fase F12.7a antes de la línea de tiempo. | Benji: que tipografías y efectos estén homologados con el resto de Oráculo. |
| Duplicados | No especificado | **Sub-fase nueva F12.1b** (abajo) | Benji: reducir al máximo lo repetido sin descartar información importante. |
| Reporte (F12.10) | Sección 6 | **Antes de diseñarlo, preguntarle a Benji** por los PDFs corporativos de Oráculo y las indicaciones que dio en otro chat | Hay material que esta conversación todavía no tiene. |

### 9.2 Duplicados en tres niveles (F12.1b)

Medición del 24/10/2026:
- `articles` tiene 1,450 notas (2.7 MB) y 7 grupos con el título repetido. Los 7 son la misma nota guardada dos veces: una con el link de `news.google.com` (RSS) y otra con el del medio. Pasa porque hoy solo se compara dentro de una misma búsqueda, no contra lo ya guardado.
- El peso de la base está en `news_index`: 77,195 notas y 368 MB, con purga a 90 días.

Niveles:
1. **Misma URL canónica:** ya existe (`app/domain/dedupe.py`).
2. **Misma nota con otro link, entre búsquedas y corridas:** antes de guardar, se compara título y fecha contra `articles`. Si coincide, se reutiliza la nota, se le suma el proveedor y se prefiere el link del medio sobre el de Google. No se le vuelve a pagar a la IA.
3. **Mismo hecho en varios medios:** no se borra nada. Las notas se agrupan en una «historia»: el monitor y el reporte muestran una tarjeta con «+N medios», y cada link sigue disponible. El umbral se decide con 5 ejemplos reales.

Va después del Mojibake (F12.1) porque los títulos corruptos impiden reconocer que dos notas son la misma.

### 9.3 Sub-fases ajustadas

| Sub-fase | Entregable |
|---|---|
| F12.0 | Este plan en `docs/`, ADR-0022 (programador) y ADR-0023 (perfiles de fuentes y BrowserWork) |
| F12.1 | Mojibake (entrada + histórico) |
| **F12.1b** | **Duplicados en tres niveles** (ADR propio, 5 ejemplos reales antes de aplicar) |
| F12.2 | Switches de fuentes, la fuente de cada nota y la medición RSS vs SearchApi |
| F12.3 | BrowserWork: Bing y Google 2, solo en manual |
| F12.4 | Categorías + «Otros» |
| F12.5 | FGR federal vs estatal |
| F12.6 | Desactivar los conceptos, dejar solo FGR |
| **F12.7a** | **Tema Oráculo** (colores y tipografías de OSINT) |
| F12.7 | Línea de tiempo en el monitor |
| F12.8 | Corridas automáticas 07:00 / 15:00 / 23:00 + persistencia |
| F12.9 | Migración a la VM de Proxmox |
| F12.10 | Reporte rediseñado (primero preguntarle a Benji) |
| F12.11 | Envíos automáticos (WhatsApp / correo) |
