# Ficha del agente: <nombre-en-kebab-case>

- **Estado:** Borrador | Aprobada (fecha, por quién) | Encendida | Apagada
- **Dueño:** <persona responsable>
- **Tipo:** A (automatización fija) | B (conversacional) | C (programado con criterio)
- **Casa:** dentro del módulo `<módulo>` | Cloudflare | agente de Claude, y por qué

## Qué hace (en una frase)
<Ejemplo: «Cuando termina cada corrida del monitor FGR, manda el PDF por correo y WhatsApp a la lista de destinatarios».>

## Disparador
<Horario (con zona horaria America/Mexico_City), evento de Oráculo o mensaje entrante.>

## Pasos
| # | Paso | Herramienta | Si falla |
|---|---|---|---|
| 1 | | | |
| 2 | | | |

## Entradas y salidas
- **Entra:** <tablas, archivos o APIs>
- **Sale a:** <canales y destinatarios, o de dónde se toma la lista>

## Conectores
| App | Cómo | ¿Conexión lista? | Pendiente fuera del chat |
|---|---|---|---|
| Gmail | Composio `GMAIL_SEND_EMAIL` | sí / no | |
| WhatsApp | Composio o Cloud API | sí / no | Plantilla aprobada por Meta |

## Datos sensibles
<Qué sale de Oráculo, a qué terceros pasa y por qué es aceptable.>

## Auditoría
- Tablas: `agent_runs`, `agent_steps` y `deliveries` (si envía).
- Dónde se ve: <pantalla o consulta>.
- Alerta de falla: <a quién y por qué canal>.

## Costo estimado al mes
<IA: tokens × precio. Mensajes: cantidad × tarifa. Total y tope máximo.>

## Riesgos
| Riesgo | Qué hacemos |
|---|---|

## Cómo se prueba
1. Pruebas automáticas con respuestas grabadas.
2. Ensayo (`dry_run`) con datos reales: 5 ejemplos.
3. Un envío real solo a Benji.
4. Una falla provocada a propósito.
