# Fase 10 — Capas vivas base (sismos, incendios, vuelos, barcos)

Arranca esta fase solo cuando la Fase 9 esté cerrada. Pégalo en Claude Code (Opus 5.5, xhigh, modo plan).
Requisito: `docs/PLAN_FASES_9-10-11.md` en el repositorio.
Naturaleza de la fase: **desarrollo y evaluación**. El objetivo es probar si estas capas aportan valor, no ponerlas en producción. Trabájala **una capa por sesión** (10.1 a 10.4).

```
Vamos a construir la Fase 10: capas vivas base sobre el globo. Es una fase de desarrollo y evaluación, no de producción.

CONTEXTO
Lee docs/PLAN_FASES_9-10-11.md (Parte III) y repasa CLAUDE.md. God's Eye View (MIT) sirve solo como REFERENCIA de implementación: cómo consulta y dibuja cada fuente. No lo importamos como librería; consumimos sus mismas fuentes públicas sobre nuestro propio globo, como capas encendibles, para que quede una sola aplicación.

ANTES DE PLANEAR
En no más de 12 líneas, explícame:
- cómo encaja el puerto LiveLayerPort con la arquitectura hexagonal existente (un adaptador por capa, igual que los proveedores de noticias);
- por qué los datos vivos NO se mezclan con los datos de investigación de los casos (comparten el globo como lienzo, nada más);
- qué riesgo de rendimiento ves al sumar capas en tiempo real al globo.

REGLAS DE ESTA FASE
- Cada capa se enciende y apaga de forma independiente desde la UI.
- Cada capa respeta el límite de peticiones de su fuente y cachea lo razonable; no debe tirar los 60 fps del globo.
- Por cada fuente, deja en el código y en un ADR la nota de su licencia como DATO (sin afirmar uso comercial): USGS y NOAA son dominio público; NASA FIRMS es CC0; OpenSky es gratuito para uso de investigación/no comercial; AISStream es gratuito con atribución de cortesía. Esto protege a Benji cuando decida la postura de producción; no estorba el desarrollo.
- Las llaves o tokens de cada fuente van en .env, nunca en el frontend ni en el repositorio.
- Los datos vivos son efímeros: no se guardan como evidencia. (Capturarlos dentro de un caso es Fase 11.)

PLAN DE TRABAJO (una capa por sesión)
10.1 Puerto LiveLayerPort + capa de SISMOS (USGS Earthquake API). Sismos recientes sobre México con magnitud y epicentro.
10.2 Capa de INCENDIOS / focos de calor (NASA FIRMS) sobre México.
10.3 Capa de VUELOS (OpenSky Network, ADS-B) sobre el espacio aéreo mexicano.
10.4 Capa de BARCOS (AISStream.io) en costas mexicanas.

EMPEZAMOS POR LA 10.1 (SISMOS)
1. Consulta la documentación oficial vigente de la USGS Earthquake API y cítala. No inventes parámetros.
2. Preséntame el plan: diseño del puerto LiveLayerPort, el adaptador de sismos, cómo se enciende/apaga la capa, cómo se dibuja sobre el globo, frecuencia de actualización y manejo de errores. Incluye archivos, commits con su mensaje exacto, y cómo lo verificaré.
3. Espera mi aprobación. Trabaja en la rama feat/f10-1-sismos.
4. Antes de dejarlo por terminado, muéstrame la capa funcionando con sismos reales recientes sobre México y confírmame que se puede encender y apagar sin afectar el rendimiento.
5. Al cerrar, entrégame el resumen de sub-fase y el ADR con la nota de licencia de la fuente. No avances a la 10.2 sin mi aprobación.
```
