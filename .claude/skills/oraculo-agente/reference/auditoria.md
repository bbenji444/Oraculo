# Estándar de auditoría (obligatorio)

**Objetivo:** que cualquier persona del equipo pueda responder, sin leer código:
- ¿Corrió? ¿Cuándo?
- ¿Qué hizo en cada paso?
- ¿A quién le mandó qué? ¿Llegó?
- Si falló, ¿en qué paso y por qué?
- ¿Cuánto costó?

Es lo que hoy da n8n al abrir una ejecución, pero en nuestra base, con respaldo y con pruebas.

## Las tres tablas

En PostgreSQL, si vive dentro de un módulo; en D1, si vive en Cloudflare. Mismos nombres.

### `agent_runs`: una fila por ejecución
| Columna | Para qué |
|---|---|
| `id` (uuid) | Número de rastreo de la ejecución |
| `agent` (text, con índice) | Nombre del agente, igual que en el catálogo |
| `trigger` (text) | `schedule`, `event`, `message` o `manual` |
| `trigger_ref` (text, con índice) | A qué responde. Por ejemplo, el `search_id` de la corrida |
| `status` (text, con índice) | `running`, `succeeded`, `partial` o `failed` |
| `dry_run` (bool) | Si fue un ensayo |
| `started_at`, `finished_at` (timestamptz) | Duración |
| `cost_usd` (numeric) | IA más mensajes |
| `error_summary` (text) | En español, para humanos |

### `agent_steps`: una fila por paso de cada ejecución
| Columna | Para qué |
|---|---|
| `id`, `run_id` (con índice) | A qué ejecución pertenece |
| `seq` (int) | Orden del paso |
| `name` (text) | Por ejemplo, `generar_resumen` o `enviar_correo:benji@…` |
| `status` (text) | `pending`, `running`, `succeeded`, `retrying`, `failed` o `skipped` |
| `attempts` (int) | Cuántas veces se intentó |
| `input_summary`, `output_summary` (jsonb) | Lo esencial, **sin secretos y sin el documento completo** |
| `provider_ref` (text) | El número que devolvió el proveedor (id del mensaje de WhatsApp, Message-ID del correo, id de la ejecución de Composio) |
| `error` (text) | En español |
| `started_at`, `finished_at` (timestamptz) | |

### `deliveries`: solo si el agente manda cosas a personas
Es la «guía de envío»: una por destino y por ejecución.
| Columna | Para qué |
|---|---|
| `id`, `run_id` | |
| `channel` (text) | `email`, `whatsapp`, `webhook`, `slack`… |
| `destination` (text) | A quién, enmascarado en la pantalla (`+52 55 •••• 1234`) |
| `idempotency_key` (text, **único**) | Por ejemplo, `search_id + canal + destino`. Así nunca se manda dos veces |
| `status` (text, con índice) | `pending`, `sent`, `delivered`, `read` o `failed` |
| `attempts`, `last_error`, `provider_ref`, `sent_at`, `delivered_at` | |

## Reglas

- Los índices van **en la misma migración** que crea la columna (CLAUDE.md §6.3). Las listas se paginan por cursor, nunca con `OFFSET`.
- **Reintentos:** esperas de 1, 5 y 30 minutos. Al cuarto fallo, `failed` y aviso al administrador. Nunca un reintento infinito.
- **Logs JSON** con `run_id` y el `trigger_ref` en cada línea, para buscar en los logs desde la tabla y viceversa.
- **Nada sensible** en la auditoría: ni llaves, ni el PDF, ni el texto completo de las notas. Solo resúmenes y referencias.
- **Pantalla mínima:**
  - la lista de ejecuciones, con filtros por agente, estado y fecha;
  - el detalle con sus pasos y envíos;
  - el botón **Reintentar**, que crea un intento nuevo y no borra el anterior.
- **Alerta:** si una ejecución termina en `failed`, o si un horario no corrió cuando debía, se avisa al administrador por un canal distinto al que falló.
- La auditoría **también se prueba**: hay pruebas de que un fallo deja su registro y de que repetir no duplica.
