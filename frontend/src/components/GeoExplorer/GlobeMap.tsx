/**
 * Globo 3D con MapLibre: mapa base, capas de INEGI, resaltado bajo el cursor,
 * tooltip ("Alcaldía Iztapalapa"), clic para seleccionar, vuelo a la región
 * seleccionada y giro lento automático que se detiene al tocar el mapa.
 *
 * No pide datos a la API: recibe la selección y avisa los clics con `onPick`.
 */
import 'maplibre-gl/dist/maplibre-gl.css';

import { type FeatureIdentifier, Map as MapLibreMap, NavigationControl } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';

import { setupMapLibre } from '../../map/setup';
import {
  easeOutQuint,
  INTRO_DURATION_MS,
  INTRO_FROM_ZOOM,
  INTRO_LNG_OFFSET_DEGREES,
} from '../../map/motion';
import {
  GLOBE_BEARING,
  prefersReducedMotion,
  REGION_BEARING,
  SPIN_STEP_MS,
  spinDegrees,
} from '../../map/spin';
import { useCameraStore } from '../../store/camera';
import {
  buildMapStyle,
  EARTH_LAYER,
  type EarthMode,
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
  /** Si el globo gira solo (especificación §14.2). */
  spinning: boolean;
  /** Avisa que la persona tocó el mapa: el giro se detiene. */
  onUserInteract: () => void;
  /** Cara de la Tierra visible (ADR-0017). */
  earth: EarthMode;
}

// Eventos de la persona sobre el mapa que detienen el giro.
const USER_EVENTS = ['mousedown', 'touchstart', 'wheel', 'dragstart'] as const;

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

