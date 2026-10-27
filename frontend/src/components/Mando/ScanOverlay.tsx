/**
 * Lo que se ve sobre el globo en el diseño «Centro de mando»: un radar que lo
 * barre mientras corre la búsqueda y, al terminar, un letrero grande
 * («BARRIDO COMPLETO · 128 notas») que se desvanece solo.
 *
 * El radar se centra en la parte libre de la pantalla, igual que el globo:
 * recibe los mismos márgenes que ExploreGlobe.
 *
 * No hace: no recibe clics (todo es `pointer-events: none`) ni pide datos.
 */
import type { CSSProperties } from 'react';

import { isFinished, type Search } from '../../services/searches';
import type { FinishNotice } from '../Explore/format';
import { DecodeText } from '../ui/DecodeText';

// Retraso de cada onda del radar, en segundos: tres ondas parejas en el ciclo.
const RING_DELAYS_S = [0, 1.1, 2.2];
// Tamaño del radar: más o menos el del globo en la vista de México.
const SCAN_SIZE = 'min(66vh, 46vw)';

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
}

export function ScanOverlay({ search, notice, right, bottom }: ScanOverlayProps) {
  const running = search !== undefined && !isFinished(search.status);
  // El centro de la parte libre: entre el encabezado y la consola, y a la
  // izquierda del expediente (el mismo encuadre que el globo).
  const center: CSSProperties = {
    left: `calc((100% - ${String(right)}px) / 2)`,
    top: `calc((100% - ${String(bottom)}px - var(--header-h)) / 2 + var(--header-h))`,
  };
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {running && (
        <div aria-hidden="true" className="mando-scan" style={{ ...center, width: SCAN_SIZE }}>
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
          <span className="mando-scan-label">Barrido en curso · {search.region_name}</span>
        </div>
      )}
      <div role="status" aria-live="polite">
        {notice && (
          <div key={notice.text} className="mando-banner" style={center}>
            <p
              className={`mando-banner-title ${
                notice.tone === 'ok'
                  ? ''
                  : notice.tone === 'warn'
                    ? 'text-amber-200'
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
