/**
 * Panel "Probar concepto" (historia H2).
 *
 * La persona elige una región y un rango; el backend arma las consultas
 * exactas que se enviarían a cada proveedor, sin llamar a ninguno ni gastar
 * créditos. Prueba el formulario tal como está, aunque no se haya guardado.
 *
 * Diseño «consola táctica» (ADR-0036): panel con borde de luz, selector de
 * rango con pastilla deslizante y cada consulta como una fila que se ilumina.
 */
import { type CSSProperties, useState } from 'react';

import { useQueryPreview } from '../../hooks/useConcepts';
import { copyText } from '../../ui/copyText';
import type { ConceptInput, PlannedQuery } from '../../services/concepts';
import type { Region } from '../../services/regions';
import { SearchBox } from '../GeoExplorer/SearchBox';
import { HudButton } from '../ui/HudButton';
import { type ChipTone, HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';

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

const PROVIDER_TONE: Record<PlannedQuery['provider'], ChipTone> = {
  searchapi: 'cyan',
  google_news_rss: 'green',
  gdelt: 'violet',
  indice_local: 'amber',
};

function QueryCard({ query }: { query: PlannedQuery }) {
  const [copied, setCopied] = useState(false);
  return (
    <li className="hud-reveal rounded-xl border border-sky-400/15 bg-black/30 p-3 transition-colors duration-300 hover:border-sky-400/40 hover:bg-sky-400/[0.04]">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <HudChip tone={PROVIDER_TONE[query.provider]}>{query.provider_label}</HudChip>
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
        <HudButton
          variant="ghost"
          size="sm"
          className="shrink-0"
          onClick={() => {
            void copyText(query.text).then((ok) => {
              setCopied(ok);
              window.setTimeout(() => {
                setCopied(false);
              }, 1500);
            });
          }}
        >
          {copied ? 'Copiado' : 'Copiar'}
        </HudButton>
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
    <HudPanel className="hud-reveal p-5">
      <section aria-labelledby="probar-concepto">
        <h3 id="probar-concepto" className="hud-kicker">
          Probar concepto
        </h3>
        <p className="mt-2 text-xs text-slate-400">
          Muestra las consultas exactas que se enviarían. No se envía nada ni se gastan créditos.
        </p>

        <div className="mt-3 space-y-2">
          <SearchBox onSelect={setRegion} />
          <div className="flex flex-wrap items-center gap-2">
            <div
              role="radiogroup"
              aria-label="Rango de fechas"
              className="hud-seg min-w-[16rem]"
              style={
                {
                  '--seg-i': Math.max(
                    0,
                    RANGES.findIndex((range) => range.days === days),
                  ),
                  '--seg-n': RANGES.length,
                } as CSSProperties
              }
            >
              {RANGES.map((range) => (
                <button
                  key={range.days}
                  type="button"
                  role="radio"
                  aria-checked={days === range.days}
                  onClick={() => {
                    setDays(range.days);
                  }}
                  className="focus-visible:outline-2 focus-visible:outline-sky-400"
                >
                  {range.label}
                </button>
              ))}
            </div>
            <HudButton
              variant="solid"
              size="sm"
              className="ml-auto"
              disabled={region === null || preview.isPending}
              onClick={() => {
                if (region) preview.mutate({ regionId: region.id, days, draft });
              }}
            >
              {preview.isPending ? 'Armando…' : 'Ver consultas'}
            </HudButton>
          </div>
          {region === null && (
            <p className="text-xs text-slate-500">
              Elige una región para probar, por ejemplo Jalisco.
            </p>
          )}
        </div>

        {preview.error && (
          <p
            role="alert"
            className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200"
          >
            {preview.error.message}
          </p>
        )}

        {result && (
          <div className="mt-4" aria-live="polite">
            <p className="mb-2 text-xs text-slate-400">
              <span className="text-slate-200">{result.region.breadcrumb}</span> ·{' '}
              {result.window.description} · {result.total_queries} consultas · ~
              {result.total_credits} crédito{result.total_credits === 1 ? '' : 's'} de SearchApi por
              página (hasta 3 páginas)
            </p>
            <ul className="space-y-2">
              {result.queries.map((query, index) => (
                <QueryCard key={`${query.provider}-${String(index)}`} query={query} />
              ))}
            </ul>
          </div>
        )}
      </section>
    </HudPanel>
  );
}