export function GlobeMap({ selection, onPick, spinning, onUserInteract, earth }: GlobeMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onPickRef = useRef(onPick);
  const onUserInteractRef = useRef(onUserInteract);
  // El ciclo de giro vive dentro de MapLibre (eventos), fuera de React: lee
  // estos refs para saber si debe seguir y cómo dar el siguiente paso.
  const spinningRef = useRef(spinning);
  const spinStepRef = useRef<() => void>(() => undefined);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [ready, setReady] = useState(false);
  // La cara de la Tierra al crear el mapa; los cambios se aplican sin recrearlo.
  const earthRef = useRef(earth);

  useEffect(() => {
    onPickRef.current = onPick;
    onUserInteractRef.current = onUserInteract;
  }, [onPick, onUserInteract]);

  useEffect(() => {
    spinningRef.current = spinning;
    const map = mapRef.current;
    if (!spinning || !ready || !map) return;
    if (spinDegrees(map.getZoom()) === 0) {
      // Muy de cerca no se gira: primero se aleja a la vista de globo sobre
      // México; al terminar (moveend) empieza el giro.
      map.easeTo({
        center: [map.getCenter().lng, INITIAL_CENTER[1]],
        zoom: INITIAL_ZOOM,
        pitch: 0,
        bearing: GLOBE_BEARING,
        duration: FLY_DURATION_MS,
      });
    } else if (!map.isMoving()) {
      // Primer paso; los siguientes los encadena moveend. Si la cámara ya se
      // mueve (por ejemplo, la entrada), el giro empieza cuando termine.
      spinStepRef.current();
    }
  }, [spinning, ready]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setupMapLibre();
    // Entrada (ADR-0017): la cámara arranca lejos y desplazada al este, y llega
    // a México frenando. Con "menos movimiento" empieza ya en México.
    const intro = !prefersReducedMotion();
    const map = new MapLibreMap({
      container,
      style: buildMapStyle(window.location.origin, earthRef.current),
      center: intro
        ? [INITIAL_CENTER[0] + INTRO_LNG_OFFSET_DEGREES, INITIAL_CENTER[1]]
        : INITIAL_CENTER,
      zoom: intro ? INTRO_FROM_ZOOM : INITIAL_ZOOM,
      // Eje inclinado como el de la Tierra (ver map/spin.ts).
      bearing: GLOBE_BEARING,
      attributionControl: { compact: true },
    });
    map.addControl(new NavigationControl({ visualizePitch: true }), 'top-right');

    let hovered: FeatureIdentifier | null = null;
    const clearHover = () => {
      if (hovered) map.setFeatureState(hovered, { hover: false });
      hovered = null;
    };

    // Giro: una animación lineal de SPIN_STEP_MS que, al terminar (moveend),
    // lanza la siguiente mientras `spinning` siga activo. Es el patrón de los
    // ejemplos de globo giratorio de MapLibre; la latitud no cambia, así que
    // México sigue a la vista en cada vuelta.
    // El giro no empieza hasta que termine la entrada de la cámara: si no, el
    // primer moveend del mapa lo arrancaba antes y daba un tirón (17/10/2026).
    let introDone = !intro;
    const spinStep = () => {
      if (!spinningRef.current || !introDone) return;
      const degrees = spinDegrees(map.getZoom());
      if (degrees === 0) return;
      const center = map.getCenter();
      map.easeTo({
        center: [center.lng - degrees, center.lat],
        duration: SPIN_STEP_MS,
        easing: (t) => t,
      });
    };
    spinStepRef.current = spinStep;
    map.on('moveend', spinStep);
    for (const type of USER_EVENTS) {
      map.on(type, () => {
        onUserInteractRef.current();
      });
    }

    map.on('load', () => {
      setReady(true);
      if (intro) {
        map.once('moveend', () => {
          introDone = true;
          spinStep();
        });
        map.easeTo({
          center: INITIAL_CENTER,
          zoom: INITIAL_ZOOM,
          duration: INTRO_DURATION_MS,
          easing: easeOutQuint,
        });
      }
    });
    // El fondo de universo sigue a la cámara (sin redibujar React).
    const shareCamera = () => {
      const center = map.getCenter();
      useCameraStore.getState().setView({
        lng: center.lng,
        lat: center.lat,
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
      });
    };
    map.on('move', shareCamera);
    shareCamera();
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

    // Si el mapa se crea cuando su contenedor aún no tiene tamaño (pestaña o
    // panel ocultos), MapLibre se queda en 400×300 y deforma el globo; este
    // observador lo reajusta en cuanto el contenedor cambia (17/10/2026).
    const observer = new ResizeObserver(() => {
      map.resize();
    });
    observer.observe(container);

    mapRef.current = map;
    // Diagnóstico: con ?depurar en la URL, el mapa queda en window.__mapa para
    // medir cámara y fluidez desde la consola (verificación de F6).
    if (new URLSearchParams(window.location.search).has('depurar')) {
      (window as unknown as { __mapa?: MapLibreMap }).__mapa = map;
    }
    return () => {
      observer.disconnect();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  useEffect(() => {
    earthRef.current = earth;
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const mode of ['night', 'day'] as const) {
      map.setLayoutProperty(EARTH_LAYER[mode], 'visibility', mode === earth ? 'visible' : 'none');
    }
  }, [earth, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !selection) return;
    const source = SOURCE_BY_LEVEL[selection.level];
    const key: FeatureIdentifier = { source, sourceLayer: source, id: selection.id };
    map.setFeatureState(key, { selected: true });
    const [west, south, east, north] = selection.bbox;
    if (west === east && south === north) {
      // Localidad sin polígono: su "rectángulo" es un punto.
      map.flyTo({
        center: [west, south],
        zoom: FLY_MAX_ZOOM.locality,
        bearing: REGION_BEARING,
        duration: FLY_DURATION_MS,
      });
    } else {
      map.fitBounds(
        [
          [west, south],
          [east, north],
        ],
        {
          padding: FLY_PADDING,
          maxZoom: FLY_MAX_ZOOM[selection.level],
          bearing: REGION_BEARING,
          duration: FLY_DURATION_MS,
        },
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
