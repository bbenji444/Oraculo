# ADR-0035: God's Eye View como módulo aparte, tal cual, para evaluarlo

- **Estado:** Retirado el 27/10/2026. Benji lo evaluó y lo quitó: «no le veo utilidad, no me sirve y está medio lento y feo». Se quitaron la pestaña, el servicio de `make up`, `scripts/dev/gods_eye.sh` y la excepción de la CSP. Lo de abajo queda como registro de lo que se probó.
- **Fecha:** 27 de octubre de 2026
- **Fase:** fuera de fase (antecede a la F10)
- **Decide:** Benji (27/10/2026: «implementa todo el proyecto de God's Eye View… pon una sección en el header antes de Estado del sistema… de momento solo quiero que lo copies tal cual como aparece en el proyecto de GitHub, si tiene otro mundo no importa… que la sección me lleve a ese módulo exacto… mañana lo voy a analizar»)

## Contexto

El plan de las fases 9 a 11 (`docs/PLAN_FASES_9-10-11.md`, §10.1) dice que God's Eye View no se importa: se consumen sus mismas fuentes sobre nuestro globo, para que quede una sola aplicación. Antes de decidir eso a fondo, Benji quiere ver y analizar el proyecto completo tal como es.

El proyecto es [bilawalsidhu/gods-eye-view](https://github.com/bilawalsidhu/gods-eye-view):

- su globo usa CesiumJS, con Vite y un servidor Node que reenvía las fuentes públicas;
- su código es MIT;
- unos datos incluidos no lo son: los cables submarinos de TeleGeography (CC BY-NC-SA) y unas imágenes de Vantor (CC BY-NC). Son de uso no comercial.

Lo que se midió el 27/10/2026:

- **Node:** pide la versión 24.14 o mayor. Windows tiene Node 22 y WSL no tenía Node.
- **Iframe:** no se deja mostrar dentro de otra página. Su página principal manda `X-Frame-Options: DENY` y `frame-ancestors 'none'`, a propósito, porque su servidor guarda llaves de API. Su modo embed oficial (`?embed=1`, con `GEV_EMBED_FRAME_ANCESTORS`) sí se deja mostrar, pero solo trae el globo, sin paneles.

## Decisión

1. **Se copia aparte, sin tocar su código:**
   - vive en `~/gods-eye-view`, en el disco de Linux de WSL;
   - queda fijo en el commit `15de9d7` (26/10/2026);
   - lo instala `make gev-instalar` (`scripts/dev/gods_eye.sh`), con su `package-lock` exacto;
   - usa su propio Node 24.22.1, bajado de nodejs.org y verificado con SHA-256, en `~/.local/node24`;
   - no se instala el Chrome de puppeteer, que solo usan sus pruebas visuales.
2. **`make up` lo arranca** como un servicio más, en `127.0.0.1:4173` (el puerto de su README), si está instalado. Lo mismo hacen `make down` y `make status`.
3. **La pestaña «God's Eye»**, antes de «Estado del sistema», muestra si el módulo está corriendo y un botón que abre la aplicación completa en su propia pestaña. No se enmarca en un iframe: para mostrarla completa habría que quitarle su protección, es decir, modificar su código.
4. **Única excepción en la CSP de nginx:** `connect-src` acepta `localhost:4173` y `127.0.0.1:4173`, para revisar si el módulo está corriendo.

## Alternativas consideradas

- **Iframe con el modo embed:** se ve solo el globo. No es «tal cual».
- **Iframe quitándole los encabezados:** modifica su código y abre a cualquier página que lo enmarque el panel donde se guardan llaves.
- **Copiarlo dentro de este repositorio:** son 205 MB, con datos de licencia no comercial. Además, `npm` es muy lento en `/mnt/d`.
- **Docker** (su `compose.yaml`): WSL no tiene Docker instalado.

## Consecuencias

- **Pruebas medidas el 27/10/2026:**
  - sus pruebas unitarias: 8,809, de las que pasan 8,807, fallan 0 y se saltan 2;
  - funcionan sin llave los vuelos (OpenSky, 6.7 mil), los vuelos militares (161), los satélites (CelesTrak, 11.5 mil), las misiones espaciales (20), las cámaras públicas, los perímetros de incendios, los ciclones, la integridad GNSS, el clima (radar y nubes), el viento, el transporte público, la radio y los sismos de USGS;
  - piden llave los barcos (AISStream), los incendios FIRMS, la voz (OpenAI), Google 3D y Street View, Cesium ion, TomTom y Mapillary. Se agregan dentro del módulo, en «Provider Settings».
- **Tarjeta de video:** son dos motores 3D en la misma tarjeta integrada. Conviene no tener abiertos a la vez Explorar y God's Eye View.
- **Esto no cambia el plan de la F10.** La forma de integrarlo se decide después de que Benji lo analice.
