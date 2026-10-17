/**
 * Tarjeta de noticia (especificación §14.4): título, medio y fecha (hora de
 * CDMX), conceptos con su color, resumen marcado como automático, ubicación con
 * insignia de precisión, proveedores y "Ver nota original".
 *
 * Nunca muestra el texto completo de la nota (CLAUDE.md §8): solo el resumen
 * propio y el link al medio.
 */
import type { Article } from '../../services/searches';
import { formatMexicoCity, isCoarse, PRECISION_LABEL } from './format';

interface NewsCardProps {
  article: Article;
  colors: ReadonlyMap<number, string>;
  onClose?: () => void;
}

const PROVIDER_LABEL: Record<string, string> = {
  searchapi: 'Google News',
  indice_local: 'Índice local',
  gdelt: 'GDELT',
  google_news_rss: 'Google News RSS',
};

export function NewsCard({ article, colors, onClose }: NewsCardProps) {
  const location = article.primary_location;
  const relevant = article.concepts.filter((c) => c.is_relevant);
  return (
    <article className="space-y-2.5 text-sm" aria-label={article.title}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold leading-snug text-slate-50">{article.title}</h3>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar ficha"
            className="-mr-1 -mt-1 shrink-0 rounded-md p-1 text-slate-400 hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20" className="size-4 fill-current">
              <path d="m10 8.94 4.47-4.47 1.06 1.06L11.06 10l4.47 4.47-1.06 1.06L10 11.06l-4.47 4.47-1.06-1.06L8.94 10 4.47 5.53l1.06-1.06L10 8.94Z" />
            </svg>
          </button>
        )}
      </div>
      <p className="text-xs text-slate-400">
        {article.source_name ?? article.source_domain ?? 'Medio sin nombre'}
        {article.published_at && ` · ${formatMexicoCity(article.published_at)}`}
      </p>
      {relevant.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {relevant.map((c) => (
            <span
              key={c.concept_id}
              className="flex items-center gap-1.5 rounded-full bg-white/10 px-2 py-0.5 text-xs text-slate-100"
            >
              <span
                aria-hidden="true"
                className="size-2 rounded-full"
                style={{ backgroundColor: colors.get(c.concept_id) ?? '#38BDF8' }}
              />
              {c.name}
            </span>
          ))}
        </div>
      )}
      {article.summary && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-sky-300/80">
            Resumen automático
          </p>
          <p className="mt-0.5 leading-relaxed text-slate-200">{article.summary}</p>
        </div>
      )}
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-300">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
            location === null
              ? 'bg-slate-700 text-slate-300'
              : isCoarse(location.precision)
                ? 'border border-dashed border-amber-300/70 text-amber-200'
                : 'bg-sky-500/20 text-sky-200'
          }`}
        >
          {PRECISION_LABEL[location?.precision ?? 'unknown']}
        </span>
        {location?.place ?? 'Sin ubicación'}
        {article.in_region === false && (
          <span className="text-amber-200">· fuera de la región</span>
        )}
      </p>
      <div className="flex items-center justify-between gap-2 pt-1">
        <span className="text-[11px] text-slate-500">
          {article.providers.map((p) => PROVIDER_LABEL[p] ?? p).join(' · ')}
        </span>
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-lg bg-sky-500/20 px-2.5 py-1 text-xs font-medium text-sky-100 hover:bg-sky-500/30 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          Ver nota original ↗
        </a>
      </div>
    </article>
  );
}
