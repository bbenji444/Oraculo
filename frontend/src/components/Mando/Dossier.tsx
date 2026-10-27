/**
 * Expediente de la misión (diseño «Centro de mando»): los resultados a la
 * derecha, para que el globo quede a la izquierda con las notas.
 *
 * Arriba, la ficha de la misión: título que se descifra, cuatro cifras que
 * corren (notas, estados, créditos y costo de la IA), una barra con las
 * categorías que más salen, el cambio entre cronología y lista, y las
 * descargas. Abajo, la misma cronología o lista del diseño 2.
 *
 * «›» lo oculta (el globo se centra y crece) y una pestaña en el borde lo
 * vuelve a abrir.
 *
 * No hace: no filtra por su cuenta; muestra las mismas notas que el globo.
 */
import { useEffect } from 'react';

import type { Article, Search } from '../../services/searches';
import { useMandoStore } from '../../store/mando';
import { useTimelineStore } from '../../store/timeline';
import { Chronology } from '../Explore/Chronology';
import { DownloadButtons } from '../Explore/Controls';
import { formatRange, providersLabel } from '../Explore/format';
import { ResultsList } from '../Explore/ResultsList';
import { categoriesIn, statesIn } from '../Explore/timelineData';
import { GLASS } from '../Explore/ui';
import { CountUp } from '../ui/CountUp';
import { DecodeText } from '../ui/DecodeText';
import { HudSegmented } from '../ui/HudSegmented';

// Categorías en la barra: las que más salen; el resto no se distinguiría.
const TOP_CATEGORIES = 5;
// Un color de la consola por tramo de la barra (styles/hud.css).
const CATEGORY_COLORS = ['#00d2ff', '#2cf5a0', '#ffb547', '#9b8cff', '#ff4d6d'];
// Retraso entre cifras al entrar, en milisegundos: entran una tras otra.
const KPI_STAGGER_MS = 90;

type DossierView = 'chrono' | 'list';
const VIEWS = [
  { value: 'chrono', label: 'Cronología' },
  { value: 'list', label: 'Noticias' },
] as const;

interface DossierProps {
  search: Search;
  /** Todas las notas de la búsqueda. */
  articles: Article[];
  /** Las relevantes (o todas, con «No relevantes»). */
  relevant: Article[];
  /** Las que se ven en el globo, con los filtros de la cronología. */
  shown: Article[];
  colors: Map<number, string>;
}

function Kpi({
  label,
  value,
  format,
  order,
}: {
  label: string;
  value: number;
  format?: (value: number) => string;
  order: number;
}) {
  return (
    <div
      className="mando-kpi hud-reveal"
      style={{ animationDelay: `${String(order * KPI_STAGGER_MS)}ms` }}
    >
      <dt className="hud-kpi-label">{label}</dt>
      <dd className="hud-kpi-value mt-1.5">
        <CountUp value={value} format={format} />
      </dd>
    </div>
  );
}

export function Dossier({ search, articles, relevant, shown, colors }: DossierProps) {
  const open = useMandoStore((s) => s.dossierOpen);
  const setOpen = useMandoStore((s) => s.setDossierOpen);
  const listOpen = useTimelineStore((s) => s.listOpen);
  const setListOpen = useTimelineStore((s) => s.setListOpen);

  // Cada misión abre su cronología desplegada.
  useEffect(() => {
    useTimelineStore.getState().setOpen(true);
  }, [search.search_id]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
        title="Abrir el expediente de la misión"
        className="hud-btn hud-btn--sm mando-edge-tab pointer-events-auto absolute right-0 top-1/2 -translate-y-1/2 bg-[#050d12]/90 px-2 py-4"
      >
        ‹ Expediente · {shown.length}
      </button>
    );
  }

  const states = statesIn(relevant);
  const categories = categoriesIn(relevant).slice(0, TOP_CATEGORIES);
  const view: DossierView = listOpen ? 'list' : 'chrono';
  return (
    <aside
      aria-label="Expediente de la misión"
      className="mando-dossier pointer-events-none absolute inset-y-4 right-4 flex w-[calc(100%-2rem)] flex-col gap-3 sm:w-[26rem]"
    >
      <section className={`${GLASS} pointer-events-auto shrink-0 space-y-3.5 p-4`}>
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="mando-kicker">Expediente</p>
            <h2 className="mt-1.5 text-[15px] leading-snug font-semibold text-slate-50">
              <DecodeText
                text={`${search.concepts.map((c) => c.name).join(', ')} · ${search.region_name}`}
              />
            </h2>
            <p className="mt-1 text-[11px] text-slate-400">
              {formatRange(search.date_from, search.date_to)}
              {search.providers && search.providers.length > 0
                ? ` · ${providersLabel(search.providers)}`
                : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
            }}
            title="Ocultar el expediente"
            aria-label="Ocultar el expediente"
            className="hud-icon-btn size-8 text-sm"
          >
            ›
          </button>
        </div>

        <dl className="grid grid-cols-4 gap-2">
          <Kpi label="Relevantes" value={shown.length} order={0} />
          <Kpi label="Estados" value={states.length} order={1} />
          <Kpi label="Créditos" value={search.credits_used} order={2} />
          <Kpi
            label="IA USD"
            value={search.llm_cost_usd}
            format={(value) => value.toFixed(3)}
            order={3}
          />
        </dl>

        {categories.length > 0 && (
          <div className="space-y-2">
            <div className="mando-meter" aria-hidden="true">
              {categories.map((category, i) => (
                <span
                  key={category.id}
                  style={{
                    flexGrow: category.count,
                    backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                    animationDelay: `${String(i * KPI_STAGGER_MS)}ms`,
                  }}
                />
              ))}
            </div>
            <ul aria-label="Categorías que más salen" className="flex flex-wrap gap-x-3 gap-y-1">
              {categories.map((category, i) => (
                <li
                  key={category.id}
                  className="flex items-center gap-1.5 text-[10.5px] text-slate-300"
                >
                  <span
                    aria-hidden="true"
                    className="size-1.5 rounded-full"
                    style={{ backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }}
                  />
                  {category.name} <span className="text-slate-500">{category.count}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <HudSegmented
          options={VIEWS}
          value={view}
          onChange={(next) => {
            setListOpen(next === 'list');
          }}
          label="Vista del expediente"
        />
        <DownloadButtons searchId={search.search_id} />
      </section>

      <div className="pointer-events-auto flex min-h-0 flex-1 flex-col">
        {listOpen ? (
          <ResultsList articles={shown} total={articles.length} colors={colors} />
        ) : (
          <Chronology articles={relevant} />
        )}
      </div>
    </aside>
  );
}
