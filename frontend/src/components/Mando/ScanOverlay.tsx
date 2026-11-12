/**
 * Lo que se ve sobre el globo en el diseño «Centro de mando»: un radar que
 * barre **la zona que se busca** mientras corre la búsqueda y, al terminar, un
 * letrero grande («BARRIDO COMPLETO · 128 notas») que se desvanece solo.
 *
 * Radar (Benji, 11/11/2026: «sincronizado con la zona que estamos buscando»,
 * «una cúpula en 3D sobre el área», «que el cliente sienta que realmente está
 * pasando algo»):
 * - con el mapa y la región, una **cúpula 3D** sobre la zona buscada (todo
 *   México, Chiapas, un municipio), dibujada en el propio globo
 *   (map/radar/dome.ts): vidrio con rejilla, haz que gira, onda en el piso y
 *   una columna de luz por cada nota encontrada. La cámara vuela a la zona,
 *   la encuadra y se inclina 60° para que se vea el volumen; al terminar se
 *   endereza;
 * - encima, el letrero con la región y sus coordenadas; abajo, la etapa en
 *   curso («Consultando proveedores», «Ubicando en el mapa»…) y las notas
 *   detectadas. Siguen a la cúpula si el mapa se mueve.
 * Sin mapa o sin región todavía, un radar plano en la parte libre de la pantalla.
 *
 * No hace: no recibe clics (todo es `pointer-events: none`); fuera de ese
 * vuelo de la cámara, no mueve el mapa.
 */
import type { Map as MapLibreMap } from 'maplibre-gl';
import { type CSSProperties, useEffect, useRef, useState } from 'react';

import { addDomeRadar, type DomeRadar } from '../../map/radar/dome';
import { isFinished, type Search } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { type FinishNotice, STAGE_LABEL } from '../Explore/format';
import { DecodeText } from '../ui/DecodeText';
import { type Bbox, blips, coordinatesLabel, type RadarGeometry, radarGeometry } from './radar';

// Retraso de cada onda del radar, en segundos: tres ondas parejas en el ciclo.
const RING_DELAYS_S = [0, 1.1, 2.2];
// Tamaño del radar sin región: más o menos el del globo en la vista de México.
const SCAN_SIZE = 'min(66vh, 46vw)';
// Ecos del radar plano a la vista como máximo: más ya no se distinguen.
const MAX_BLIPS = 18;
// Inclinación de la cámara durante el barrido (grados): deja ver el volumen
// de la cúpula. 60 es lo más que MapLibre deja por omisión (maxPitch); Benji,
// 11/11/2026: «que el mundo se inclinara un poco para que se pudiera ver el
// efecto 3D de la zona» (con 40 se veía casi plana).
const DOME_PITCH = 60;
const TILT_MS = 1400;
// Vuelo a la zona: aire para el encabezado y la consola, sin acercarse de más.
const AIM_PADDING = { top: 140, bottom: 300, left: 60, right: 60 };
const AIM_MAX_ZOOM = 7;
const AIM_MS = 2200;
// Espera para no chocar con el acomodo propio del globo al recibir el mapa.
const AIM_DELAY_MS = 400;
// El letrero de arriba nunca queda debajo del encabezado (px desde arriba).
const MIN_LABEL_TOP_PX = 130;

const BANNER_TITLE: Record<FinishNotice['tone'], string> = {
  ok: 'Barrido completo',
  warn: 'Barrido parcial',
  error: 'Barrido interrumpido',
};

interface ScanOverlayProps {
  search: Search | undefined;
  /** Aviso de que la búsqueda que se vio correr terminó (useFinishNotice). */
  notice: FinishNotice | null;
  /** Píxeles que ocupan los paneles a la derecha y la consola abajo. */
  right: number;
  bottom: number;
  /** El mapa, para poner el radar sobre la región buscada. */
  map?: MapLibreMap | null;
  /** Rectángulo de la región buscada (`focus_bbox`), si ya se conoce. */
  regionBbox?: Bbox;
}

