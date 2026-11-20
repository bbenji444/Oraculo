# ADR-0119: Monitor detrás del gateway de Oráculo

- **Estado:** propuesto (20/11/2026).
- **Fase:** F12.

## Contexto

Oráculo core definió cómo abrir los módulos externos sin sacar al usuario de su dirección (`gateway_modulos_agentes.md`):

1. El usuario hace clic en el módulo y llega a `https://oraculo/m/<slug>/`.
2. Oráculo reenvía cada petición al módulo e inyecta `Authorization: Bearer <llave del usuario en el módulo>`, `X-Oraculo-User`, `X-Oraculo-User-Id` y `X-Oraculo-Module`.
3. Reescribe `Location`, `Set-Cookie` y las URLs del HTML. **No** reescribe las URLs metidas en el JavaScript.
4. Espera 30 s por defecto.

El módulo OSINT ya lo cumple (`gateway-oraculo-modulo.md`, 20/11/2026). Benji, el mismo día: «vamos a dejar el monitor listo igual que OSINT».

El monitor ya cumplía lo esencial: una llave `orc_live_…` por persona que se acepta como Bearer (ADR-0047), 401 sin llave, el panel «Accesos», búsquedas asíncronas y navegación por `#/`. Una revisión del código encontró lo que fallaba:

- **Rutas absolutas en la pantalla:** `/api/v1`, `/tiles`, `/assets`, `/globo.svg` y `window.location.origin` en el mapa. Detrás del gateway todo eso se pediría a Oráculo, fuera de `/m/noticias/`.
- **Una sola IP para todos:** cada petición llegaría con la IP de Oráculo. La bitácora vería a una sola persona, y diez llaves malas de cualquiera bloquearían a todos con 429.
- **Cualquiera podía entrar directo a la VM**, saltándose a Oráculo.
- **Tiempo de espera corto:** el reporte (la primera vez escribe el resumen con la IA), las sugerencias de términos y los envíos de prueba pueden pasar de 30 s. nginx los cortaba a los 60.
- **Llave inválida:** si fallaba la llave que mandó Oráculo, la pantalla ofrecía usuario, contraseña y código del monitor, que el analista no tiene.
- **Sin candado:** nada impedía arrancar la VM en `AUTH_MODE=dev`, donde entra cualquiera como superusuario.

## Decisión

1. **La pantalla pide todo junto a la página.**
   - El build usa `base: './'` y la API parte de `import.meta.env.BASE_URL`, que vale `./` en el build y `/` en desarrollo y pruebas.
   - El mapa arma sus URLs absolutas con `pageBase()` (`config/api.ts`), que conserva el prefijo, porque PMTiles exige URLs absolutas.
   - La misma compilación sirve en la raíz (acceso directo) y bajo `/m/noticias/`.
2. **nginx confía solo en el gateway.** `ORACULO_GATEWAY_IPS` lista las IP del proxy de Oráculo:
   - solo de esas IP se cree `X-Forwarded-For` (`real_ip`), y nginx manda a la API una sola IP, la del analista, sin agregarla a la cadena;
   - solo de esas IP pasan los `X-Oraculo-*`; de cualquier otra se borran.
3. **`GATEWAY_ONLY=si` cierra la puerta.** Solo entran el gateway y la propia máquina; el resto recibe 403.
   - La decisión se toma sobre `$realip_remote_addr`, quien abrió la conexión, porque `allow` vería la IP ya reescrita.
   - Por defecto es `no`, para no cortar el acceso directo mientras Oráculo no esté conectado.
4. **240 s** para `searches/{id}/report`, `report/view`, `concepts/suggest`, `deliveries/test` y `deliveries/history/{id}/retry`, lo mismo que pide OSINT. El resto de `/api` se queda en 60 s.
5. **Saber cuándo se entró por Oráculo.**
   - `/app-config` responde `via_gateway`. Con él la pantalla muestra «Tu acceso lo da Oráculo» en lugar del formulario, y oculta «Salir» y «Mi contraseña».
   - Detrás del gateway el 401 manda con el administrador de Oráculo, y el log dice de quién era la petición.
   - Si `X-Oraculo-User` no coincide con el dueño de la llave, queda una advertencia en el log, una vez por pareja.
   - Quién es la persona lo dice **solo** la llave.
6. **Candado obligatorio.** `make up` se niega a arrancar en `AUTH_MODE=dev` si nginx escucha fuera de la propia máquina, y `/health` reporta `auth_mode`.
7. **La entrega** para Oráculo y los agentes de IA del equipo está en [docs/gateway-oraculo.md](../gateway-oraculo.md).

## Alternativas consideradas

- **Fijar `base: '/m/noticias/'` en el build.**
  - Pros: no depende de rutas relativas.
  - Contras: rompe el acceso directo actual (`192.168.0.42:8080`) y obliga a dos compilaciones.
  - Se descartó: la base relativa sirve para las dos.
- **Que Oráculo reescriba también el JavaScript.**
  - Contras: frágil (las URLs se arman en tiempo de ejecución) y depende de otro equipo.
- **La lista de IP en la API** (como OSINT).
  - Contras: nginx sirve `/tiles`, `/assets` y la página sin pasar por la API, así que quedarían abiertos.
  - Se descartó: en nginx cubre todo.
- **Guardar los `X-Oraculo-*` en una columna de la bitácora.**
  - Contras: migración y tocar los cuatro escritores de auditoría.
  - Por ahora basta el log; se puede agregar después.
- **Volver asíncrono el reporte** (en el worker, con consulta de estado).
  - Pros: no dependería del tiempo del gateway.
  - Contras: cambia el flujo de la pantalla.
  - Se descartó por ahora: con 240 s basta.

## Consecuencias

- **Lo que debe hacer Oráculo** queda escrito en la entrega:
  - redirigir `/m/noticias` a `/m/noticias/`;
  - dejar pasar `Range` y `206` sin juntarlos ni comprimirlos;
  - 240 s en las rutas largas;
  - abrir el módulo como página completa, no en iframe.
- **Si Oráculo usara un iframe,** los encabezados actuales (`X-Frame-Options: DENY`, `frame-ancestors 'none'`) lo bloquearían. Habría que cambiarlos con un ADR nuevo.
- **Swagger** (`/api/v1/docs`) pide `openapi.json` con ruta absoluta, así que solo sirve en acceso directo.
- **Encender `GATEWAY_ONLY=si` en la VM** corta el acceso directo por IP. Se hace cuando Oráculo ya entre, con OK de Benji.
- **Verificado el 20/11/2026** con un Oráculo simulado en la PC (nginx en 8081 que quita `/m/noticias`, inyecta una llave de prueba y sale desde otra IP):
  - todas las peticiones quedan dentro de `/m/noticias/`;
  - entra sin login;
  - las teselas responden 206, incluso en el archivo de 1.3 GB;
  - la bitácora guarda la IP real;
  - una llave mala muestra el aviso;
  - los encabezados falsificados directo a la VM no cuentan.
