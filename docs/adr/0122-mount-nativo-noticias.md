# ADR-0122: El monitor también vive en /noticias/ (mount nativo del gateway)

- **Estado:** propuesto (20/11/2026).
- **Fase:** F12.
- **Reemplaza en parte:** ADR-0119 (el gateway quitaba `/m/noticias` antes de reenviar).

## Contexto

El ADR-0119 se escribió con el contrato `/m/<slug>/`: Oráculo quitaba ese prefijo y reenviaba el resto a la raíz del monitor.

El mismo 20/11/2026 el core cambió de estrategia (commit `5b30686`, `apps/dashboard/proxy.py` y `middleware.py`). Ahora cada módulo vive bajo un *mount nativo* tomado de la ruta de su `href` (OSINT: `http://…/osint/html` → `/osint`). Oráculo reenvía **la misma ruta** al upstream, sin quitar nada.

El módulo Noticias tenía `href = http://10.244.214.144:8080`, sin ruta. El mount quedaba vacío y `/go/Noticias/` mandaba a `/`, el tablero de Oráculo. Benji pegó su llave y no pudo entrar. En el log de la VM no había ni una petición del servidor de Oráculo.

## Decisión

1. **nginx atiende `/noticias/…` igual que `/…`.**
   - `rewrite ^/noticias/(.*)$ /$1 last` vuelve a buscar el location, así la API, los 240 s y los mapas con Range funcionan igual.
   - `/noticias` redirige con 301 relativo a `/noticias/`.
   - La raíz sigue sirviendo, para la API directa y para `make status`.
2. **En Oráculo el `href` pasa a `http://10.244.214.144:8080/noticias/`.** Con eso el mount es `/noticias` y la entrada es `/noticias/`. Lo cambia el admin de Oráculo; el monitor no toca ese servidor.
3. **La pantalla no cambia:** ya usa rutas relativas (ADR-0119), así que sirve igual bajo `/noticias/`.

## Alternativas consideradas

- **Compilar la pantalla con `base: '/noticias/'`.**
  - Contras: rompe la raíz y obliga a dos compilaciones.
  - Se descartó: la base relativa ya sirve para las dos.
- **Pedir a Oráculo que vuelva a `/m/<slug>/` con prefijo quitado.**
  - Contras: depende de otro equipo, y el core ya eligió el mount nativo para todos los módulos.

## Consecuencias

- **Mientras Oráculo no cambie el `href`,** `/go/Noticias/` sigue regresando al tablero.
- **El prefijo `/noticias` queda reservado** en el monitor: ninguna ruta propia puede empezar así.
- **Entrega actualizada** en [docs/gateway-oraculo.md](../gateway-oraculo.md).
