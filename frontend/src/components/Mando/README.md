# Centro de mando (diseño 3)

El diseño principal de Explorar desde el 27/10/2026 (ADR-0037): la búsqueda como una consola de consulta de vidrio abajo, el globo encima y los resultados en un expediente a la derecha.

El diseño anterior, con la columna a la izquierda (ADR-0036), se ve con `?clasico` en la URL:

```
http://localhost:8080/?clasico#/explorar
```

| Archivo               | Qué hace                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `MandoPanels.tsx`     | Acomoda las piezas sobre el globo y mide el alto de la consola.                                                           |
| `MissionDock.tsx`     | La consola en tres zonas: radar, la frase con sus tarjetas y las consultas recientes, y el costo con «Iniciar barrido».   |
| `TrackPicker.tsx`     | La ventana «¿Qué rastrear?» al centro: la FGR con sus subdivisiones y los temas generales (ADR-0038).                     |
| `MissionProgress.tsx` | Mientras se busca: el riel de etapas, el porcentaje, el cronómetro y la bitácora.                                         |
| `ScanOverlay.tsx`     | El radar sobre el globo y el letrero «BARRIDO COMPLETO»: la cúpula en una zona y la esfera en «Todo el mundo» (ADR-0116). |
| `Dossier.tsx`         | El expediente: las cifras, las categorías, la cronología o la lista, y el reporte.                                        |
| `PlatformTabs.tsx`    | Las pestañas «Todo · Noticias · Facebook · X…» del expediente, como en Google: una plataforma a la vez (ADR-0117).        |
| `FilterPopover.tsx`   | La ventana «Filtro»: plataforma, categorías, estado, ubicación y no relevantes.                                           |
| `PlatformFilter.tsx`  | La sección «Plataforma» de «Filtro»: varias plataformas a la vez (ADR-0117).                                              |
| `ReportViewer.tsx`    | «Ver reporte» y «Descargar PDF», y la ventana donde se lee el reporte sin descargarlo (ADR-0111).                         |
| `mission.ts`          | La lógica pura: los textos de la frase, el horario de las corridas automáticas, las consultas recientes y la bitácora.    |

## Dónde viven las demás piezas

- **Estilos:** `src/styles/mando.css`.
- **Estado propio:** `src/store/mando.ts`. Guarda qué tarjeta está abierta, si se ve el expediente y el alto de la consola.
- **La cúpula y la esfera del radar:** capas WebGL del mapa en `src/map/radar/` (ver su README). `ScanOverlay.tsx` solo decide cuál poner y dibuja los letreros.
- **Lo que comparte con el diseño 2:**
  - la búsqueda misma, en `store/explorer.ts`;
  - `useSearchLauncher`;
  - los controles de cada parte de la frase;
  - la cronología y la lista;
  - las plataformas y las bandas de relevancia (`Explore/platforms.ts` y `Explore/relevance.ts`, ADR-0117): «No relevantes» suma solo las cercanas; las ajenas se cuentan aparte y se ven con el botón «Ver las N que descartó la IA» (`Explore/StandingNote.tsx`);
  - los avisos de la búsqueda (Google web sin créditos, ADR-0115) en letra chica, en la consola y en el expediente (`Explore/SearchNotices.tsx`).
