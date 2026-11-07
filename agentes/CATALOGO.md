# Catálogo de agentes y automatizaciones

La lista que reemplaza a la pantalla de flujos de n8n. Cada automatización nueva se registra aquí al encenderse (skill `oraculo-agente`, fase 8).

| Nombre | Tipo | Dónde vive | Lo dispara | Dueño | Estado | Auditoría |
|---|---|---|---|---|---|---|
| `envios-reportes` | A · automatización fija | Monitor de noticias (`/envios`, ADR-0039) | Fin de cada corrida FGR (07:00, 15:00 y 23:00) y el reloj cada minuto para reintentos | Benjamin Oviedo | Prototipo: correo funcionando, apagado para corridas (`DELIVERIES_ENABLED=false`); WhatsApp próximamente | Pantalla «Envíos» › Historial; tablas `deliveries` y `delivery_attempts` · [manual de fallas](envios-reportes/MANUAL_DE_FALLAS.md) |
