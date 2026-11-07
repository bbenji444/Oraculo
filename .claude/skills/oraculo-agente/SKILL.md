---
name: oraculo-agente
description: Diseña, construye, prueba y enciende automatizaciones y agentes de IA para Oráculo (el sistema de investigación con el monitor de noticias, PostgreSQL en Proxmox y flujos que hoy viven en n8n), siempre auditables y en español sencillo. Úsalo cuando Benji o el equipo digan "quiero automatizar…", "quiero un agente que…", "manda el reporte por WhatsApp/correo", "un bot que conteste…", "cada día a las X haz…", "migra este flujo de n8n", "/oraculo-agente", o cualquier variación donde algo de Oráculo deba correr solo, mandar algo a alguien o conversar con usuarios. Cubre tres tipos (automatización fija, agente conversacional y agente programado con criterio), elige dónde vive (dentro del módulo, Cloudflare o agentes de Claude), conecta apps con Composio y deja cada ejecución registrada para rastrear y corregir errores como en n8n.
---

# Oráculo · Crear agentes y automatizaciones

Skill para construir cualquier automatización o agente de Oráculo con el mismo método, de modo que el equipo los entienda todos y cada ejecución quede rastreable.

Está inspirada en `crear-agente` de Santiago Muñoz / Horizontes IA (licencia MIT), pero adaptada a Oráculo:
- **Claude** es el cerebro de los agentes nuevos;
- **Composio** pone las conexiones con apps (Gmail, WhatsApp Business, Slack, Drive…);
- la **auditoría es obligatoria**;
- se respetan las reglas del repositorio (`CLAUDE.md`).

---

## Reglas que nunca se rompen

1. **Lee primero `CLAUDE.md`** del repositorio donde vas a trabajar y respétalo: idioma, ramas, commits, permisos y pruebas. Si esta skill y `CLAUDE.md` chocan, manda `CLAUDE.md` y lo dices.
2. **Sin auditoría no hay agente.** Toda ejecución deja su registro (ver `reference/auditoria.md`). Un agente que falla en silencio está mal hecho, aunque «funcione».
3. **Fontanería con código, criterio con IA.** Mandar, reintentar, programar y mover datos es código. La IA solo va donde hace falta leer, resumir, clasificar, decidir o conversar. Nunca pongas a una IA a «decidir» si se manda el reporte de las 07:00.
4. **Nada sale al mundo sin permiso.** Cada envío real (correo, WhatsApp o webhook a terceros) pasa primero por el **modo ensayo** y luego por **un envío de prueba a Benji** con su OK explícito. Lo mismo al encenderlo para la lista completa.
5. **Las llaves nunca se pegan en el chat.** Se guardan en `.env` (que está en `.gitignore`), en `wrangler secret put` o en la conexión de Composio. Si alguien pega una llave, avísale que la cambie.
6. **No inventes APIs.** Antes de usar una herramienta de Composio, un endpoint de Meta, de Cloudflare o de Anthropic, revisa su esquema o documentación vigente. Lo que no puedas confirmar va marcado `# VERIFICAR:` y se avisa.
7. **Información sensible.** Oráculo trabaja investigaciones (por ejemplo, el monitor de la FGR). Antes de mandar algo por un tercero, pregunta qué datos salen y a dónde. Nunca uses canales no oficiales: nada de APIs de WhatsApp «baratas» por QR, como Evolution API o WAHA.
8. **Explica como a alguien que aprende haciendo:** primero que funcione y se vea, luego el porqué. Español claro, con analogías, una decisión a la vez.

---

## Los tres tipos de agente

Pregunta primero cuál es. Cambia todo lo demás.

