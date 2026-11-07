# Migrar un flujo de n8n a código

**Idea:** migración por estrangulamiento. Lo nuevo crece al lado de lo viejo y lo reemplaza flujo por flujo, sin un día de «apagar todo».

## Pasos

1. **Exportar el flujo** desde n8n (menú del flujo › *Download*): queda un JSON. Guárdalo en `agentes/<nombre>/n8n-original.json`, **sin credenciales**; revísalo antes de guardarlo.
2. **Leerlo y traducirlo a la ficha:**
   - el nodo disparador (Cron, Webhook…) es el disparador;
   - cada nodo es un paso de la ficha, con su nombre en español;
   - los nodos de credenciales son conectores de Composio o adaptadores propios;
   - los nodos IF/Switch son reglas del dominio, con pruebas;
   - los nodos de IA son pasos con Claude.
3. **Buscar lo que n8n hacía a escondidas:** reintentos, filtros dentro de expresiones `{{ }}`, horarios con su zona horaria, deduplicación. Cada cosa se vuelve una regla explícita y probada.
4. **Construir con la skill** (fases 2 a 5), con auditoría.
5. **Correr en paralelo una semana:**
   - el agente nuevo en **modo ensayo**, o mandando solo a Benji;
   - n8n sigue igual;
   - se comparan los resultados día por día.
6. **Si n8n necesita seguir recibiendo datos,** el agente nuevo le manda un **webhook firmado** (HMAC, cabeceras *Standard Webhooks*: `webhook-id`, `webhook-timestamp`, `webhook-signature`).
7. **Apagar el flujo de n8n** cuando el nuevo lleve una semana igual o mejor. Se anota la fecha en el catálogo y se guarda el JSON viejo como referencia.

## Qué preguntar antes de migrar

- ¿Quién usa el resultado de este flujo y qué pasa si se retrasa un día?
- ¿Tiene datos sensibles?
- ¿Cuántas veces falló el último mes? (Si n8n tiene el historial, revísalo.)
