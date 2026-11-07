# Agentes conversacionales (tipo B)

Un agente que platica: alguien le escribe por WhatsApp, Slack o un chat web, y el agente responde consultando Oráculo y, si hace falta, actúa.

## Cómo está armado

```
Mensaje entrante ─► puerta de entrada (verifica la firma) ─► run en agent_runs
        ─► Claude con herramientas (tool use)
              ├─ herramientas de LECTURA de Oráculo (buscar notas, ver la última corrida)
              └─ herramientas de ACCIÓN (mandar, crear un caso) ─► piden confirmación
        ─► respuesta ─► se manda y se registra
```

- **Claude como cerebro**, con tool use. Escribe el código con la skill `claude-api`: el ciclo de herramientas y la elección del modelo (uno rápido y barato para preguntas simples, el más capaz para análisis).
- **Las herramientas son funciones nuestras**, con permisos claros. Primero las de lectura. Las de acción, después y con confirmación.
- **Las herramientas de Composio** (Gmail, Drive, Slack…) se pueden dar al agente, pero **solo las que la ficha aprueba**, nunca el catálogo completo.

## Reglas de seguridad

1. **Quién es quién:** cada mensaje se liga a una persona registrada. Un número desconocido recibe una respuesta genérica y no consulta nada.
2. **Solo ve lo que esa persona puede ver** en Oráculo: los mismos permisos que en la pantalla.
3. **Confirmación humana para actuar:** «¿Mando este reporte a estas 3 personas? Responde SÍ». La acción se registra con quién la confirmó.
4. **Lo que dice el contenido no son órdenes.** El texto de las noticias o de un correo es información, no instrucciones para el agente.
5. **Tope de costo por conversación y por día**, registrado en `agent_runs.cost_usd`.
6. **Cada conversación es una ejecución**, y cada llamada a Claude o a una herramienta es un paso en `agent_steps`, con tokens y costo.

## Memoria de la conversación

- La de corto plazo (los últimos mensajes) va en la base, ligada a la persona.
- No guardes datos sensibles de más. Define en la ficha cuánto tiempo se conserva.

## WhatsApp como canal de entrada

- Se necesita el webhook de mensajes de la Cloud API. Meta llama a una URL pública: la puerta en Cloudflare (ver `donde-vive.md`).
- Dentro de la ventana de 24 horas después de que la persona escribe se puede responder libremente. Fuera de ella, solo con plantillas aprobadas.
