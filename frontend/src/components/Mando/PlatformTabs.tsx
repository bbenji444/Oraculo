/**
 * Pestañas de plataforma del expediente (ADR-0117), como las de Google
 * («Todo · Noticias · Videos»): «Todo 42 · Noticias 35 · Facebook 5 · X 2…»,
 * entre «Cronología | Noticias» y «N de M notas · Filtro», para verlas sin
 * abrir ninguna ventana.
 *
 * - Una a la vez: tocar Facebook deja solo Facebook; tocarla otra vez regresa
 *   a «Todo». Para ver varias juntas («Facebook y X») está la sección
 *   «Plataforma» de «Filtro»; las dos escriben en el mismo filtro.
 * - Cada pestaña dice cuántas notas vería: respeta los demás filtros y
 *   «Incluir las no relevantes», pero no la plataforma (conteo facetado).
 * - Solo salen las plataformas que tienen notas; si todo es de una sola
 *   (lo normal hasta que llegue Google web), la fila no aparece.
 * - En celular la fila se desliza de lado, con un desvanecido a la derecha
 *   que avisa que hay más. En la computadora pasan a un segundo renglón: con
 *   el mouse no hay cómo deslizar una fila sin barra.
 *
 * No hace: no filtra por su cuenta; escribe en `useTimelineStore`, que
 * comparten el globo, la lista y la cronología.
 */
import type { CSSProperties } from 'react';

import type { Article } from '../../services/searches';
import { useTimelineStore } from '../../store/timeline';
import { PlatformIcon } from '../Explore/PlatformMark';
import { platformTabs, tabChoice } from '../Explore/platforms';

// Color de «Todo»: el gris de la paleta (mismo que «Todas» de las categorías).
const ALL_TONE = '148 163 184';

function notes(count: number): string {
  return `${String(count)} ${count === 1 ? 'nota' : 'notas'}`;
}

interface PlatformTabsProps {
  /** Las notas con todos los demás filtros puestos, sin el de plataforma. */
  articles: readonly Article[];
  className?: string;
}

export function PlatformTabs({ articles, className = '' }: PlatformTabsProps) {
  const selected = useTimelineStore((s) => s.platforms);
  const setPlatform = useTimelineStore((s) => s.setPlatform);
  const tabs = platformTabs(articles, selected);
  // Con una sola plataforma la fila no diría nada; pero si hay una elegida
  // se queda, para poder regresar a «Todo».
  if (tabs.length <= 1 && selected.length === 0) return null;
  const all = selected.length === 0;
  return (
    <div
      role="group"
      aria-label="Filtrar por plataforma"
      className={`platform-tabs sin-barra ${className}`}
    >
      <button
        type="button"
        aria-pressed={all}
        aria-label={`Todo: ${notes(articles.length)}`}
        onClick={() => {
          setPlatform(null);
        }}
        className="platform-tab"
        style={{ '--cat': ALL_TONE } as CSSProperties}
      >
        <span>Todo</span>
        <span className="platform-tab-count">{articles.length}</span>
      </button>
      {tabs.map((tab) => {
        const on = selected.includes(tab.id);
        return (
          <button
            key={tab.id}
            type="button"
            aria-pressed={on}
            aria-label={`${tab.label}: ${notes(tab.count)}`}
            title={
              on && selected.length === 1
                ? 'Tócala otra vez para ver todas'
                : `Ver solo ${tab.label}`
            }
            onClick={() => {
              setPlatform(tabChoice(selected, tab.id));
            }}
            className="platform-tab"
            style={{ '--cat': tab.tone } as CSSProperties}
          >
            <PlatformIcon info={tab} className="platform-tab-icon" />
            <span className={tab.icon ? undefined : 'platform-letter'}>{tab.label}</span>
            <span className="platform-tab-count">{tab.count}</span>
          </button>
        );
      })}
    </div>
  );
}
