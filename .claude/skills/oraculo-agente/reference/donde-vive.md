# Dónde vive el agente

Elige con estas preguntas, en orden. La primera que diga «sí» decide.

1. **¿Los datos o el disparador están dentro de un módulo de Oráculo?** Por ejemplo, «terminó la corrida» o «hay notas nuevas en PostgreSQL».
   → **Dentro del módulo**: Python, FastAPI y Celery en Proxmox.
   - Ventajas: la misma base y los mismos respaldos; las pruebas corren contra la base de pruebas; no hay que sacar datos a internet.
   - Disparadores: un evento al final de un proceso, como `run_automatic_job` en el monitor, o el reloj de Celery (beat).
2. **¿Tiene que recibir mensajes desde internet (un bot de WhatsApp, un webhook de un tercero) sin exponer el servidor de Proxmox?**
   → **Cloudflare Worker** como puerta de entrada.
   - Recibe el mensaje, verifica la firma y lo deja en una cola. Oráculo lo consulta por un túnel seguro, como Cloudflare Tunnel (VERIFICAR la configuración en su momento), o el Worker llama a la API de Oráculo protegida.
3. **¿Es independiente de Oráculo y corre por horario?** Por ejemplo, resumir blogs del sector cada mañana.
   → **Cloudflare Worker** con Cron Trigger. Usa **Workflows** si tiene varios pasos que deben reintentarse por separado, y **D1** para su auditoría.
   - Deja prendidos *Workers Logs* y *Traces*; vienen apagados.
4. **¿Es del tipo C (con criterio) y necesita una computadora propia para trabajar, como leer muchos archivos, correr código o navegar?**
   → **Agentes de Claude programados** (Managed Agents, `client.beta.deployments`, beta `managed-agents-2026-04-01`).
   - Cada corrida es una sesión con sus eventos guardados. El resultado se entrega por el sistema de envíos de Oráculo, para que también quede en la auditoría.

## Comparación rápida

| | Dentro del módulo | Cloudflare | Agentes de Claude |
|---|---|---|---|
| Costo base | Ya pagado (Proxmox) | Plan gratuito amplio | Tokens por corrida |
| Datos de Oráculo | Directo | Por la API o un túnel | Por la API |
| Si se apaga Proxmox | No corre | Sigue corriendo | Sigue corriendo |
| Mejor para | Tipo A ligado a un módulo | Puertas de entrada y agentes sueltos | Tipo C complejo |
| Auditoría | Tablas en PostgreSQL | Tablas en D1 y logs de Workers | Eventos de la sesión, más nuestra guía |

## Regla final

Si dudas, **dentro del módulo**. Mover algo a Cloudflare después es fácil si la lógica está separada en puertos y adaptadores.
