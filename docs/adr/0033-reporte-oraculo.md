# ADR-0033: Reporte PDF con el lenguaje visual de Oráculo: expediente, categorías, línea del tiempo y Estado ▸ Categoría ▸ Noticias

- **Estado:** Aceptado
- **Fecha:** 26 de octubre de 2026
- **Fase:** F12.10
- **Decide:** Benji (plan F12 §0 y §6: «un reporte mucho más dinámico… muy visual… muy formal»; «lo único que le gustó a mis jefes fue la representación visual de México con porcentajes, me pidieron más cosas así»; «las noticias con flecha de despliegue tipo chevron»; el 26/10/2026: «quiero que armes los pdf»)

## Contexto

El reporte de la F7 (ADR-0018) era un documento claro y sobrio. Le faltaba:

- la clasificación por delito (F12.4) y quién actúa (F12.5);
- la línea del tiempo (F12.7);
- la división de las noticias por estado;
- el lenguaje visual de Oráculo.

Como referencia de diseño se usó el expediente de persona de Oráculo 2.0 que Benji compartió. De él se tomó **solo la forma**, nunca su contenido:

- número de expediente;
- banda de confidencialidad;
- insignias de confianza;
- fechas en mayúsculas.

Los colores y tipografías salen de OSINT Oráculo (F12.7a).

## Decisión

1. **Portada Oráculo de hoja completa:**
   - fondo `#050505` con una red de nodos en cian, dibujada con una semilla fija por expediente: no hace falta ninguna imagen externa;
   - el número de expediente (`EXP-FGR-20261025-2300` en las corridas automáticas);
   - título en Orbitron y las cifras clave;
   - la banda «USO INTERNO · CONFIDENCIAL».
2. **Cada página interior lleva el expediente** en el encabezado, «USO INTERNO · CONFIDENCIAL», la fecha de emisión y el número de página. Las páginas interiores siguen en blanco para que se impriman bien.
3. **Panorama:** cifras, resumen ejecutivo y datos clave (ahora también el delito más frecuente) y **tarjetas por categoría** con su estado principal y las etiquetas libres más repetidas. Lo que viene de la IA lleva la insignia «IA · INFERENCIA».
4. **Se conserva el mapa de México con porcentajes**, la tabla por estado (ahora con %) y los medios. Se agregan **barras apiladas por categoría** en cada estado.
5. **Línea del tiempo:**
   - las barras usan la fecha de publicación, por hora o por día, en hora de la CDMX (ADR-0032);
   - los 3 picos van resaltados, cada uno con la nota que lo explica.
6. **Noticias por Estado ▸ Categoría ▸ Nota**, numeradas de corrido:
   - Estados y categorías generan **marcadores plegables** en el panel del lector de PDF (`bookmark-state: closed`). Es el «chevron» que funciona en cualquier lector, sin JavaScript.
   - Cada nota lleva sus insignias: categoría, quién actúa y confianza (ALTA, MEDIA o BAJA según el puntaje de relevancia de la IA).
7. **Fuentes incluidas:** Orbitron (de OSINT, OFL) para títulos y cifras, y Noto Sans para el texto. Se quitan los emojis de títulos y resúmenes: ninguna de las dos fuentes los tiene y salían como cuadros. Los chevrons usan «›», que Noto Sans sí tiene.
8. **Las corridas automáticas (F12.8) usan este mismo reporte**, y se sigue pudiendo pedir desde Explorar.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Secciones desplegables dentro de la página (JavaScript en el PDF) | Solo funcionan en Adobe Reader y no se imprimen. Los marcadores plegables funcionan en cualquier lector. |
| Mapa coloreado por categoría dominante | Requiere otro mapa estático; las barras apiladas por estado dicen lo mismo y caben junto al mapa con %. Queda como mejora. |
| Imagen de portada de OSINT | Una imagen corporativa no sirve de portada para cualquier reporte; la red generada se ve igual y no depende de archivos externos. |
| Fuentes del expediente de referencia (IBM Plex Mono, Spectral) | Habría que descargarlas. Orbitron y Noto Sans ya estaban, y Orbitron es la tipografía técnica de Oráculo. |

## Consecuencias

- **Tamaño:** el reporte de la primera corrida automática ocupa 26 páginas (104 notas) y ~265 KB.
- **Colores de las categorías:** son provisionales, hasta que se definan con datos (ADR-0029). Si una categoría trae `color`, se usa ese.
- **Pendiente:**
  - mapa por categoría dominante;
  - envío del reporte por WhatsApp o correo (F12.11).
