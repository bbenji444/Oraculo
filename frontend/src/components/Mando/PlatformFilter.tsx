/**
 * Sección «Plataforma» de la ventana «Filtro» (ADR-0117): un botón por cada
 * plataforma que trae la consulta (Noticias, Facebook, X, YouTube…), con su
 * color y cuántas notas tiene.
 *
 * Se prenden y apagan varias a la vez: con «Facebook» y «X» quedan las de las
 * dos. Sin ninguno prendido se ven todas. Es el mismo filtro que las pestañas
 * del expediente (`PlatformTabs`), que eligen una sola.
 *
 * No hace: no filtra por su cuenta (eso es `applyTimeline`).
 */
import type { CSSProperties } from 'react';

import type { Article } from '../../services/searches';
import { useTimelineStore } from '../../store/timeline';
import { PlatformIcon } from '../Explore/PlatformMark';
import { platformTabs } from '../Explore/platforms';

// Color de «Todas»: el gris de la paleta, como en las categorías.
const ALL_TONE = '148 163 184';

interface PlatformFilterProps {
  /** Las notas de la consulta, antes de este filtro (para contar). */
  articles: readonly Article[];
}

export function PlatformFilter({ articles }: PlatformFilterProps) {
  const picked = useTimelineStore((s) => s.platforms);
  const toggle = useTimelineStore((s) => s.togglePlatform);
  const clear = useTimelineStore((s) => s.setPlatform);
  const platforms = platformTabs(articles, picked);
  const none = picked.length === 0;
  return (
    // Otro nombre que las pestañas del expediente: las dos están en pantalla
    // cuando la ventana está abierta.
    <div role="group" aria-label="Plataformas a mostrar" className="grid grid-cols-3 gap-1.5">
      <button
        type="button"
        aria-pressed={none}
        onClick={() => {
          clear(null);
        }}
        className="mando-cat mando-cat--card"
        style={{ '--cat': ALL_TONE } as CSSProperties}
      >
        <span className="mando-cat-name">Todas</span>
      </button>
      {platforms.map((platform) => {
        const on = picked.includes(platform.id);
        return (
          <button
            key={platform.id}
            type="button"
            aria-pressed={on}
            onClick={() => {
              toggle(platform.id);
            }}
            title={`${platform.label}: ${String(platform.count)} notas`}
            // Apagadas se ven tenues cuando hay otra prendida.
            data-dim={!none && !on ? '' : undefined}
            className="mando-cat mando-cat--card"
            style={{ '--cat': platform.tone } as CSSProperties}
          >
            <PlatformIcon info={platform} className="platform-tab-icon" />
            <span className={`mando-cat-name ${platform.icon ? '' : 'platform-letter'}`}>
              {platform.label}
            </span>
            <span className="mando-cat-count">{platform.count}</span>
          </button>
        );
      })}
    </div>
  );
}
