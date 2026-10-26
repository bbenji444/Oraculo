/**
 * «Mis casos» sobre el globo de Explorar (Fase 9.6, D9).
 *
 * Con el interruptor encendido, cada caso abierto de la persona aparece como
 * un marcador en el centro de sus notas, con su nombre y cuántas entidades
 * confirmadas tiene. Clic en uno: entra a su muro (`#/explorar?caso=<id>`).
 *
 * No hace: no dibuja el muro (eso es `CaseWall`) ni pide más que la lista.
 */
import type { GeoJSONSource, Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { useEffect } from 'react';

import { useCasesOnMap } from '../../hooks/useCaseGraph';
import { wallHash } from '../../map/muro/orbit';
import type { CaseOnMap } from '../../services/caseGraph';
import { useExplorerStore } from '../../store/explorer';

const SOURCE = 'mis-casos';
const RING_LAYER = 'mis-casos-anillo';
// Exportada: el globo ignora los clics sobre un caso (no elige la región de abajo).
export const CASES_DOT_LAYER = 'mis-casos-punto';
const DOT_LAYER = CASES_DOT_LAYER;
const LABEL_LAYER = 'mis-casos-nombre';
const LAYERS = [RING_LAYER, DOT_LAYER, LABEL_LAYER];
// Ámbar: no se confunde con los puntos azules de las noticias ni con el muro.
const CASE_COLOR = '#F59E0B';

function geoJson(cases: CaseOnMap[]) {
  return {
    type: 'FeatureCollection' as const,
    features: cases.map((c) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] },
      properties: {
        caseId: c.id,
        label: `${c.name}\n${String(c.confirmed_count)} entidades · ${String(c.article_count)} notas`,
      },
    })),
  };
}

function removeLayers(map: MapLibreMap): void {
  for (const id of LAYERS) if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(SOURCE)) map.removeSource(SOURCE);
}

function addLayers(map: MapLibreMap, cases: CaseOnMap[]): void {
  removeLayers(map);
  map.addSource(SOURCE, { type: 'geojson', data: geoJson(cases) });
  map.addLayer({
    id: RING_LAYER,
    type: 'circle',
    source: SOURCE,
    paint: {
      'circle-radius': 18,
      'circle-color': CASE_COLOR,
      'circle-opacity': 0.18,
      'circle-blur': 0.6,
    },
  });
  map.addLayer({
    id: DOT_LAYER,
    type: 'circle',
    source: SOURCE,
    paint: {
      'circle-radius': 7,
      'circle-color': CASE_COLOR,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#FEF3C7',
    },
  });
  map.addLayer({
    id: LABEL_LAYER,
    type: 'symbol',
    source: SOURCE,
    layout: {
      'text-field': ['get', 'label'],
      'text-font': ['Noto Sans Regular'],
      'text-size': 12,
      'text-offset': [0, 1.4],
      'text-anchor': 'top',
      'text-optional': true,
    },
    paint: { 'text-color': '#FDE68A', 'text-halo-color': '#020617', 'text-halo-width': 1.4 },
  });
}

export function CasesOnGlobe({ map }: { map: MapLibreMap | null }) {
  const showCases = useExplorerStore((s) => s.showCases);
  const inWall = useExplorerStore((s) => s.wallCaseId !== null);
  const earth = useExplorerStore((s) => s.earth);
  const visible = showCases && !inWall;
  const cases = useCasesOnMap(visible).data;

  useEffect(() => {
    if (!map) return;
    if (!visible || !cases) {
      removeLayers(map);
      return;
    }
    const source = map.getSource<GeoJSONSource>(SOURCE);
    if (source) {
      void source.setData(geoJson(cases));
    } else {
      addLayers(map, cases);
    }
  }, [map, visible, cases]);

  // Día/noche cambia el estilo y se lleva las capas: se vuelven a poner.
  useEffect(() => {
    if (!map || !visible || !cases) return;
    const readd = () => {
      if (!map.getSource(SOURCE)) addLayers(map, cases);
    };
    map.once('idle', readd);
    return () => {
      map.off('idle', readd);
    };
  }, [map, visible, cases, earth]);

  useEffect(() => {
    if (!map || !visible) return;
    const onClick = (event: MapMouseEvent) => {
      const layers = map.getLayer(DOT_LAYER) ? [DOT_LAYER, RING_LAYER] : [];
      const [hit] = map.queryRenderedFeatures(event.point, { layers });
      const caseId = hit?.properties.caseId as string | undefined;
      if (caseId) window.location.hash = wallHash(caseId);
    };
    const pointer = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
    const plain = () => {
      map.getCanvas().style.cursor = '';
    };
    map.on('click', onClick);
    map.on('mouseenter', DOT_LAYER, pointer);
    map.on('mouseleave', DOT_LAYER, plain);
    return () => {
      map.off('click', onClick);
      map.off('mouseenter', DOT_LAYER, pointer);
      map.off('mouseleave', DOT_LAYER, plain);
    };
  }, [map, visible]);

  return null;
}
