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
import { type PointerEvent as ReactPointerEvent, useEffect, useRef, useState } from 'react';

import { useRegionDetail } from '../../hooks/useRegions';
import {
  easeInOutCubic,
  easeOutCubic,
  flyDurationMs,
  flyPitch,
  idleResumeMs,
  INTRO_DURATION_MS,
  INTRO_FROM_ZOOM,
  INTRO_LNG_OFFSET_DEGREES,
  introSpin,
  type MotionPreset,
  pulsePhase,
  spinFactor,
  spinRamp,
  SPIN_RAMP_MS,
  staggerDelayMs,
} from '../../map/motion';
import {
  DASHED_RING_IMAGE,
  dashedRingPixels,
  hasMapPoint,
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
  pointCoordinates,
  STACK_LIMIT,
  stackedIds,
} from '../../map/newsLayers';
import { collapseAttributionOnStart } from '../../map/attribution';
import { smoothFlights } from '../../map/flight';
import {
  articleOffset,
  auraOpacity,
  ringAround,
  articleZoom,
  calloutWidth,
  columnInTheWay,
  flyPadding,
  fitZoom,
  frameZoom,
  overviewPadding,
  GLOBE_FRAME_MS,
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
import { CASES_DOT_LAYER } from './CasesOnGlobe';
import { GlobeUnavailable } from './GraphicsBoundary';
import { GLASS } from './ui';

interface ExploreGlobeProps {
  articles: readonly Article[];
  colors: ReadonlyMap<number, string>;
  /** Avisa cuando el mapa está listo (o se quita), para el muro y «Mis casos» (9.6). */
  onMap?: (map: MapLibreMap | null) => void;
  /**
   * Si Explorar está a la vista. En otra pestaña del sistema el globo se queda
   * montado (no se destruye ni se vuelve a crear) pero deja de girar, así no
   * ocupa la tarjeta de video.
   */
  active?: boolean;
  /**
   * Píxeles que ocupan los paneles a la izquierda y a la derecha. El centro
   * del globo se corre a la parte libre con una animación, y sin paneles se
   * centra y crece un poco (Benji, 27/10/2026; map/framing.ts).
   */
  insetLeft?: number;
  insetRight?: number;
  /**
   * Píxeles que ocupa una consola abajo (diseño «Centro de mando»): el globo
   * flota encima de ella.
   */
  insetBottom?: number;
  /** Si el globo se encuadra debajo del encabezado y no detrás de él. */
  clearHeader?: boolean;
}

interface Insets {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/**
 * Radio del globo en pantalla, en píxeles. Un punto a 90° del centro de la
 * cámara cae justo en el borde del globo; su distancia al centro es el radio.
 */
function globeRadiusPx(map: MapLibreMap): number {
  const center = map.getCenter();
  const middle = map.project(center);
  const edge = map.project([center.lng + 90, 0]);
  return Math.hypot(edge.x - middle.x, edge.y - middle.y);
}

function sameInsets(a: Insets, b: Insets): boolean {
  return a.left === b.left && a.right === b.right && a.top === b.top && a.bottom === b.bottom;
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

// Distancia de la ficha de una nota sin lugar al borde de arriba del espacio
// libre, en píxeles: debajo de los controles del globo.
const UNPLACED_CARD_TOP_PX = 72;
// En el Centro de mando, los controles del globo van arriba a la izquierda,
// debajo del encabezado: la ficha de una nota empieza debajo de ellos para no
// taparlos (alto de su renglón de botones más su margen, en píxeles).
const MANDO_CONTROLS_PX = 60;

interface Callout {
  // Nota a la que pertenece: si cambia la nota elegida, esta ficha ya no se muestra.
  articleId: number;
  x: number;
  y: number;
  visible: boolean;
}

// Vista de «inicio»: México con el eje inclinado (map/spin.ts). Es a donde
// vuelven «Limpiar globo» y el botón de inicio.
const INITIAL_CENTER: [number, number] = [-102, 23.5];
// Un poco más cerca que al principio (1.8): el globo abarca más pantalla al
// abrir el sistema (Benji, 27/10/2026).
const INITIAL_ZOOM = 2;
// Al abrir el sistema la entrada termina sobre el Atlántico (Benji, 26/10/2026)
// y desde ahí el giro normal trae a América y a México a la vista.
const INTRO_CENTER: [number, number] = [-35, 20];
// «Nueva consulta» y «Ajustar consulta» vuelven a esa misma vista y la ponen a
// girar al instante (Benji, 28/10/2026).
const ATLANTIC_CENTER = INTRO_CENTER;
// «Acercar» un grupo: 1.5 niveles más que donde se separa, sin pasar de 15.
const STACK_EXTRA_ZOOM = 1.5;
const MAX_STACK_ZOOM = 15;
// Si el navegador quita los gráficos 3D y no los devuelve en este tiempo, se
// avisa con «Recargar». Casi siempre vuelven en menos de un segundo y MapLibre
// redibuja solo; el aviso es para cuando Chrome ya los bloqueó.
const GRAPHICS_LOST_NOTICE_MS = 6000;
// Curva de vuelo de MapLibre: 1.42 es su valor por defecto (aleja y acerca
// sin marear); un poco más alta da más sensación de "despegue".
const FLY_CURVE = 1.5;
// Vuelo a una nota: más arco (se aleja un poco y cae sobre el lugar), para que
// se sienta el viaje aunque la nota esté cerca (Benji: «más dinámicos»).
const ARTICLE_FLY_CURVE = 1.9;
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
const MS_PER_SECOND = 1000;
// Desvanecido de los nombres del mapa al aparecer (MapLibre usa 300 ms).
const LABEL_FADE_MS = 120;
// Aire mínimo entre la ficha arrastrada y la orilla del mapa.
const CARD_DRAG_MARGIN = 12;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

/**
 * Lo que tapa el encabezado arriba del mapa, en pixeles (`--header-h`): el
 * mapa se dibuja también detrás de él y la ficha no debe subir ahí.
 */
function headerInsetPx(): number {
  const root = document.documentElement;
  const value = getComputedStyle(root).getPropertyValue('--header-h').trim();
  const rem = Number.parseFloat(getComputedStyle(root).fontSize) || 16;
  if (value.endsWith('rem')) return Number.parseFloat(value) * rem;
  if (value.endsWith('px')) return Number.parseFloat(value);
  return 0;
}
// Eventos de la persona que detienen el giro.
const USER_EVENTS = ['mousedown', 'touchstart', 'wheel', 'dragstart'] as const;
const NEWS_LAYERS = ['news-point', 'news-coarse', 'news-cluster'];
const LEVEL_ORDER: RegionLevel[] = ['country', 'state', 'municipality', 'locality'];

type FlyFn = ReturnType<typeof smoothFlights>;

// Aureola: 1.4 veces el diámetro del globo (el degradado empieza en su borde).
const AURA_SCALE = 2.8;
// Brillo del Sol: tamaño respecto al radio, distancia al centro (justo fuera
// del borde) y ángulo (arriba a la izquierda, en radianes).
const SUN_GLARE_SCALE = 1.25;
const SUN_DISTANCE = 1.02;
const SUN_ANGLE = (-140 * Math.PI) / 180;
// Búsqueda del borde: 16 direcciones y anillos de 60° a 90° del centro cada 2°
// (con la cámara inclinada el borde visible queda antes de los 90°). Son ~250
// proyecciones por cuadro: medido, no se nota.
const LIMB_DIRECTIONS = 16;
const LIMB_FROM_DEG = 60;
const LIMB_TO_DEG = 90;
const LIMB_STEP_DEG = 2;

/**
 * Dónde se ve el globo en pantalla: centro y radio de su silueta.
 *
 * MapLibre no lo expone. Se proyectan anillos de puntos cada vez más lejos del
 * centro y, en cada dirección, se queda el más lejano (ese es el borde).
 */
function globeOutline(map: MapLibreMap): { x: number; y: number; radius: number } {
  const center = map.getCenter();
  const origin = map.project(center);
  const edge = Array.from({ length: LIMB_DIRECTIONS }, () => ({ d: 0, x: origin.x, y: origin.y }));
  for (let distance = LIMB_FROM_DEG; distance <= LIMB_TO_DEG; distance += LIMB_STEP_DEG) {
    ringAround([center.lng, center.lat], distance, LIMB_DIRECTIONS).forEach((point, i) => {
      const p = map.project(point);
      const d = Math.hypot(p.x - origin.x, p.y - origin.y);
      const best = edge[i];
      if (best && Number.isFinite(d) && d > best.d) edge[i] = { d, x: p.x, y: p.y };
    });
  }
  const x = edge.reduce((sum, p) => sum + p.x, 0) / edge.length;
  const y = edge.reduce((sum, p) => sum + p.y, 0) / edge.length;
  const radius = edge.reduce((sum, p) => sum + Math.hypot(p.x - x, p.y - y), 0) / edge.length;
  return { x, y, radius };
}

/**
 * Pone la aureola y el brillo del Sol alrededor del globo, donde esté y del
 * tamaño que tenga; se apagan al acercarse (ya no se ve el borde).
 */
function placeAura(map: MapLibreMap, aura: HTMLElement | null, sun: HTMLElement | null): void {
  if (!aura || !sun) return;
  const opacity = auraOpacity(map.getZoom());
  aura.style.opacity = String(opacity);
  sun.style.opacity = String(opacity);
  // Apagadas no hace falta buscar el borde (y de cerca ni se ve).
  if (opacity === 0) return;
  const { x, y, radius } = globeOutline(map);
  const size = radius * AURA_SCALE;
  Object.assign(aura.style, {
    left: `${String(x - size / 2)}px`,
    top: `${String(y - size / 2)}px`,
    width: `${String(size)}px`,
    height: `${String(size)}px`,
  });
  // El Sol se asoma arriba a la izquierda del borde, como al amanecer.
  const glare = radius * SUN_GLARE_SCALE;
  const sunX = x + Math.cos(SUN_ANGLE) * radius * SUN_DISTANCE;
  const sunY = y + Math.sin(SUN_ANGLE) * radius * SUN_DISTANCE;
  Object.assign(sun.style, {
    left: `${String(sunX - glare / 2)}px`,
    top: `${String(sunY - glare / 2)}px`,
    width: `${String(glare)}px`,
    height: `${String(glare)}px`,
  });
}

export function ExploreGlobe({
  articles,
  colors,
  onMap,
  active = true,
  insetLeft = 0,
  insetRight = 0,
  insetBottom = 0,
  clearHeader = false,
}: ExploreGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const auraRef = useRef<HTMLDivElement>(null);
  const sunRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  // La entrada desde el espacio terminó: hasta entonces nadie más mueve la cámara
  // (el muro de la 9.6 volaría y la entrada lo pisaría).
  const [introFinished, setIntroFinished] = useState(false);
  // Sube cuando aterriza un vuelo que dejó pendiente el encuadre de los paneles.
  const [framePending, setFramePending] = useState(0);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const [callout, setCallout] = useState<Callout | null>(null);
  const [stack, setStack] = useState<Stack | null>(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0, top: 0 });
  // Cuánto se movió a mano la ficha de la nota (arrastrándola). Va con su
  // nota: al elegir otra, la ficha vuelve a su lugar.
  const [drag, setDrag] = useState({ articleId: null as number | null, dx: 0, dy: 0 });
  const dragStartRef = useRef<{ x: number; y: number; dx: number; dy: number } | null>(null);
  const [cardHeight, setCardHeight] = useState(CALLOUT_INITIAL_HEIGHT);
  const [graphicsLost, setGraphicsLost] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const regionId = useExplorerStore((s) => s.regionId);
  const articleId = useExplorerStore((s) => s.articleId);
  const articleRequest = useExplorerStore((s) => s.articleRequest);
  const spinning = useExplorerStore((s) => s.spinning);
  const earth = useExplorerStore((s) => s.earth);
  const motion = useExplorerStore((s) => s.motion);
  const wallCaseId = useExplorerStore((s) => s.wallCaseId);
  const homeRequest = useExplorerStore((s) => s.homeRequest);
  const region = useRegionDetail(regionId).data;
  const selected = articles.find((a) => a.article_id === articleId) ?? null;

  // El mapa vive fuera de React: lee estos refs dentro de sus eventos.
  const motionRef = useRef<MotionPreset>(motion);
  const spinningRef = useRef(spinning);
  const activeRef = useRef(active);
  const spinStartRef = useRef(0);
  const spinStepRef = useRef<() => void>(() => undefined);
  const insetsRef = useRef<Insets>({
    left: insetLeft,
    right: insetRight,
    top: 0,
    bottom: insetBottom,
  });
  // Para crear el mapa ya encuadrado; los cambios llegan por el efecto de encuadre.
  const clearHeaderRef = useRef(clearHeader);
  // Si ya se ajustó el globo al espacio libre al terminar la entrada (diseño 3).
  const fittedRef = useRef(false);
  // Vista general (el globo entero, sin región ni nota elegida). Solo ahí el
  // Centro de mando ajusta el zoom al espacio libre: antes, al llegar a un país
  // (zoom < 3) cualquier cambio de la consola lo volvía a alejar y parecía que
  // el globo no hacía zoom a la región (Benji, 27/10/2026).
  const overviewRef = useRef(true);
  // Márgenes de la cámara: en la vista general del Centro de mando el globo
  // pasa por detrás de la consola (map/framing.ts, overviewPadding).
  const cameraInsets = (insets: Insets): Insets =>
    clearHeaderRef.current && overviewRef.current ? overviewPadding(insets) : insets;
  // Si el globo está acercado por no tener paneles (frameZoom).
  const expandedRef = useRef(false);
  // Mientras se corre el encuadre, el giro espera: el corrimiento ya lo incluye.
  const framingRef = useRef(false);
  // Si hay un vuelo pedido en curso (a una nota o región): el encuadre no lo
  // interrumpe, solo cambia el margen de la cámara.
  const flyingRef = useRef(false);
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
        ? [INTRO_CENTER[0] + INTRO_LNG_OFFSET_DEGREES, INTRO_CENTER[1]]
        : INITIAL_CENTER,
      zoom: intro ? INTRO_FROM_ZOOM : INITIAL_ZOOM,
      bearing: GLOBE_BEARING,
      attributionControl: { compact: true },
      // Los nombres aparecen casi de inmediato al llegar a una nota (MapLibre
      // los desvanece en 300 ms por defecto y se sentía que cargaba lento).
      fadeDuration: LABEL_FADE_MS,
    });
    // El encuadre de los paneles desde el principio: la entrada ya llega corrida.
    if (clearHeaderRef.current) insetsRef.current = { ...insetsRef.current, top: headerInsetPx() };
    map.setPadding(cameraInsets(insetsRef.current));
    map.addControl(new NavigationControl({ visualizePitch: true }), 'top-right');
    // Créditos plegados al iniciar: solo el botón "i" (ver map/attribution.ts).
    const stopAttribution = collapseAttributionOnStart(map.getContainer());
    const fly = smoothFlights(map, () => window.devicePixelRatio);

    let introDone = !intro;
    let introFrame = 0;
    // Termina la entrada: desde aquí el globo es de la persona (o del giro).
    // `landed`: la entrada llegó sola a su lugar final (ya encuadrada), así no
    // hay un segundo ajuste después.
    const finishIntro = (landed = false) => {
      if (introDone) return;
      introDone = true;
      cancelAnimationFrame(introFrame);
      if (landed && clearHeaderRef.current) fittedRef.current = true;
      setIntroFinished(true);
    };
    // Zoom en el que debe terminar la entrada. En el Centro de mando es el que
    // llena el espacio libre (fitZoom): antes la entrada terminaba en el zoom
    // fijo y luego el globo se reacomodaba hacia arriba, y se veía un brinco
    // (Benji, 28/10/2026). El radio crece al doble por punto de zoom, así que
    // el resultado no depende del zoom de cada cuadro.
    const introTargetZoom = () => {
      if (!clearHeaderRef.current) return INITIAL_ZOOM;
      const padding = map.getPadding();
      const box = map.getContainer();
      return fitZoom(map.getZoom(), globeRadiusPx(map), {
        width: box.clientWidth - (padding.left ?? 0) - (padding.right ?? 0),
        height: box.clientHeight - (padding.top ?? 0) - (padding.bottom ?? 0),
      });
    };
    const spinStep = () => {
      if (!spinningRef.current || !introDone || !activeRef.current || framingRef.current) return;
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
    // Un vuelo pedido (elegir una nota, reabrir una búsqueda) termina la
    // entrada: si no, la entrada seguía moviendo la cámara cuadro a cuadro y
    // el globo nunca llegaba a la nota (27/10/2026).
    flyRef.current = (duration, start) => {
      finishIntro();
      fly(duration, () => {
        start();
        if (!map.isMoving()) return;
        flyingRef.current = true;
        map.once('moveend', () => {
          flyingRef.current = false;
          // Si volvió a la vista general, se ajusta al espacio libre.
          if (!fittedRef.current) setFramePending((count) => count + 1);
        });
      });
    };
    for (const type of USER_EVENTS) {
      map.on(type, () => {
        lastInteractionRef.current = performance.now();
        // Si toca el globo durante la entrada, la entrada se detiene ahí.
        finishIntro();
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

    let lostTimer = 0;
    map.on('webglcontextlost', () => {
      window.clearTimeout(lostTimer);
      lostTimer = window.setTimeout(() => {
        setGraphicsLost(true);
      }, GRAPHICS_LOST_NOTICE_MS);
    });
    map.on('webglcontextrestored', () => {
      window.clearTimeout(lostTimer);
      setGraphicsLost(false);
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
        // La entrada gira desde el espacio y entrega su velocidad al giro
        // normal: frena parejo hasta llevar justo esa velocidad (introSpin) y
        // el giro sigue sin pausa y sin rampa (Benji, 27/10/2026).
        const from = map.getCenter();
        const fromZoom = map.getZoom();
        const distance = from.lng - INTRO_CENTER[0];
        const spinPerSecond =
          (spinDegrees(INITIAL_ZOOM) * spinFactor(motionRef.current) * MS_PER_SECOND) /
          SPIN_STEP_MS;
        const endSlope = (spinPerSecond * INTRO_DURATION_MS) / MS_PER_SECOND / distance;
        const startMs = performance.now();
        const stepIntro = (now: number) => {
          if (introDone) return;
          const t = Math.min(1, (now - startMs) / INTRO_DURATION_MS);
          const settle = easeOutCubic(t);
          map.jumpTo({
            center: [
              from.lng - distance * introSpin(t, endSlope),
              from.lat + (INTRO_CENTER[1] - from.lat) * settle,
            ],
            zoom: fromZoom + (introTargetZoom() - fromZoom) * settle,
          });
          if (t < 1) {
            introFrame = requestAnimationFrame(stepIntro);
            return;
          }
          finishIntro(true);
          // Ya va a toda velocidad: el giro empieza sin su rampa.
          spinStartRef.current = performance.now() - SPIN_RAMP_MS;
          spinStep();
        };
        introFrame = requestAnimationFrame(stepIntro);
      } else {
        setIntroFinished(true);
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
      // La aureola va en el mismo cuadro que el globo: si esperara al siguiente
      // se quedaría atrás (o quieta) mientras la cámara se mueve sin parar.
      placeAura(map, auraRef.current, sunRef.current);
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
      const store = useExplorerStore.getState();
      // Con el muro abierto, los clics son del muro (CaseWall), no de las regiones.
      if (store.wallCaseId !== null) return;
      // Un clic en «Mis casos» abre el muro (CasesOnGlobe), no elige la región de abajo.
      if (
        map.getLayer(CASES_DOT_LAYER) &&
        map.queryRenderedFeatures(event.point, { layers: [CASES_DOT_LAYER] }).length > 0
      ) {
        return;
      }
      const news = firstAt(event.point, NEWS_LAYERS);
      if (news?.properties.cluster) {
        // Grupo: la lista dice qué notas son; "Acercar" las separa en el mapa.
        const source = map.getSource<GeoJSONSource>(NEWS_SOURCE);
        // Como `unknown`: la forma la revisa pointCoordinates (ver newsLayers.ts).
        const geometry: unknown = news.geometry;
        const coordinates = pointCoordinates(geometry);
        if (!coordinates) return;
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
      const newsGeometry: unknown = news?.geometry;
      const newsPoint = pointCoordinates(newsGeometry);
      if (newsPoint && stacked.length > 1) {
        openStack(newsPoint, stacked, stacked.length, null);
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
      setViewport({
        width: container.clientWidth,
        height: container.clientHeight,
        top: headerInsetPx(),
      });
    });
    observer.observe(container);
    mapRef.current = map;
    return () => {
      observer.disconnect();
      stopAttribution();
      cancelAnimationFrame(calloutFrame);
      cancelAnimationFrame(introFrame);
      window.clearTimeout(lostTimer);
      map.remove();
      mapRef.current = null;
      setReady(false);
      setIntroFinished(false);
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

  // --- Pestaña a la vista -------------------------------------------------
  useEffect(() => {
    const returning = active && !activeRef.current;
    activeRef.current = active;
    const map = mapRef.current;
    // Solo al volver de otra pestaña: en la primera carga no hace falta, y
    // medir de nuevo cortaba la entrada desde el espacio y el giro.
    if (!returning || !ready || !map) return;
    // Mientras estuvo oculto el contenedor midió 0: se vuelve a medir y, si
    // estaba girando, sigue.
    map.resize();
    if (!map.isMoving()) spinStepRef.current();
  }, [active, ready]);

  // --- Encuadre según los paneles ------------------------------------------
  // Con la búsqueda a un lado, el centro de la cámara (su `padding`) se corre a
  // la parte libre; al ocultarla, el globo se centra y crece un poco. Si está
  // girando, el corrimiento lleva su vuelta para que el giro no se detenga.
  useEffect(() => {
    const previous = insetsRef.current;
    const next: Insets = {
      left: insetLeft,
      right: insetRight,
      top: clearHeader ? headerInsetPx() : 0,
      bottom: insetBottom,
    };
    insetsRef.current = next;
    const map = mapRef.current;
    if (!map || !ready) return;
    if (!introFinished) {
      // Durante la entrada el margen se pone de una vez (la entrada mueve la
      // cámara cuadro a cuadro y llega ya encuadrada): sin segundo ajuste.
      map.setPadding(cameraInsets(next));
      return;
    }
    // En el Centro de mando el globo se ajusta también al terminar la entrada.
    const firstFit = clearHeader && !fittedRef.current;
    if (sameInsets(previous, next) && !firstFit) return;
    if (flyingRef.current) {
      // Va volando a una nota o región: cambiar el margen ahora (setPadding es
      // un jumpTo) cortaba el vuelo a medio camino. Se encuadra al aterrizar.
      insetsRef.current = previous;
      const retry = () => {
        setFramePending((count) => count + 1);
      };
      map.once('moveend', retry);
      return () => {
        map.off('moveend', retry);
      };
    }
    fittedRef.current = true;
    const padding = cameraInsets(next);
    let zoom: number;
    if (clearHeader) {
      // Centro de mando: en la vista general el globo entero llena el espacio
      // libre; con una región o una nota elegida, el zoom no se toca (solo se
      // recorre el centro a la parte libre).
      const screen = screenOf(map);
      zoom = overviewRef.current
        ? fitZoom(map.getZoom(), globeRadiusPx(map), {
            width: screen.width - padding.left - padding.right,
            height: screen.height - padding.top - padding.bottom,
          })
        : map.getZoom();
    } else {
      // Solo los paneles de los lados agrandan o achican el globo.
      const open = insetLeft + insetRight > 0;
      const framed = frameZoom(map.getZoom(), open, expandedRef.current);
      expandedRef.current = framed.expanded;
      zoom = framed.zoom;
    }
    const center = map.getCenter();
    const turning = spinningRef.current && activeRef.current;
    const turn = turning
      ? spinDegrees(map.getZoom()) * spinFactor(motionRef.current) * (GLOBE_FRAME_MS / SPIN_STEP_MS)
      : 0;
    framingRef.current = true;
    map.easeTo({
      padding,
      zoom,
      center: [center.lng - turn, center.lat],
      duration: motionRef.current === 'off' ? 0 : GLOBE_FRAME_MS,
      easing: easeInOutCubic,
    });
    const done = () => {
      framingRef.current = false;
      spinStepRef.current();
    };
    if (map.isMoving()) map.once('moveend', done);
    else done();
  }, [insetLeft, insetRight, insetBottom, clearHeader, ready, introFinished, framePending]);

  // --- Giro ----------------------------------------------------------------
  useEffect(() => {
    spinningRef.current = spinning;
    const map = mapRef.current;
    if (!spinning || !ready || !map) return;
    spinStartRef.current = performance.now();
    if (spinDegrees(map.getZoom()) === 0) {
      // De cerca no se gira: primero se aleja a la vista de globo, que vuelve a
      // ser la vista general (se ajusta al espacio libre al llegar).
      overviewRef.current = true;
      fittedRef.current = false;
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

  // Elegir o soltar una nota, una región o el muro cuenta como uso: el giro
  // no arranca en cuanto se cierra la ficha.
  useEffect(() => {
    lastInteractionRef.current = performance.now();
  }, [regionId, articleId, wallCaseId]);

  // Reanudar el giro tras un rato sin uso, si no se está viendo nada.
  // En el Centro de mando la región de la consulta (casi siempre México) no
  // cuenta: el globo gira con los resultados a la vista y se detiene al abrir
  // una nota, el muro o la lista de un grupo (Benji, 30/10/2026: «que la
  // tierra gire automáticamente cuando no estoy representando nada»).
  const stackOpen = stack !== null;
  useEffect(() => {
    const idleMs = idleResumeMs({
      mando: clearHeader,
      regionId,
      articleId,
      wallCaseId,
      stackOpen,
    });
    if (spinning || idleMs === null || motion === 'off') return;
    const timer = window.setInterval(() => {
      if (performance.now() - lastInteractionRef.current > idleMs) {
        useExplorerStore.getState().setSpinning(true);
      }
    }, IDLE_CHECK_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [spinning, regionId, articleId, wallCaseId, stackOpen, motion, clearHeader]);

  // El muro y «Mis casos» dibujan sobre este mismo mapa (9.6).
  useEffect(() => {
    onMap?.(ready && introFinished ? mapRef.current : null);
  }, [onMap, ready, introFinished]);

  // «Limpiar globo»: de regreso a la vista de México. En el Centro de mando,
  // «Nueva consulta» y «Ajustar consulta» van al Atlántico y al llegar giran.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || homeRequest === 0) return;
    const atlantic = useExplorerStore.getState().homeTarget === 'atlantic';
    const center = atlantic ? ATLANTIC_CENTER : INITIAL_CENTER;
    const target = { lng: center[0], lat: center[1], zoom: INITIAL_ZOOM };
    const duration = flyDurationMs(cameraOf(map), target, 'up', motionRef.current);
    // De vuelta en la vista general: al aterrizar se ajusta al espacio libre.
    overviewRef.current = true;
    fittedRef.current = false;
    // Mientras vuela no gira: el giro haría su propio vuelo y cortaría este.
    if (atlantic) useExplorerStore.getState().setSpinning(false);
    flyRef.current(duration, () => {
      map.flyTo({
        center,
        zoom: INITIAL_ZOOM,
        padding: cameraInsets(insetsRef.current),
        pitch: 0,
        bearing: GLOBE_BEARING,
        curve: FLY_CURVE,
        duration,
        essential: false,
      });
    });
    if (!atlantic) return;
    const spin = () => {
      useExplorerStore.getState().setSpinning(true);
    };
    // El vuelo ya arrancó (flyRef lo empieza en el acto): gira al aterrizar.
    if (map.isMoving()) map.once('moveend', spin);
    else spin();
    return () => {
      map.off('moveend', spin);
    };
  }, [homeRequest, ready]);

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
    // Con el encuadre de los paneles (padding de la cámara) el centro ya está en
    // la parte libre: se encuadra en ella y sin volver a apartar el panel. Se
    // usa el margen completo (no el de la vista general, que pasa por detrás
    // de la consola) y el vuelo lo lleva consigo.
    overviewRef.current = false;
    const inset = insetsRef.current;
    const reservedLeft = inset.left;
    const reservedRight = inset.right;
    const screen = screenOf(map);
    const free = {
      width: screen.width - reservedLeft - reservedRight,
      height: screen.height - inset.top - inset.bottom,
    };
    const padding = flyPadding(
      free,
      columnInTheWay({
        mando: clearHeaderRef.current,
        reservedPx: reservedLeft + reservedRight,
        panelOpen: useExplorerStore.getState().panelOpen,
      }),
      clearHeaderRef.current,
    );
    // Una localidad sin polígono es un punto: se acerca al zoom de localidad.
    const isPoint = box[0] === box[2] && box[1] === box[3];
    const maxZoom = FLY_MAX_ZOOM[isPoint ? 'locality' : region.level];
    const camera = globeCamera(box, free, padding, maxZoom);
    const [lng, lat] = camera.center;
    const { zoom } = camera;
    const duration = flyDurationMs(cameraOf(map), { lng, lat, zoom }, kind, motionRef.current);
    flyRef.current(duration, () => {
      map.flyTo({
        center: camera.center,
        zoom,
        padding: inset,
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
    const duration = flyDurationMs(cameraOf(map), { lng, lat, zoom }, 'article', motionRef.current);
    overviewRef.current = false;
    flyRef.current(duration, () => {
      map.flyTo({
        center: [lng, lat],
        zoom,
        padding: insetsRef.current,
        offset: articleOffset(screenOf(map)),
        pitch: flyPitch('article'),
        bearing: REGION_BEARING,
        curve: ARTICLE_FLY_CURVE,
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
  // Nota sin punto en el mapa (la IA no supo dónde pasó): antes no pasaba nada
  // al elegirla y parecía que el clic no servía (Benji, 27/10/2026). Ahora su
  // ficha sale en medio del espacio libre, con un aviso.
  const unplaced = selected !== null && !hasMapPoint(selected);
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

  // Lugar de la ficha: nunca se sale del mapa ni sube al encabezado
  // (map/newsLayers.ts). Si se arrastró, se suma lo que se movió, sin salirse.
  const cardWidth = calloutWidth(viewport);
  const cardViewport = clearHeader
    ? { ...viewport, top: viewport.top + MANDO_CONTROLS_PX }
    : viewport;
  const placement = (point: { x: number; y: number }) => {
    const base = calloutPlacement(point, { width: cardWidth, height: cardHeight }, cardViewport);
    if (drag.articleId !== articleId) return base;
    const left = clamp(
      base.left + drag.dx,
      CARD_DRAG_MARGIN,
      viewport.width - cardWidth - CARD_DRAG_MARGIN,
    );
    const top = clamp(
      base.top + drag.dy,
      viewport.top + CARD_DRAG_MARGIN,
      viewport.height - cardHeight - CARD_DRAG_MARGIN,
    );
    return {
      left,
      top,
      lineX: base.lineX + (left - base.left),
      lineY: base.lineY + (top - base.top),
    };
  };
  // Arrastrar la ficha con el mouse (Benji, 27/10/2026): desde cualquier parte
  // que no sea un link ni un botón.
  const startCardDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !(event.target instanceof Element)) return;
    if (event.target.closest('a, button, input, select, textarea')) return;
    const current = drag.articleId === articleId ? drag : { dx: 0, dy: 0 };
    dragStartRef.current = { x: event.clientX, y: event.clientY, dx: current.dx, dy: current.dy };
    event.currentTarget.setPointerCapture(event.pointerId);
    // Sin esto, arrastrar seleccionaba el texto de la ficha.
    event.preventDefault();
  };
  const moveCardDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const start = dragStartRef.current;
    if (!start) return;
    setDrag({
      articleId,
      dx: start.dx + event.clientX - start.x,
      dy: start.dy + event.clientY - start.y,
    });
  };
  const endCardDrag = () => {
    dragStartRef.current = null;
  };

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
    const { lng, lat } = stack;
    // Un poco más allá de donde el grupo se separa: se llega al lugar.
    const zoom = Math.min(MAX_STACK_ZOOM, stack.expandZoom + STACK_EXTRA_ZOOM);
    setStack(null);
    const duration = flyDurationMs(cameraOf(map), { lng, lat, zoom }, 'region', motionRef.current);
    flyRef.current(duration, () => {
      map.easeTo({ center: [lng, lat], zoom, duration, easing: easeInOutCubic });
    });
  };

  return (
    <div className="absolute inset-0">
      {/* Detrás del globo: una aureola cian muy tenue y el brillo del Sol que se
          asoma por el borde. El globo tapa lo de en medio; solo se ve el borde. */}
      <div
        ref={auraRef}
        aria-hidden="true"
        className="pointer-events-none absolute rounded-full"
        style={{
          background:
            // closest-side: los % son del radio del cuadro (el globo llega al 71 %).
            // Ligeramente azulada (Benji, 26/10/2026): ni el cian puro, que se
            // veía demasiado azul, ni el gris del primer ajuste.
            'radial-gradient(circle closest-side, transparent 0 70.5%, rgb(150 205 245 / 0.34) 72%, rgb(100 165 230 / 0.13) 77%, rgb(80 135 215 / 0.045) 87%, transparent 100%)',
        }}
      />
      <div
        ref={sunRef}
        aria-hidden="true"
        className="pointer-events-none absolute rounded-full mix-blend-screen"
        style={{
          background:
            'radial-gradient(circle, rgb(255 255 255 / 0.95) 0, rgb(255 238 205 / 0.5) 5%, rgb(255 205 150 / 0.18) 20%, rgb(120 200 255 / 0.06) 42%, transparent 62%)',
        }}
      />
      {/* globo-bajo-encabezado: los botones del mapa bajan al hueco del encabezado. */}
      <div
        ref={containerRef}
        className="globo-bajo-encabezado h-full w-full"
        aria-label="Globo interactivo"
      />
      {graphicsLost && <GlobeUnavailable />}
      {tooltip?.label && (
        <div
          role="tooltip"
          className="hud-panel pointer-events-none absolute z-10 max-w-xs -translate-x-1/2 -translate-y-[calc(100%+14px)] bg-[#050d12]/95 px-3 py-1.5 text-sm"
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
            className="absolute z-20 cursor-grab touch-none active:cursor-grabbing"
            title="Arrastra la ficha para moverla"
            onPointerDown={startCardDrag}
            onPointerMove={moveCardDrag}
            onPointerUp={endCardDrag}
            onPointerCancel={endCardDrag}
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
      {selected && unplaced && (
        <div
          className="absolute z-20"
          style={{
            left: insetLeft + (viewport.width - insetLeft - insetRight - cardWidth) / 2,
            top: viewport.top + UNPLACED_CARD_TOP_PX,
            width: cardWidth,
          }}
        >
          <div
            role="dialog"
            aria-label="Nota sin lugar en el mapa"
            className={`${GLASS} animate-[fadeIn_200ms_ease-out] p-4`}
          >
            <p className="mb-2 font-display text-[9.5px] tracking-[0.22em] text-sky-300 uppercase">
              Sin lugar en el mapa · la nota no dice dónde pasó
            </p>
            <NewsCard
              article={selected}
              colors={colors}
              onClose={() => {
                useExplorerStore.getState().selectArticle(null);
              }}
            />
          </div>
        </div>
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
