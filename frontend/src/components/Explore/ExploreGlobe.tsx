/**
 * El globo de la pantalla Explorar (especificación §14.2; ADR-0017).
 *
 * - Tierra con texturas de la NASA (día o noche) sobre el fondo de universo.
 * - Entrada desde el espacio, giro lento con rampa que se detiene al tocar y
 *   se reanuda solo tras 25 s sin uso (si no hay región ni nota elegida).
 * - Hover y clic en regiones (país → estado → municipio → localidad); la
 *   región elegida vive en el store, igual que en los filtros.
 * - Resultados: mapa de calor, grupos, puntos con brillo que aparecen en
 *   cascada, anillo punteado para lo ubicado solo por estado o país, latido de
 *   la nota elegida y su ficha con línea guía (se oculta si el punto queda
 *   detrás del globo).
 * - Velocidades del módulo `map/motion.ts` según la preferencia de la persona.
 *
 * No pide datos a la API: recibe las notas y los colores de los conceptos.
 */
import 'maplibre-gl/dist/maplibre-gl.css';

import {
  type FeatureIdentifier,
  type GeoJSONSource,
  LngLat,
  type LngLatBoundsLike,
  Map as MapLibreMap,
  NavigationControl,
} from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';

import { useRegionDetail } from '../../hooks/useRegions';
import {
  easeInOutCubic,
  easeOutQuint,
  flyDurationMs,
  flyPitch,
  IDLE_RESUME_MS,
  INTRO_DURATION_MS,
  INTRO_FROM_ZOOM,
  INTRO_LNG_OFFSET_DEGREES,
  type MotionPreset,
  pulsePhase,
  spinFactor,
  spinRamp,
  staggerDelayMs,
} from '../../map/motion';
import {
  DASHED_RING_IMAGE,
  dashedRingPixels,
  isOnVisibleSide,
  NEWS_SOURCE,
  newsFeatures,
  newsLayers,
  pulseStyle,
  selectedFilter,
  CLUSTER_MAX_ZOOM,
  CLUSTER_RADIUS_PX,
  calloutPlacement,
} from '../../map/newsLayers';
import { setupMapLibre } from '../../map/setup';
import { GLOBE_BEARING, REGION_BEARING, SPIN_STEP_MS, spinDegrees } from '../../map/spin';
import {
  buildMapStyle,
  EARTH_LAYER,
  featureLabel,
  FLY_MAX_ZOOM,
  INTERACTIVE_LAYERS,
  type RegionFeatureProps,
  type RegionLevel,
  SOURCE_BY_LEVEL,
} from '../../map/style';
import type { Article } from '../../services/searches';
import { useCameraStore } from '../../store/camera';
import { useExplorerStore } from '../../store/explorer';
import { NewsCard } from './NewsCard';
import { GLASS } from './ui';

interface ExploreGlobeProps {
  articles: readonly Article[];
  colors: ReadonlyMap<number, string>;
}

interface Tooltip {
  x: number;
  y: number;
  label: string;
  detail: string;
}

interface Callout {
  // Nota a la que pertenece: si cambia la nota elegida, esta ficha ya no se muestra.
  articleId: number;
  x: number;
  y: number;
  visible: boolean;
}

// Vista inicial: México con el eje inclinado (map/spin.ts).
const INITIAL_CENTER: [number, number] = [-102, 23.5];
const INITIAL_ZOOM = 1.8;
// Márgenes al volar: libres el panel de la izquierda y las gráficas de la derecha.
const FLY_PADDING = { top: 90, bottom: 90, left: 430, right: 330 };
// Curva de vuelo de MapLibre: 1.42 es su valor por defecto (aleja y acerca
// sin marear); un poco más alta da más sensación de "despegue".
const FLY_CURVE = 1.5;
// Al volar a una nota: el punto queda a la izquierda y abajo del centro para
// que su ficha quepa a la derecha.
const ARTICLE_OFFSET: [number, number] = [-120, 70];
// Zoom al volar a una nota: municipio o más cerca si es precisa; estado si no.
const ARTICLE_ZOOM_PRECISE = 7.5;
const ARTICLE_ZOOM_COARSE = 5;
// Ancho de la ficha; su lugar lo decide calloutPlacement (nunca se sale del mapa).
const CALLOUT_WIDTH = 330;
// Alto supuesto de la ficha mientras se mide la real.
const CALLOUT_INITIAL_HEIGHT = 280;
// Revisión de inactividad para reanudar el giro.
const IDLE_CHECK_MS = 1000;
// El latido se redibuja a 30 cuadros por segundo: suficiente y barato.
const PULSE_FRAME_MS = 1000 / 30;
// Rampa mínima: con 0 el paso no se movería y la cadena de giro se cortaría.
const MIN_SPIN_RAMP = 0.05;
// Eventos de la persona que detienen el giro.
const USER_EVENTS = ['mousedown', 'touchstart', 'wheel', 'dragstart'] as const;
const NEWS_LAYERS = ['news-point', 'news-coarse', 'news-cluster'];
const LEVEL_ORDER: RegionLevel[] = ['country', 'state', 'municipality', 'locality'];

