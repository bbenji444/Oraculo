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
  keepNewsLayers,
  NEWS_SOURCE,
  newsFeatures,
  newsLayers,
  pulseStyle,
  selectedFilter,
  CLUSTER_MAX_ZOOM,
  CLUSTER_RADIUS_PX,
  calloutPlacement,
  STACK_LIMIT,
  stackedIds,
} from '../../map/newsLayers';
import { collapseAttributionOnStart } from '../../map/attribution';
import { smoothFlights } from '../../map/flight';
import {
  articleOffset,
  articleZoom,
  calloutWidth,
  flyPadding,
  globeCamera,
  type ScreenSize,
} from '../../map/framing';
import { setupMapLibre } from '../../map/setup';
import { GLOBE_BEARING, REGION_BEARING, SPIN_STEP_MS, spinDegrees } from '../../map/spin';
import {
  buildMapStyle,
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
import { NewsStack } from './NewsStack';
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

/** Lista abierta de las notas de un mismo lugar (grupo o puntos encimados). */
interface Stack {
  lng: number;
  lat: number;
  x: number;
  y: number;
  ids: number[];
  total: number;
  /** Zoom que separa el grupo; `null` si son notas en el mismo punto. */
  expandZoom: number | null;
  /** `articleRequest` al abrirla: elegir otra nota (desde donde sea) la cierra. */
  request: number;
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
// Curva de vuelo de MapLibre: 1.42 es su valor por defecto (aleja y acerca
// sin marear); un poco más alta da más sensación de "despegue".
const FLY_CURVE = 1.5;
// Lista de un grupo: 20 rem de ancho; alto según cuántas notas (encabezado +
// renglones de dos líneas), con tope y desplazamiento dentro.
const STACK_WIDTH = 320;
const STACK_BASE_HEIGHT = 56;
const STACK_ROW_HEIGHT = 56;
const STACK_MAX_HEIGHT = 380;
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

type FlyFn = ReturnType<typeof smoothFlights>;

export function ExploreGlobe({ articles, colors }: ExploreGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const [callout, setCallout] = useState<Callout | null>(null);
  const [stack, setStack] = useState<Stack | null>(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [cardHeight, setCardHeight] = useState(CALLOUT_INITIAL_HEIGHT);
  const cardRef = useRef<HTMLDivElement>(null);

  const regionId = useExplorerStore((s) => s.regionId);
  const articleId = useExplorerStore((s) => s.articleId);
  const articleRequest = useExplorerStore((s) => s.articleRequest);
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
  // Vuela con menos resolución y la recupera al aterrizar (map/flight.ts).
  const flyRef = useRef<FlyFn>((_duration, start) => {
    start();
  });

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
    // Créditos plegados al iniciar: solo el botón "i" (ver map/attribution.ts).
    const stopAttribution = collapseAttributionOnStart(map.getContainer());
    const fly = smoothFlights(map, () => window.devicePixelRatio);
    flyRef.current = fly;

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
    // Arrastrar o girar la rueda cierra la lista de un grupo: ya no apunta a nada.
    map.on('dragstart', () => {
      setStack(null);
    });
    map.on('wheel', () => {
      setStack(null);
    });

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
        fly(INTRO_DURATION_MS, () => {
          map.easeTo({
            center: INITIAL_CENTER,
            zoom: INITIAL_ZOOM,
            duration: INTRO_DURATION_MS,
            easing: easeOutQuint,
          });
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
        setStack((current) => {
          if (!current) return current;
          const point = map.project([current.lng, current.lat]);
          return { ...current, x: point.x, y: point.y };
        });
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
    const openStack = (
      coordinates: [number, number],
      ids: number[],
      total: number,
      expandZoom: number | null,
    ) => {
      const [lng, lat] = coordinates;
      const point = map.project(coordinates);
      const request = useExplorerStore.getState().articleRequest;
      setStack({ lng, lat, x: point.x, y: point.y, ids, total, expandZoom, request });
    };
    map.on('click', (event) => {
      const news = firstAt(event.point, NEWS_LAYERS);
      const store = useExplorerStore.getState();
      if (news?.properties.cluster) {
        // Grupo: la lista dice qué notas son; "Acercar" las separa en el mapa.
        const source = map.getSource<GeoJSONSource>(NEWS_SOURCE);
        if (news.geometry.type !== 'Point') return;
        const coordinates = news.geometry.coordinates as [number, number];
        const clusterId = Number(news.properties.cluster_id);
        const total = Number(news.properties.point_count);
        if (!source) return;
        void Promise.all([
          source.getClusterLeaves(clusterId, STACK_LIMIT, 0),
          source.getClusterExpansionZoom(clusterId),
        ]).then(([leaves, zoom]) => {
          openStack(coordinates, stackedIds(leaves), total, zoom);
        });
        return;
      }
      // Notas encimadas en el mismo punto (p. ej. varias "solo por estado").
      const stacked = stackedIds(
        map.queryRenderedFeatures([event.point.x, event.point.y], {
          layers: NEWS_LAYERS.filter((id) => map.getLayer(id)),
        }),
      );
      if (news?.geometry.type === 'Point' && stacked.length > 1) {
        const coordinates = news.geometry.coordinates as [number, number];
        openStack(coordinates, stacked, stacked.length, null);
        return;
      }
      if (news?.id !== undefined) {
        setStack(null);
        store.selectArticle(Number(news.id));
        return;
      }
      setStack(null);
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
      stopAttribution();
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
  // Cambia la textura de la Tierra y también los colores del mapa de calles
  // (claro de día, oscuro de noche). MapLibre aplica solo las diferencias y
  // keepNewsLayers conserva los puntos de noticias, que no vienen en el estilo.
  useEffect(() => {
    const previous = earthRef.current;
    earthRef.current = earth;
    const map = mapRef.current;
    if (!map || !ready || previous === earth) return;
    map.setStyle(buildMapStyle(window.location.origin, earth), {
      diff: true,
      transformStyle: keepNewsLayers,
    });
  }, [earth, ready]);

  // --- Giro ----------------------------------------------------------------
  useEffect(() => {
    spinningRef.current = spinning;
    const map = mapRef.current;
    if (!spinning || !ready || !map) return;
    spinStartRef.current = performance.now();
    if (spinDegrees(map.getZoom()) === 0) {
      // De cerca no se gira: primero se aleja a la vista de globo.
      const duration = flyDurationMs(
        cameraOf(map),
        { lng: map.getCenter().lng, lat: INITIAL_CENTER[1], zoom: INITIAL_ZOOM },
        'up',
        motionRef.current,
      );
      flyRef.current(duration, () => {
        map.easeTo({
          center: [map.getCenter().lng, INITIAL_CENTER[1]],
          zoom: INITIAL_ZOOM,
          pitch: 0,
          bearing: GLOBE_BEARING,
          duration,
          easing: easeInOutCubic,
        });
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
    // Encuadre de la parte principal (sin territorios lejanos), medido sobre
    // la esfera y no en el mapa plano (map/framing.ts).
    const box = region.focus_bbox;
    const padding = flyPadding(screenOf(map), useExplorerStore.getState().panelOpen);
    // Una localidad sin polígono es un punto: se acerca al zoom de localidad.
    const isPoint = box[0] === box[2] && box[1] === box[3];
    const maxZoom = FLY_MAX_ZOOM[isPoint ? 'locality' : region.level];
    const camera = globeCamera(box, screenOf(map), padding, maxZoom);
    const [lng, lat] = camera.center;
    const { zoom } = camera;
    const duration = flyDurationMs(cameraOf(map), { lng, lat, zoom }, kind, motionRef.current);
    flyRef.current(duration, () => {
      map.flyTo({
        center: camera.center,
        zoom,
        bearing: REGION_BEARING,
        pitch: flyPitch(region.level),
        curve: FLY_CURVE,
        duration,
        essential: false,
      });
    });
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
  // Se vuelve a volar cada vez que se elige una nota, aunque sea la misma
  // (`articleRequest`), y no cuando solo se recarga la lista.
  const selectedId = selected?.article_id ?? null;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setFilter('news-pulse', selectedFilter(selectedId));
    const article = selectedRef.current;
    const loc = article?.primary_location;
    const lng = loc?.lon ?? null;
    const lat = loc?.lat ?? null;
    if (article === null || !loc || lng === null || lat === null) return;
    const zoom = articleZoom(loc.precision, lng, lat);
    // La ficha aparece cuando la cámara llega (no persigue al punto en vuelo).
    setCallout(null);
    const onArrive = () => {
      const point = map.project([lng, lat]);
      setCallout({ articleId: article.article_id, x: point.x, y: point.y, visible: true });
    };
    const duration = flyDurationMs(cameraOf(map), { lng, lat, zoom }, 'region', motionRef.current);
    flyRef.current(duration, () => {
      map.flyTo({
        center: [lng, lat],
        zoom,
        offset: articleOffset(screenOf(map)),
        pitch: flyPitch('article'),
        bearing: REGION_BEARING,
        curve: FLY_CURVE,
        duration,
        essential: false,
      });
    });
    // Se escucha el aterrizaje hasta que el vuelo arrancó: si interrumpió otro
    // vuelo, ese "terminó" no es el de esta nota. Sin animación, ya llegó.
    if (map.isMoving()) map.once('moveend', onArrive);
    else onArrive();

    // Latido a 30 fps (sin animación: anillo fijo).
    if (motionRef.current === 'off') {
      return () => {
        map.off('moveend', onArrive);
      };
    }
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
      map.off('moveend', onArrive);
      cancelAnimationFrame(frame);
    };
  }, [selectedId, articleRequest, ready]);

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
  const cardWidth = calloutWidth(viewport);
  const placement = (point: { x: number; y: number }) =>
    calloutPlacement(point, { width: cardWidth, height: cardHeight }, viewport);

  // Lista de un grupo: las notas más recientes primero, junto al punto.
  const stackArticles = articles
    .filter((article) => stack?.ids.includes(article.article_id))
    .sort((a, b) => (b.published_at ?? '').localeCompare(a.published_at ?? ''));
  const stackPlacement =
    stack &&
    calloutPlacement(
      stack,
      {
        width: STACK_WIDTH,
        height: Math.min(
          STACK_MAX_HEIGHT,
          STACK_BASE_HEIGHT + stackArticles.length * STACK_ROW_HEIGHT,
        ),
      },
      viewport,
    );
  const zoomIntoStack = () => {
    const map = mapRef.current;
    if (!map || stack?.expandZoom == null) return;
    const { lng, lat, expandZoom: zoom } = stack;
    setStack(null);
    const duration = flyDurationMs(cameraOf(map), { lng, lat, zoom }, 'region', motionRef.current);
    flyRef.current(duration, () => {
      map.easeTo({ center: [lng, lat], zoom, duration, easing: easeInOutCubic });
    });
  };

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
              width: cardWidth,
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
      {stack?.request === articleRequest && stackPlacement && (
        <div
          className="absolute z-30 animate-[fadeIn_150ms_ease-out]"
          style={{ left: stackPlacement.left, top: stackPlacement.top }}
        >
          <NewsStack
            articles={stackArticles}
            colors={colors}
            total={stack.total}
            onSelect={(articleId) => {
              setStack(null);
              useExplorerStore.getState().selectArticle(articleId);
            }}
            onZoom={stack.expandZoom === null ? undefined : zoomIntoStack}
            onClose={() => {
              setStack(null);
            }}
          />
        </div>
      )}
    </div>
  );
}

/** Tamaño del mapa en pantalla (para encuadrar sin taparlo con los paneles). */
function screenOf(map: MapLibreMap): ScreenSize {
  const container = map.getContainer();
  return { width: container.clientWidth, height: container.clientHeight };
}

/** Dónde está la cámara (para calcular la duración de un vuelo). */
function cameraOf(map: MapLibreMap) {
  const center = map.getCenter();
  return { lng: center.lng, lat: center.lat, zoom: map.getZoom() };
}
