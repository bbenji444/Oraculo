/**
 * Globo 3D con MapLibre: mapa base, capas de INEGI, resaltado bajo el cursor,
 * tooltip ("Alcaldía Iztapalapa"), clic para seleccionar y vuelo a la región
 * seleccionada.
 *
 * No pide datos a la API: recibe la selección y avisa los clics con `onPick`.
 */
import 'maplibre-gl/dist/maplibre-gl.css';

import { type FeatureIdentifier, Map as MapLibreMap, NavigationControl } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';

import { setupMapLibre } from '../../map/setup';
import {
  buildMapStyle,
  featureLabel,
  FLY_MAX_ZOOM,
  INTERACTIVE_LAYERS,
  type RegionFeatureProps,
  type RegionLevel,
  SOURCE_BY_LEVEL,
} from '../../map/style';

export interface MapSelection {
  id: number;
  level: RegionLevel;
  bbox: [number, number, number, number];
}

interface GlobeMapProps {
  selection: MapSelection | null;
  onPick: (regionId: number) => void;
}

interface TooltipState {
  x: number;
  y: number;
  label: string;
  code: string;
}

// Vista inicial: el globo centrado en México (especificación §14.2).
const INITIAL_CENTER: [number, number] = [-102, 23.5];
const INITIAL_ZOOM = 1.8;
// Margen al volar a una región: deja libre el panel lateral de la izquierda.
const FLY_PADDING = { top: 80, bottom: 80, left: 420, right: 80 };
const FLY_DURATION_MS = 1800;

export function GlobeMap({ selection, onPick }: GlobeMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onPickRef = useRef(onPick);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    onPickRef.current = onPick;
  }, [onPick]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setupMapLibre();
    const map = new MapLibreMap({
      container,
      style: buildMapStyle(window.location.origin),
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
      attributionControl: { compact: true },
    });
    map.addControl(new NavigationControl({ visualizePitch: true }), 'top-right');

    let hovered: FeatureIdentifier | null = null;
    const clearHover = () => {
      if (hovered) map.setFeatureState(hovered, { hover: false });
      hovered = null;
    };

    map.on('load', () => {
      setReady(true);
    });
    map.on('mousemove', (event) => {
      const feature = map.queryRenderedFeatures(event.point, { layers: INTERACTIVE_LAYERS })[0];
      if (feature?.id === undefined) {
        clearHover();
        setTooltip(null);
        map.getCanvas().style.cursor = '';
        return;
      }
      const key: FeatureIdentifier = {
        source: feature.source,
        sourceLayer: feature.sourceLayer,
        id: feature.id,
      };
      const sameFeature =
        hovered !== null && hovered.id === key.id && hovered.source === key.source;
      if (!sameFeature) {
        clearHover();
        map.setFeatureState(key, { hover: true });
        hovered = key;
      }
      map.getCanvas().style.cursor = 'pointer';
      const props = feature.properties as RegionFeatureProps;
      setTooltip({
        x: event.point.x,
        y: event.point.y,
        label: featureLabel(props) ?? '',
        code: typeof props.code === 'string' ? props.code : '',
      });
    });
    map.on('mouseout', () => {
      clearHover();
      setTooltip(null);
    });
    map.on('click', (event) => {
      const feature = map.queryRenderedFeatures(event.point, { layers: INTERACTIVE_LAYERS })[0];
      if (feature?.id !== undefined) onPickRef.current(Number(feature.id));
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !selection) return;
    const source = SOURCE_BY_LEVEL[selection.level];
    const key: FeatureIdentifier = { source, sourceLayer: source, id: selection.id };
    map.setFeatureState(key, { selected: true });
    const [west, south, east, north] = selection.bbox;
    if (west === east && south === north) {
      // Localidad sin polígono: su "rectángulo" es un punto.
      map.flyTo({ center: [west, south], zoom: FLY_MAX_ZOOM.locality, duration: FLY_DURATION_MS });
    } else {
      map.fitBounds(
        [
          [west, south],
          [east, north],
        ],
        { padding: FLY_PADDING, maxZoom: FLY_MAX_ZOOM[selection.level], duration: FLY_DURATION_MS },
      );
    }
    return () => {
      if (mapRef.current === map) map.setFeatureState(key, { selected: false });
    };
  }, [selection, ready]);

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" aria-label="Globo interactivo" />
      {tooltip?.label && (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[calc(100%+12px)] rounded-lg border border-slate-700/80 bg-slate-900/95 px-3 py-1.5 text-sm shadow-xl shadow-black/40 backdrop-blur"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <span className="font-medium text-slate-100">{tooltip.label}</span>
          {tooltip.code && (
            <span className="ml-2 font-mono text-xs text-slate-400">{tooltip.code}</span>
          )}
        </div>
      )}
    </div>
  );
}