export function ExploreGlobe({ articles, colors }: ExploreGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const [callout, setCallout] = useState<Callout | null>(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [cardHeight, setCardHeight] = useState(CALLOUT_INITIAL_HEIGHT);
  const cardRef = useRef<HTMLDivElement>(null);

  const regionId = useExplorerStore((s) => s.regionId);
  const articleId = useExplorerStore((s) => s.articleId);
  const spinning = useExplorerStore((s) => s.spinning);
  const earth = useExplorerStore((s) => s.earth);
  const motion = useExplorerStore((s) => s.motion);
  const region = useRegionDetail(regionId).data;
  const selected = articles.find((a) => a.article_id === articleId) ?? null;

  // El mapa vive fuera de React: lee estos refs dentro de sus eventos.
  const motionRef = useRef<MotionPreset>(motion);
  const spinningRef = useRef(spinning);
  const spinStartRef = useRef(0);
  const spinStepRef = useRef<() => void>(() => undefined);
  const earthRef = useRef(earth);
  const lastInteractionRef = useRef(0);
  const levelRef = useRef<RegionLevel | null>(null);
  const selectedRef = useRef<Article | null>(selected);
  // Notas por id para el tooltip (el evento del mapa lee la versión vigente).
  const articlesByIdRef = useRef(new Map<number, Article>());

  useEffect(() => {
    motionRef.current = motion;
    selectedRef.current = selected;
  }, [motion, selected]);

  // --- Creación del mapa ---------------------------------------------------
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setupMapLibre();
    lastInteractionRef.current = performance.now();
    const intro = motionRef.current !== 'off';
    const map = new MapLibreMap({
      container,
      style: buildMapStyle(window.location.origin, earthRef.current),
      center: intro
        ? [INITIAL_CENTER[0] + INTRO_LNG_OFFSET_DEGREES, INITIAL_CENTER[1]]
        : INITIAL_CENTER,
      zoom: intro ? INTRO_FROM_ZOOM : INITIAL_ZOOM,
      bearing: GLOBE_BEARING,
      attributionControl: { compact: true },
    });
    map.addControl(new NavigationControl({ visualizePitch: true }), 'top-right');

    let introDone = !intro;
    const spinStep = () => {
      if (!spinningRef.current || !introDone) return;
      const ramp = Math.max(MIN_SPIN_RAMP, spinRamp(performance.now() - spinStartRef.current));
      const degrees = spinDegrees(map.getZoom()) * spinFactor(motionRef.current) * ramp;
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
        lastInteractionRef.current = performance.now();
        useExplorerStore.getState().setSpinning(false);
      });
    }

    map.on('load', () => {
      const size = 44;
      map.addImage(DASHED_RING_IMAGE, { width: size, height: size, data: dashedRingPixels(size) });
      map.addSource(NEWS_SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        cluster: true,
        clusterRadius: CLUSTER_RADIUS_PX,
        clusterMaxZoom: CLUSTER_MAX_ZOOM,
        promoteId: 'id',
      });
      for (const layer of newsLayers()) map.addLayer(layer);
      setReady(true);
      if (intro) {
        map.once('moveend', () => {
          introDone = true;
          spinStartRef.current = performance.now();
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

    // El fondo de universo y la ficha siguen a la cámara.
    let calloutFrame = 0;
    const onMove = () => {
      const center = map.getCenter();
      useCameraStore.getState().setView({
        lng: center.lng,
        lat: center.lat,
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
      });
      cancelAnimationFrame(calloutFrame);
      calloutFrame = requestAnimationFrame(() => {
        const loc = selectedRef.current?.primary_location;
        const lng = loc?.lon ?? null;
        const lat = loc?.lat ?? null;
        if (lng === null || lat === null) return;
        const point = map.project([lng, lat]);
        setCallout((current) =>
          current?.articleId === selectedRef.current?.article_id
            ? current && {
                ...current,
                x: point.x,
                y: point.y,
                visible: isOnVisibleSide(center, { lng, lat }),
              }
            : current,
        );
      });
    };
    map.on('move', onMove);
    onMove();

    // Hover: primero las notas, luego las regiones.
    let hovered: FeatureIdentifier | null = null;
    const clearHover = () => {
      if (hovered) map.setFeatureState(hovered, { hover: false });
      hovered = null;
    };
    const firstAt = (point: { x: number; y: number }, layers: string[]) =>
      map
        .queryRenderedFeatures([point.x, point.y], {
          layers: layers.filter((id) => map.getLayer(id)),
        })
        .at(0);
    map.on('mousemove', (event) => {
      const news = firstAt(event.point, NEWS_LAYERS);
      const feature = news ?? firstAt(event.point, INTERACTIVE_LAYERS);
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
      if (hovered === null || hovered.id !== key.id || hovered.source !== key.source) {
        clearHover();
        map.setFeatureState(key, { hover: true });
        hovered = key;
      }
      map.getCanvas().style.cursor = 'pointer';
      if (news) {
        const count = news.properties.point_count as number | undefined;
        const article = articlesByIdRef.current.get(Number(news.id));
        setTooltip({
          x: event.point.x,
          y: event.point.y,
          label: count ? `${String(count)} notas` : (article?.title ?? 'Nota'),
          detail: count ? 'clic para acercar' : (article?.primary_location?.place ?? ''),
        });
        return;
      }
      const props = feature.properties as RegionFeatureProps;
      setTooltip({
        x: event.point.x,
        y: event.point.y,
        label: featureLabel(props) ?? '',
        detail: typeof props.code === 'string' ? props.code : '',
      });
    });
    map.on('mouseout', () => {
      clearHover();
      setTooltip(null);
    });
    map.on('click', (event) => {
      const news = firstAt(event.point, NEWS_LAYERS);
      const store = useExplorerStore.getState();
      if (news?.properties.cluster) {
        // Grupo: acercarse hasta que se separen sus notas.
        const source = map.getSource<GeoJSONSource>(NEWS_SOURCE);
        const coordinates = (news.geometry as { coordinates: [number, number] }).coordinates;
        void source?.getClusterExpansionZoom(Number(news.properties.cluster_id)).then((zoom) => {
          map.easeTo({
            center: coordinates,
            zoom,
            duration: flyDurationMs(
              cameraOf(map),
              { lng: coordinates[0], lat: coordinates[1], zoom },
              'region',
              motionRef.current,
            ),
            easing: easeInOutCubic,
          });
        });
        return;
      }
      if (news?.id !== undefined) {
        store.selectArticle(Number(news.id));
        return;
      }
      const region = firstAt(event.point, INTERACTIVE_LAYERS);
      if (region?.id !== undefined) store.selectRegion(Number(region.id));
    });

    // Diagnóstico: con ?depurar en la URL, el mapa queda en window.__mapa.
    if (new URLSearchParams(window.location.search).has('depurar')) {
      (window as unknown as { __mapa?: MapLibreMap }).__mapa = map;
    }
    // Si el contenedor no tenía tamaño al crear el mapa, se reajusta después.
    const observer = new ResizeObserver(() => {
      map.resize();
      setViewport({ width: container.clientWidth, height: container.clientHeight });
    });
    observer.observe(container);
    mapRef.current = map;
    return () => {
      observer.disconnect();
      cancelAnimationFrame(calloutFrame);
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
    // El mapa se crea una sola vez; lo demás llega por refs y efectos.
  }, []);

  useEffect(() => {
    articlesByIdRef.current = new Map(articles.map((article) => [article.article_id, article]));
  }, [articles]);

  // --- Día / noche ---------------------------------------------------------
  useEffect(() => {
    earthRef.current = earth;
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const mode of ['night', 'day'] as const) {
      map.setLayoutProperty(EARTH_LAYER[mode], 'visibility', mode === earth ? 'visible' : 'none');
    }
  }, [earth, ready]);

  // --- Giro ----------------------------------------------------------------
  useEffect(() => {
    spinningRef.current = spinning;
    const map = mapRef.current;
    if (!spinning || !ready || !map) return;
    spinStartRef.current = performance.now();
    if (spinDegrees(map.getZoom()) === 0) {
      // De cerca no se gira: primero se aleja a la vista de globo.
      map.easeTo({
        center: [map.getCenter().lng, INITIAL_CENTER[1]],
        zoom: INITIAL_ZOOM,
        pitch: 0,
        bearing: GLOBE_BEARING,
        duration: flyDurationMs(
          cameraOf(map),
          { lng: map.getCenter().lng, lat: INITIAL_CENTER[1], zoom: INITIAL_ZOOM },
          'up',
          motionRef.current,
        ),
        easing: easeInOutCubic,
      });
    } else if (!map.isMoving()) {
      spinStepRef.current();
    }
  }, [spinning, ready]);

  // Reanudar el giro tras un rato sin uso, si no hay nada elegido.
  useEffect(() => {
    if (spinning || regionId !== null || articleId !== null || motion === 'off') return;
    const timer = window.setInterval(() => {
      if (performance.now() - lastInteractionRef.current > IDLE_RESUME_MS) {
        useExplorerStore.getState().setSpinning(true);
      }
    }, IDLE_CHECK_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [spinning, regionId, articleId, motion]);

  // --- Región elegida: resaltar y volar -------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || region?.id !== regionId) return;
    const source = SOURCE_BY_LEVEL[region.level];
    const key: FeatureIdentifier = { source, sourceLayer: source, id: region.id };
    map.setFeatureState(key, { selected: true });
    const previous = levelRef.current;
    const kind =
      previous !== null && LEVEL_ORDER.indexOf(region.level) < LEVEL_ORDER.indexOf(previous)
        ? 'up'
        : 'region';
    levelRef.current = region.level;
    const [west, south, east, north] = region.bbox;
    const isPoint = west === east && south === north;
    const camera = isPoint
      ? { center: { lng: west, lat: south }, zoom: FLY_MAX_ZOOM.locality }
      : map.cameraForBounds(
          [
            [west, south],
            [east, north],
          ] as LngLatBoundsLike,
          {
            padding: FLY_PADDING,
            maxZoom: FLY_MAX_ZOOM[region.level],
          },
        );
    if (camera?.center !== undefined && camera.zoom !== undefined) {
      const { lng, lat } = LngLat.convert(camera.center);
      const center = { lng, lat };
      map.flyTo({
        center: [center.lng, center.lat],
        zoom: camera.zoom,
        bearing: REGION_BEARING,
        pitch: flyPitch(region.level),
        curve: FLY_CURVE,
        duration: flyDurationMs(
          cameraOf(map),
          { ...center, zoom: camera.zoom },
          kind,
          motionRef.current,
        ),
        essential: false,
      });
    }
    return () => {
      if (mapRef.current === map) map.setFeatureState(key, { selected: false });
    };
  }, [region, regionId, ready]);

  // --- Resultados: datos y aparición en cascada --------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const geojson = newsFeatures(articles, colors);
    void map.getSource<GeoJSONSource>(NEWS_SOURCE)?.setData(geojson);
    const timers = geojson.features.map((feature, index) =>
      window.setTimeout(
        () => {
          map.setFeatureState({ source: NEWS_SOURCE, id: feature.id }, { shown: true });
        },
        staggerDelayMs(index, geojson.features.length, motionRef.current),
      ),
    );
    return () => {
      for (const timer of timers) window.clearTimeout(timer);
    };
  }, [articles, colors, ready]);

  // --- Nota elegida: latido, vuelo y ficha -----------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setFilter('news-pulse', selectedFilter(selected?.article_id ?? null));
    const loc = selected?.primary_location;
    const lng = loc?.lon ?? null;
    const lat = loc?.lat ?? null;
    if (selected === null || lng === null || lat === null) return;
    const coarse = loc?.precision === 'state' || loc?.precision === 'country';
    const zoom = Math.max(map.getZoom(), coarse ? ARTICLE_ZOOM_COARSE : ARTICLE_ZOOM_PRECISE);
    const target = { lng, lat, zoom };
    // La ficha aparece cuando la cámara llega (no persigue al punto en vuelo).
    map.once('moveend', () => {
      const point = map.project([target.lng, target.lat]);
      setCallout({ articleId: selected.article_id, x: point.x, y: point.y, visible: true });
    });
    map.flyTo({
      center: [target.lng, target.lat],
      zoom,
      offset: ARTICLE_OFFSET,
      pitch: flyPitch('article'),
      bearing: REGION_BEARING,
      curve: FLY_CURVE,
      duration: flyDurationMs(cameraOf(map), target, 'region', motionRef.current),
      essential: false,
    });

    // Latido a 30 fps (sin animación: anillo fijo).
    if (motionRef.current === 'off') return;
    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (now - last < PULSE_FRAME_MS) return;
      last = now;
      const { radius, opacity } = pulseStyle(pulsePhase(now));
      map.setPaintProperty('news-pulse', 'circle-radius', radius);
      map.setPaintProperty('news-pulse', 'circle-stroke-opacity', opacity);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
    };
  }, [selected, ready]);

  // Alto real de la ficha (cambia con el largo del resumen) para acomodarla.
  const calloutShown = callout?.visible === true && callout.articleId === articleId;
  useEffect(() => {
    const card = cardRef.current;
    if (!calloutShown || !card) return;
    const observer = new ResizeObserver(() => {
      setCardHeight(card.offsetHeight);
    });
    observer.observe(card);
    return () => {
      observer.disconnect();
    };
  }, [calloutShown]);

  // Esc cierra la ficha.
  useEffect(() => {
    if (articleId === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') useExplorerStore.getState().selectArticle(null);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [articleId]);

  // Lugar de la ficha: nunca se sale del mapa (map/newsLayers.ts).
  const placement = (point: { x: number; y: number }) =>
    calloutPlacement(point, { width: CALLOUT_WIDTH, height: cardHeight }, viewport);

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" aria-label="Globo interactivo" />
      {tooltip?.label && (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-10 max-w-xs -translate-x-1/2 -translate-y-[calc(100%+14px)] rounded-lg border border-white/10 bg-slate-950/90 px-3 py-1.5 text-sm shadow-xl shadow-black/50 backdrop-blur"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <span className="font-medium text-slate-100">{tooltip.label}</span>
          {tooltip.detail && <span className="ml-2 text-xs text-slate-400">{tooltip.detail}</span>}
        </div>
      )}
      {selected && calloutShown && (
        <>
          <svg
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 z-10 h-full w-full"
          >
            <line
              x1={callout.x}
              y1={callout.y}
              x2={placement(callout).lineX}
              y2={placement(callout).lineY}
              stroke="rgba(226,232,240,0.7)"
              strokeWidth={1.2}
            />
            <circle cx={callout.x} cy={callout.y} r={3} fill="#F8FAFC" />
          </svg>
          {/* Capa exterior: posición. Capa interior: animación de entrada. */}
          <div
            ref={cardRef}
            className="absolute z-20"
            style={{
              left: placement(callout).left,
              top: placement(callout).top,
              width: CALLOUT_WIDTH,
            }}
          >
            <div className={`${GLASS} animate-[fadeIn_200ms_ease-out] p-4`}>
              <NewsCard
                article={selected}
                colors={colors}
                onClose={() => {
                  useExplorerStore.getState().selectArticle(null);
                }}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/** Dónde está la cámara (para calcular la duración de un vuelo). */
function cameraOf(map: MapLibreMap) {
  const center = map.getCenter();
  return { lng: center.lng, lat: center.lat, zoom: map.getZoom() };
}
