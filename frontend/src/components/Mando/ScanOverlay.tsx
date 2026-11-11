/**
 * Lo que se ve sobre el globo en el diseño «Centro de mando»: un radar que
 * barre **la zona que se busca** mientras corre la búsqueda y, al terminar, un
 * letrero grande («BARRIDO COMPLETO · 128 notas») que se desvanece solo.
 *
 * Radar (Benji, 11/11/2026: «sincronizado con la zona que estamos buscando»,
 * «que el cliente sienta que realmente está pasando algo»):
 * - va centrado en la región buscada y de su tamaño (todo México, Chiapas, un
 *   municipio), siguiendo al mapa si se mueve;
 * - esquinas de «objetivo fijado» alrededor de la región y sus coordenadas;
 * - barrido, ondas y ecos: un símbolo de nota aparece por cada nota que se
 *   va encontrando;
 * - abajo, la etapa en curso («Consultando proveedores», «Ubicando en el
 *   mapa»…) y las notas detectadas.
 * Sin mapa o sin región todavía, se centra en la parte libre de la pantalla.
 *
 * No hace: no recibe clics (todo es `pointer-events: none`) ni mueve el mapa.
 */
import type { Map as MapLibreMap } from 'maplibre-gl';
import { type CSSProperties, useEffect, useState } from 'react';

import { isFinished, type Search } from '../../services/searches';
import { type FinishNotice, STAGE_LABEL } from '../Explore/format';
import { DecodeText } from '../ui/DecodeText';
import { type Bbox, blips, coordinatesLabel, type RadarGeometry, radarGeometry } from './radar';

// Retraso de cada onda del radar, en segundos: tres ondas parejas en el ciclo.
const RING_DELAYS_S = [0, 1.1, 2.2];
// Tamaño del radar sin región: más o menos el del globo en la vista de México.
const SCAN_SIZE = 'min(66vh, 46vw)';
// Ecos a la vista como máximo: más ya no se distinguen.
const MAX_BLIPS = 18;

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
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
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
  const stage = STAGE_LABEL[search.progress.stage ?? 'plan'] ?? 'Preparando el barrido';
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
          {found > 0 && ` · ${String(search.progress.articles ?? found)} notas detectadas`}
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
