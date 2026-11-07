# Manual de fallas: envíos de reportes (ADR-0039)

Para quien esté de guardia. No hace falta leer código.

## 1. ¿Dónde veo qué pasó?
- **Pantalla:** http://localhost:8080/#/envios › «Historial de envíos». Cada fila dice estado, intentos y el error en español.
- **Consulta rápida** (`wsl make db-shell`):
  ```sql
  SELECT created_at, destination, status, attempts, last_error
  FROM deliveries ORDER BY created_at DESC LIMIT 10;
  ```
- **Logs:** `wsl make logs`; busca «Envíos de la corrida» o «Composio no aceptó el envío».

## 2. Fallas conocidas
| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Error «Falta COMPOSIO_API_KEY en el .env» | No hay llave del proyecto de Composio | Poner la llave `ak_` en el `.env` y `wsl make down && wsl make up` |
| Composio responde `401 Invalid API key` | La llave es `ck_` u `oak_`, o se borró | Crear una llave de **proyecto** (Platform › proyecto › Settings › API Keys) |
| La cuenta se queda en «Falta autorizar» | No se abrió o no se terminó el link | Volver a conectarla y pulsar «Ya autoricé» |
| Error `403` o «unauthorized» al mandar | Venció la autorización de Outlook o Gmail | Reconectar la cuenta y pulsar «Reintentar» |
| «Enviado» pero no llega | El proveedor tarda o lo mandó a spam | Esperar unos minutos y revisar «Correo no deseado»; Hotmail tiene límites diarios |
| Las corridas no mandan nada | `DELIVERIES_ENABLED=false` (así viene) o no hay reglas para esa hora | Revisar las reglas; encender en el `.env` y reiniciar |
| «Ya no existe el reporte de esa corrida» | Se borró la búsqueda o su PDF | Volver a generar el reporte desde Explorar |

## 3. Reintentar
- En la pantalla: botón **Reintentar** en la fila. No duplica lo que ya llegó: los intentos anteriores quedan registrados.

## 4. Apagar los envíos de emergencia
- Poner `DELIVERIES_ENABLED=false` en el `.env` y `wsl make down && wsl make up`. Las reglas se pueden apagar una por una con su interruptor.

## 5. A quién avisar
- Benjamin Oviedo.