/** Sigue al mapa: dónde cae la región en la pantalla en cada movimiento. */
function useRegionOnScreen(
  map: MapLibreMap | null | undefined,
  bbox: Bbox | undefined,
): RadarGeometry | null {
  const [geometry, setGeometry] = useState<RadarGeometry | null>(null);
  useEffect(() => {
    if (!map || !bbox) return;
    let frame = 0;
    // Un cálculo por cuadro como máximo. Sin cancelar el pendiente: mientras
    // el globo se mueve hay un «move» en cada cuadro y, cancelando, el cálculo
    // nunca llegaba a correr (el radar se quedaba en su lugar de respaldo).
    const measure = () => {
      if (frame !== 0) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const canvas = map.getContainer();
        setGeometry(
          radarGeometry((lngLat) => map.project(lngLat), bbox, {
            width: canvas.clientWidth,
            height: canvas.clientHeight,
          }),
        );
      });
    };
    measure();
    map.on('move', measure);
    map.on('resize', measure);
    return () => {
      cancelAnimationFrame(frame);
      map.off('move', measure);
      map.off('resize', measure);
    };
  }, [map, bbox]);
  return map && bbox ? geometry : null;
}

/**
 * La cúpula 3D sobre la región mientras se busca; se quita al terminar.
 *
 * @returns Si hay cúpula (hay mapa y región).
 */
function useDomeRadar(
  map: MapLibreMap | null | undefined,
  bbox: Bbox | undefined,
  found: number,
): boolean {
  const animate = useExplorerStore((s) => s.motion !== 'off');
  const radarRef = useRef<DomeRadar | null>(null);
  const foundRef = useRef(found);
  useEffect(() => {
    foundRef.current = found;
    radarRef.current?.setBlips(found);
  }, [found]);
  useEffect(() => {
    if (!map || !bbox) return;
    // La cámara vuela a la zona, la encuadra y se inclina: vista desde arriba
    // la cúpula parece un disco; inclinada se nota su volumen. Aunque la zona
    // ya se vea, se encuadra: una zona chica (un estado) se veía diminuta.
    const [west, south, east, north] = bbox;
    const aim = () => {
      const center: [number, number] = [(west + east) / 2, (south + north) / 2];
      const fit = map.cameraForBounds([west, south, east, north], { padding: AIM_PADDING });
      map.flyTo({
        center,
        zoom: Math.min(fit?.zoom ?? map.getZoom(), AIM_MAX_ZOOM),
        pitch: DOME_PITCH,
        duration: animate ? AIM_MS : 0,
      });
    };
    let aimTimer = 0;
    // Se espera a que el globo termine su propio acomodo: si no, lo cancelaba.
    const aimSoon = () => {
      window.clearTimeout(aimTimer);
      aimTimer = window.setTimeout(aim, AIM_DELAY_MS);
    };
    try {
      radarRef.current = addDomeRadar(map, bbox, animate);
      radarRef.current.setBlips(foundRef.current);
      if (map.isMoving()) map.once('moveend', aimSoon);
      else aimSoon();
    } catch {
      // Sin WebGL 2 o con el estilo a medio cargar no hay cúpula; los
      // letreros siguen diciendo qué pasa.
      radarRef.current = null;
    }
    return () => {
      const hadDome = radarRef.current !== null;
      radarRef.current?.remove();
      radarRef.current = null;
      window.clearTimeout(aimTimer);
      map.off('moveend', aimSoon);
      // Al terminar el barrido la cámara se endereza para ver los resultados.
      if (hadDome && map.getPitch() > 0) {
        map.easeTo({ pitch: 0, duration: animate ? TILT_MS : 0 });
      }
    };
  }, [map, bbox, animate]);
  return Boolean(map && bbox);
}

