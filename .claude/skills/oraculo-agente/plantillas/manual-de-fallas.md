# Manual de fallas: <nombre-del-agente>

Para quien esté de guardia. Nadie necesita leer código para seguirlo.

## 1. ¿Dónde veo qué pasó?
- Pantalla: <URL o sección>.
- Consulta rápida (PostgreSQL o D1):
  ```sql
  SELECT id, status, started_at, error_summary
  FROM agent_runs WHERE agent = '<nombre>'
  ORDER BY started_at DESC LIMIT 10;
  ```
- Logs: buscar el `run_id` en <dónde están los logs>.

## 2. Fallas conocidas
| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Envío de WhatsApp en `failed` con «fuera de la ventana de 24 horas» | Se intentó mandar sin plantilla | Revisar que el paso use la plantilla aprobada |
| Correo en `failed` por autenticación | Venció la autorización de la conexión en Composio | Volver a autorizar Gmail en Composio y pulsar Reintentar |
| No hay ejecución a la hora esperada | El servidor estaba apagado o se detuvo el reloj | `make status`; si corresponde, correr a mano: <comando> |
| | | |

## 3. Reintentar
- Desde la pantalla: botón **Reintentar** en la guía. No duplica lo que ya llegó.
- A mano: <comando>.

## 4. Apagar el agente de emergencia
- <variable de entorno o interruptor> y reiniciar: <comando>.

## 5. A quién avisar
- <persona y canal>.
