# Composio en Oráculo

**Qué es:** un **llavero de conexiones**. Benji autoriza una vez su Gmail, su WhatsApp Business o Slack, y luego Claude o el código pueden usar esas apps sin manejar contraseñas ni OAuth a mano. Tiene más de 500 apps.

**Qué no es:** no tiene reloj propio ni guarda nuestra auditoría. El disparador y la guía de envío son nuestros.

## Dos formas de usarlo

1. **Desde el chat** (las herramientas MCP `COMPOSIO_*` en Claude Code). Sirve para **probar** una conexión, explorar las herramientas o hacer algo una sola vez. Flujo:
   1. `COMPOSIO_SEARCH_TOOLS`, con `session: {generate_id: true}`, para encontrar la herramienta y ver si hay conexión activa.
   2. Si no la hay, `COMPOSIO_MANAGE_CONNECTIONS` (toolkit `gmail`, `whatsapp`…) y esperar a que Benji autorice.
   3. Revisar el **esquema completo** de la herramienta. Si trae `schemaRef`, usar `COMPOSIO_GET_TOOL_SCHEMAS`.
   4. `COMPOSIO_MULTI_EXECUTE_TOOL`, con argumentos exactos al esquema.
2. **Desde el código del agente** (producción), con el SDK de Composio para Python o TypeScript y una llave de Composio en `.env`.
   - El adaptador `ComposioChannel` implementa el puerto de envío, traduce los errores a excepciones del dominio y guarda el id de ejecución en `agent_steps.provider_ref`.
   - **VERIFICAR** en <https://docs.composio.dev> el nombre exacto del paquete, cómo se crea el cliente, cómo se elige la cuenta conectada (usuario o entidad) y cómo se ejecuta una herramienta, **antes** de escribir el adaptador.
   - Las pruebas usan respuestas grabadas, nunca la cuenta real.

## Herramientas que ya sabemos que existen (5/11/2026)

| Para | Herramienta | Notas |
|---|---|---|
| Correo con PDF | `GMAIL_SEND_EMAIL` | `attachment` como archivo subido; unos 25 MB máximo; `recipient_email`, `extra_recipients`, `cc`, `bcc`; `is_html` |
| Subir el PDF a WhatsApp | `WHATSAPP_UPLOAD_MEDIA` | Necesita `phone_number_id`; documentos de hasta 100 MB |
| Mandar el PDF | `WHATSAPP_SEND_MEDIA_BY_ID` | **Solo llega si esa persona escribió en las últimas 24 horas** |
| Ver los números de la cuenta | `WHATSAPP_GET_PHONE_NUMBERS` | Para obtener el `phone_number_id` |

## Trampas conocidas

- **WhatsApp es la API oficial de Meta.** Hace falta una cuenta de WhatsApp Business verificada y un número. Para escribir **primero** (como el reporte de las 07:00) se necesita una **plantilla aprobada** de tipo utilidad, con el documento. Antes de prometerlo, revisa si el toolkit de Composio tiene una herramienta para mandar plantillas (`COMPOSIO_SEARCH_TOOLS` con «send template»). Si no la tiene, ese paso va con un adaptador propio de la Cloud API.
- **Costo de WhatsApp** (México, mensaje de utilidad): unos 0.0085 USD desde el 1/10/2026 (VERIFICAR en la página de precios de Meta). Guárdalo en `agent_runs.cost_usd`.
- **Archivos:** las herramientas piden el archivo como una referencia que Composio sube a su almacenamiento. Revisa en el esquema cómo se le pasa un archivo local (el PDF de `REPORTS_DIR`).
- **Privacidad:** el PDF y los datos pasan por Composio y por Google o Meta. Decláralo en la ficha del agente y pide el OK.
- **Una cuenta por propósito:** si se puede, conecta una cuenta de servicio de Oráculo, no el correo personal de alguien.
- Si una herramienta esperada no aparece, repite la búsqueda con `search_strategy: "tool_search"`.