| Tipo | Qué es | Ejemplos en Oráculo | Lo dispara |
|---|---|---|---|
| **A. Automatización fija** | Pasos siempre iguales, sin decisiones | Mandar el PDF de cada corrida por correo y WhatsApp; avisar a n8n con un webhook; copiar un reporte a Drive | Un evento («terminó la corrida») o un horario |
| **B. Agente conversacional** | Platica con una persona y usa herramientas para responder | Un bot de WhatsApp que contesta «¿qué pasó hoy con la FGR en Jalisco?» consultando el monitor | Un mensaje de alguien |
| **C. Agente programado con criterio** | Corre solo a una hora y usa IA para pensar | Cada lunes, «qué cambió en la semana» a partir de las corridas; detectar un tema que crece | Un horario |

Reglas por tipo:
- **A** no lleva IA en el camino del envío, salvo que el contenido se genere con IA en un paso anterior y guardado.
- **B** siempre pide confirmación humana antes de una acción que sale al mundo (mandar, borrar, publicar). Solo lee lo que la persona puede ver. Ver `reference/conversacional.md`.
- **C** define antes qué es un buen resultado (una rúbrica corta) y guarda lo que produjo para revisarlo.

---

## Dónde vive el agente (su «casa»)

Detalle en `reference/donde-vive.md`. Resumen:

1. **Dentro del módulo** (Python, FastAPI y Celery, como el monitor) cuando los datos ya viven ahí y el disparador es algo del módulo, como «terminó la corrida». **Es la opción por defecto para Oráculo**: misma base, mismos respaldos y mismas pruebas.
2. **Cloudflare Workers** (con Cron Triggers, Workflows y D1) para agentes independientes que no necesitan la base de Oráculo o que deben recibir mensajes desde internet sin exponer el servidor de Proxmox.
3. **Agentes de Claude programados** (Managed Agents, en beta) para el tipo C cuando el agente necesita una computadora propia para trabajar: leer archivos o correr código.

Si dudas, elige 1 y explica por qué.

---

## Protocolo en 8 fases

Avanza una fase a la vez. Al terminar cada una, di en una línea qué quedó listo.

### Fase 0 · Contexto
- Lee `CLAUDE.md`, el README del módulo y, si existe, `docs/PLAN_AUTOMATIZACION.md` y `agentes/CATALOGO.md`.
- Revisa si ya hay una pieza que sirva: un canal de envío, una tabla de auditoría o un conector de Composio ya autorizado. **Reutiliza antes de crear.**

### Fase 1 · Entrevista (una pregunta a la vez)
1. ¿Qué quieres que pase? Pide un ejemplo concreto.
2. ¿Qué lo dispara: un horario, un evento de Oráculo o un mensaje de alguien?
3. ¿De dónde salen los datos: una tabla de Oráculo, un PDF, una API o internet?
4. ¿A dónde va el resultado y a quién: correo, WhatsApp, webhook, Drive o Slack?
5. ¿Qué datos sensibles van ahí?
6. ¿Qué pasa si falla: reintento, aviso a quién y en cuánto tiempo?
7. ¿Cuánto puede costar al mes, como máximo?

### Fase 2 · Ficha del agente
- Llena `plantillas/ficha-agente.md`: tipo, casa, disparador, pasos, conectores, datos sensibles, auditoría, costo estimado y riesgos.
- Muéstrala en lenguaje sencillo, con un diagrama corto, y **espera la aprobación**.
- La ficha aprobada se guarda en `agentes/<nombre>/FICHA.md` del repositorio.

### Fase 3 · Conectores y cuentas
- Para cada app, primero busca la herramienta en Composio (`COMPOSIO_SEARCH_TOOLS`) y revisa su esquema completo. Si no hay conexión activa, inicia la conexión y que Benji la autorice. Detalles y trampas en `reference/composio.md`.
- Para lo que Composio no cubra, usa la API oficial con un adaptador propio.
- Lista lo que Benji debe hacer fuera del chat (por ejemplo, dar de alta la plantilla de WhatsApp en Meta) con su tiempo estimado.

