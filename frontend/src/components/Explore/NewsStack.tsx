/**
 * Lista de las notas de un mismo lugar del globo (un grupo o puntos encimados).
 *
 * Varias notas en un mismo punto se dibujan como un círculo con número, o una
 * encima de otra cuando comparten coordenadas (todas las ubicadas "solo por
 * estado" caen en el centro del estado). Antes, al hacer clic, solo se acercaba
 * el mapa y no se sabía cuáles eran. Esta lista dice cuáles son y deja abrir
 * cada una.
 *
 * No hace: no mueve la cámara (eso lo decide el globo con `onZoom`) ni pide
 * datos: recibe las notas ya cargadas.
 */
import type { Article } from '../../services/searches';
import { formatDay } from './format';
import { GLASS } from './ui';

interface NewsStackProps {
  articles: Article[];
  colors: ReadonlyMap<number, string>;
  /** Cuántas notas tiene el grupo (puede ser más de las que se listan). */
  total: number;
  onSelect: (articleId: number) => void;
  /** Acercarse hasta separar el grupo; `undefined` si ya no se puede. */
  onZoom?: () => void;
  onClose: () => void;
}

export function NewsStack({ articles, colors, total, onSelect, onZoom, onClose }: NewsStackProps) {
  return (
    <section aria-label="Notas en este lugar" className={`${GLASS} w-80 space-y-2 p-3 text-sm`}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-display text-xs font-semibold uppercase tracking-[0.14em] text-sky-200/80">
          {total} notas en este lugar
        </h3>
        <div className="flex items-center gap-1">
          {onZoom && (
            <button
              type="button"
              onClick={onZoom}
              className="rounded-md px-2 py-0.5 text-[11px] text-sky-200 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-sky-400"
            >
              Acercar
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar lista"
            className="rounded-md px-1.5 text-slate-400 hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            ×
          </button>
        </div>
      </div>
      <ul className="max-h-72 space-y-1 overflow-y-auto pr-1">
        {articles.map((article) => {
          const concept = article.concepts.find((c) => c.is_relevant) ?? article.concepts[0];
          return (
            <li key={article.article_id}>
              <button
                type="button"
                onClick={() => {
                  onSelect(article.article_id);
                }}
                className="flex w-full gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-sky-400"
              >
                <span
                  aria-hidden="true"
                  className="mt-1.5 size-2 shrink-0 rounded-full"
                  style={{
                    backgroundColor:
                      (concept && colors.get(concept.concept_id)) ?? 'rgb(56 189 248)',
                  }}
                />
                <span className="min-w-0">
                  <span className="line-clamp-2 leading-snug text-slate-100">{article.title}</span>
                  <span className="block truncate text-[11px] text-slate-400">
                    {article.source_name ?? article.source_domain ?? 'Medio sin nombre'}
                    {article.published_at && ` · ${formatDay(article.published_at)}`}
                    {article.primary_location?.place && ` · ${article.primary_location.place}`}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {total > articles.length && (
        <p className="text-[11px] text-slate-500">
          Se muestran {articles.length}; acércate para ver el resto.
        </p>
      )}
    </section>
  );
}
