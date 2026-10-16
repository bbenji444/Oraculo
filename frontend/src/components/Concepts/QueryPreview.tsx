/**
 * Panel "Probar concepto" (historia H2).
 *
 * La persona elige una región y un rango; el backend arma las consultas
 * exactas que se enviarían a cada proveedor, sin llamar a ninguno ni gastar
 * créditos. Prueba el formulario tal como está, aunque no se haya guardado.
 */
import { useState } from 'react';

import { useQueryPreview } from '../../hooks/useConcepts';
import type { ConceptInput, PlannedQuery } from '../../services/concepts';
import type { Region } from '../../services/regions';
import { SearchBox } from '../GeoExplorer/SearchBox';

interface QueryPreviewProps {
  draft: ConceptInput;
}

// Rangos del panel de búsqueda (especificación §14.3) y el máximo de 90
// días que cubre GDELT.
const RANGES = [
  { days: 1, label: 'Hoy' },
  { days: 7, label: '7 días' },
  { days: 30, label: '30 días' },
  { days: 90, label: '90 días' },
];

const PROVIDER_STYLE: Record<PlannedQuery['provider'], string> = {
  searchapi: 'bg-sky-500/15 text-sky-200 ring-sky-500/30',
  google_news_rss: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/30',
  gdelt: 'bg-violet-500/15 text-violet-200 ring-violet-500/30',
  indice_local: 'bg-amber-500/15 text-amber-200 ring-amber-500/30',
};

function QueryCard({ query }: { query: PlannedQuery }) {
  const [copied, setCopied] = useState(false);
  return (
    <li className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <span
          className={`rounded-md px-2 py-0.5 font-medium ring-1 ${PROVIDER_STYLE[query.provider]}`}
        >
          {query.provider_label}
        </span>
        <span className="text-slate-400">
          {query.filters.country} · {query.filters.language} · {query.filters.period}
        </span>
        <span className="ml-auto text-slate-500">
          {query.estimated_credits === 0
            ? 'gratis'
            : `${String(query.estimated_credits)} crédito${query.estimated_credits === 1 ? '' : 's'}`}
        </span>
      </div>
      <div className="flex items-start gap-2">
        <code className="block flex-1 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-slate-200">
          {query.text}
        </code>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(query.text).then(() => {
              setCopied(true);
              window.setTimeout(() => {
                setCopied(false);
              }, 1500);
            });
          }}
          className="shrink-0 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          {copied ? 'Copiado' : 'Copiar'}
        </button>
      </div>
    </li>
  );
}

export function QueryPreview({ draft }: QueryPreviewProps) {
  const [region, setRegion] = useState<Region | null>(null);
  const [days, setDays] = useState(7);
  const preview = useQueryPreview();
  const result = preview.data;

  return (
    <section
      aria-labelledby="probar-concepto"
      className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"
    >
      <h3 id="probar-concepto" className="text-sm font-semibold text-slate-100">
        Probar concepto
      </h3>
      <p className="mt-0.5 text-xs text-slate-400">
        Muestra las consultas exactas que se enviarían. No se envía nada ni se gastan créditos.
      </p>

      <div className="mt-3 space-y-2">
        <SearchBox onSelect={setRegion} />
        <div className="flex flex-wrap items-center gap-2">
          <div role="radiogroup" aria-label="Rango de fechas" className="flex gap-1">
            {RANGES.map((range) => (
              <button
                key={range.days}
                type="button"
                role="radio"
                aria-checked={days === range.days}
                onClick={() => {
                  setDays(range.days);
                }}
                className={`rounded-md px-2.5 py-1 text-xs focus-visible:outline-2 focus-visible:outline-sky-400 ${
                  days === range.days
                    ? 'bg-slate-700 text-slate-50'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`}
              >
                {range.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            disabled={region === null || preview.isPending}
            onClick={() => {
              if (region) preview.mutate({ regionId: region.id, days, draft });
            }}
            className="ml-auto rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 focus-visible:outline-2 focus-visible:outline-sky-300 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {preview.isPending ? 'Armando…' : 'Ver consultas'}
          </button>
        </div>
        {region === null && (
          <p className="text-xs text-slate-500">
            Elige una región para probar, por ejemplo Jalisco.
          </p>
        )}
      </div>

      {preview.error && (
        <p role="alert" className="mt-3 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {preview.error.message}
        </p>
      )}

      {result && (
        <div className="mt-4" aria-live="polite">
          <p className="mb-2 text-xs text-slate-400">
            <span className="text-slate-200">{result.region.breadcrumb}</span> ·{' '}
            {result.window.description} · {result.total_queries} consultas · ~{result.total_credits}{' '}
            crédito{result.total_credits === 1 ? '' : 's'} de SearchApi
          </p>
          <ul className="space-y-2">
            {result.queries.map((query, index) => (
              <QueryCard key={`${query.provider}-${String(index)}`} query={query} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