### Fase 4 · Construir
- Rama de trabajo según `CLAUDE.md`.
- **Arquitectura hexagonal:**
  - un **puerto** por tipo de salida (por ejemplo, `DeliveryChannelPort`);
  - un **adaptador** por canal: Composio-Gmail, Composio-WhatsApp, webhook…;
  - la lógica en casos de uso;
  - las reglas (estados, reintentos) en el dominio.
- La **auditoría** se crea en la misma migración que las tablas del agente (`reference/auditoria.md`).
- Cada paso tiene **tiempo límite, reintentos con espera creciente e idempotencia**: repetirlo no duplica el envío.
- **Modo ensayo** (`dry_run`): recorre todo, guarda la guía y **no manda nada**. Es lo primero que se prueba.
- Pasos con IA: Claude. Usa la skill `claude-api` para el código y elige el modelo según el trabajo. Guarda en la auditoría los tokens y el costo de cada llamada.
- Pruebas con respuestas grabadas: **nunca llaman a internet ni mandan nada real**.

### Fase 5 · Probar en local
1. Pruebas automáticas, lint y tipos en verde.
2. **Ensayo** con datos reales: muestra 5 guías tal como quedaron y lo que se habría mandado.
3. **Un envío real solo a Benji**, con su OK: muestra el resultado, el número de mensaje del proveedor y la guía en estado «enviado» o «entregado».
4. **Provoca una falla a propósito** (por ejemplo, un destino inválido) y muestra que quedó registrada, se reintentó y avisó.

### Fase 6 · Encender
- Con el OK de Benji, prende el disparador real (el horario o el evento) para la lista acordada.
- Verifica la primera ejecución real completa en la auditoría.

### Fase 7 · Documentar
- `agentes/<nombre>/README.md`: qué hace, cómo se prende y se apaga, y cómo se prueba.
- `agentes/<nombre>/MANUAL_DE_FALLAS.md`, desde `plantillas/manual-de-fallas.md`: qué hacer cuando falla cada paso.
- Un ADR si hubo una decisión de arquitectura, más el CHANGELOG y `CLAUDE.md` §9 si hay comandos nuevos.

### Fase 8 · Catálogo
- Agrega una línea en `agentes/CATALOGO.md`: nombre, tipo, casa, disparador, dueño, estado y dónde ver su auditoría. Es la lista que reemplaza a la pantalla de flujos de n8n.

---

## Migrar un flujo de n8n

Sigue `reference/migrar-n8n.md`:
1. Exportar el JSON del flujo.
2. Convertir cada nodo en un paso con su registro de auditoría.
3. Mantener n8n recibiendo un webhook firmado mientras se compara.
4. Apagar el flujo viejo solo cuando el nuevo lleve una semana igual o mejor.

---

## Cómo hablarle a Benji

- Primero el resultado visible, luego la explicación.
- Analogías. Por ejemplo, la guía de envío de una paquetería = la auditoría; el llavero = Composio.
- Traduce siempre:

| Término | Dilo así |
|---|---|
| webhook | aviso automático por internet |
| idempotencia | si se repite, no se duplica |
| `dry_run` | modo ensayo |
| cron | horario automático |
| OAuth | autorizar la conexión con tu cuenta |
| plantilla de WhatsApp | mensaje con huecos que Meta aprueba antes |

- Cuando haya que decidir, da tu recomendación y su porqué. No le pidas que elija entre muchas opciones.

---

## Archivos de la skill

- `reference/donde-vive.md`: cómo elegir la casa del agente.
- `reference/auditoria.md`: el estándar de registro (tablas, estados, logs y pantalla).
- `reference/composio.md`: cómo usar Composio, con sus trampas conocidas (WhatsApp y Gmail).
- `reference/conversacional.md`: el patrón de agente que conversa, con confirmación humana.
- `reference/migrar-n8n.md`: la receta para pasar flujos de n8n a código.
- `plantillas/ficha-agente.md`: la ficha que se aprueba antes de construir.
- `plantillas/manual-de-fallas.md`: qué hacer cuando algo falla.