function RegionRadar({
  search,
  map,
  bbox,
  fallback,
}: {
  search: Search;
  map: MapLibreMap | null | undefined;
  bbox: Bbox | undefined;
  fallback: CSSProperties;
}) {
  const geometry = useRegionOnScreen(map, bbox);
  const found = Math.min(search.progress.articles ?? 0, MAX_BLIPS);
  const dome = useDomeRadar(map, bbox, found);
  // El globo mira la zona del barrido: si no es la región elegida (por
  // ejemplo, al volver con la búsqueda ya corriendo), se elige y el globo vuela
  // a ella como al elegirla a mano.
  const regionId = search.region_id;
  useEffect(() => {
    const store = useExplorerStore.getState();
    if (store.regionId !== regionId) store.selectRegion(regionId);
  }, [regionId]);
  const stage = STAGE_LABEL[search.progress.stage ?? 'plan'] ?? 'Preparando el barrido';
  const detected =
    found > 0 ? ` · ${String(search.progress.articles ?? found)} notas detectadas` : '';
  if (dome && geometry && bbox) {
    // La cúpula la dibuja el globo; aquí solo los letreros, pegados a ella.
    return (
      <div
        aria-hidden="true"
        className="mando-dome-labels"
        style={{
          left: geometry.cx,
          top: Math.max(geometry.box.top, MIN_LABEL_TOP_PX),
          height: Math.max(
            0,
            geometry.box.top + geometry.box.height - Math.max(geometry.box.top, MIN_LABEL_TOP_PX),
          ),
        }}
      >
        <span className="mando-dome-title">
          Barrido en curso · {search.region_name}
          <span className="mando-dome-coords">{coordinatesLabel(bbox)}</span>
        </span>
        <span className="mando-scan-status mando-dome-status">
          <span className="mando-scan-status-dot" />
          {stage}
          {detected}
        </span>
      </div>
    );
  }
  const placed: CSSProperties = geometry
    ? { left: geometry.cx, top: geometry.cy, width: geometry.radius * 2 }
    : { ...fallback, width: SCAN_SIZE };

  return (
    <>
      {geometry && (
        <div
          aria-hidden="true"
          className="mando-target"
          style={{
            left: geometry.box.left,
            top: geometry.box.top,
            width: geometry.box.width,
            height: geometry.box.height,
          }}
        >
          <span className="mando-target-corner mando-target-corner--tl" />
          <span className="mando-target-corner mando-target-corner--tr" />
          <span className="mando-target-corner mando-target-corner--bl" />
          <span className="mando-target-corner mando-target-corner--br" />
        </div>
      )}
      <div aria-hidden="true" className="mando-scan" style={placed}>
        <span className="mando-scan-grid" />
        <span className="mando-scan-frame" />
        <span className="mando-scan-cross" />
        <span className="mando-scan-sweep" />
        {RING_DELAYS_S.map((delay) => (
          <span
            key={delay}
            className="mando-scan-ring"
            style={{ animationDelay: `${String(delay)}s` }}
          />
        ))}
        {blips(found).map((blip, index) => (
          <span
            key={index}
            className="mando-blip"
            style={{
              left: `${String(blip.x)}%`,
              top: `${String(blip.y)}%`,
              animationDelay: `${String(blip.delay)}s`,
            }}
          >
            <svg viewBox="0 0 16 16" width="12" height="12">
              <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
              <path d="M4.5 5.5h7M4.5 8h7M4.5 10.5h4" />
            </svg>
          </span>
        ))}
        <span className="mando-scan-label">Barrido en curso · {search.region_name}</span>
        {bbox && <span className="mando-scan-coords">{coordinatesLabel(bbox)}</span>}
        <span className="mando-scan-status">
          <span className="mando-scan-status-dot" />
          {stage}
          {detected}
        </span>
      </div>
    </>
  );
}

export function ScanOverlay({ search, notice, right, bottom, map, regionBbox }: ScanOverlayProps) {
  const running = search !== undefined && !isFinished(search.status);
  // El centro de la parte libre: entre el encabezado y la consola, y a la
  // izquierda del expediente (el mismo encuadre que el globo).
  const center: CSSProperties = {
    left: `calc((100% - ${String(right)}px) / 2)`,
    top: `calc((100% - ${String(bottom)}px - var(--header-h)) / 2 + var(--header-h))`,
  };
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {running && <RegionRadar search={search} map={map} bbox={regionBbox} fallback={center} />}
      <div role="status" aria-live="polite">
        {notice && (
          <div key={notice.text} className="mando-banner" style={center}>
            <p
              className={`mando-banner-title ${
                notice.tone === 'ok'
                  ? ''
                  : notice.tone === 'warn'
                    ? 'text-violet-200'
                    : 'text-rose-300'
              }`}
            >
              <DecodeText text={BANNER_TITLE[notice.tone].toUpperCase()} onHover={false} />
            </p>
            <div aria-hidden="true" className="mando-banner-line" />
            <p className="font-display text-[11px] tracking-[0.3em] text-sky-200 uppercase">
              {notice.text}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
