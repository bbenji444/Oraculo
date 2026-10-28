/**
 * Expediente de la consulta (Centro de mando): los resultados a la derecha,
 * para que el globo quede a la izquierda con las notas.
 *
 * Dos paneles:
 * - **Resumen**, de vidrio y con color: título que se descifra, el PDF, cuatro
 *   cifras que corren (relevantes, estados, créditos y costo de la IA) y una
 *   barra con las categorías que más salen, cada una de su color. «▴» lo
 *   pliega a un renglón.
 * - **Noticias**: arriba las pestañas «Cronología | Noticias», en el mismo
 *   lugar para las dos vistas; abajo la cronología o la lista, compactas, para
 *   que quepan muchas (Benji, 28/10/2026: «quiero que en el listado de
 *   noticias se vean muchas más noticias»).
 *
 * «›» oculta todo el expediente (el globo se recentra) y una pestaña en el
 * borde lo vuelve a abrir.
 *
 * No hace: no filtra por su cuenta; muestra las mismas notas que el globo.
 */
import { type CSSProperties, useEffect } from 'react';

import type { Article, Search } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useMandoStore } from '../../store/mando';
import { useTimelineStore } from '../../store/timeline';
import { categoryColor } from '../Explore/categoryColor';
import { Chronology } from '../Explore/Chronology';
import { DownloadButtons } from '../Explore/Controls';
import { formatRange, matchesListFilter, providersLabel } from '../Explore/format';
import { ResultsList } from '../Explore/ResultsList';
import { categoriesIn, statesIn } from '../Explore/timelineData';
import { GLASS } from '../Explore/ui';
import { CountUp } from '../ui/CountUp';
import { DecodeText } from '../ui/DecodeText';
import { HudSegmented } from '../ui/HudSegmented';
import { ActivityTimeline } from './ActivityTimeline';
import { FilterPopover } from './FilterPopover';
import { windowLabel } from './mission';
import { MANDO_GLASS } from './ui';

// Categorías en la barra: las que más salen; el resto no se distinguiría.
const TOP_CATEGORIES = 5;
// Las que se nombran debajo de la barra, en un solo renglón (todas se ven al
// pasar el mouse por la barra): así el resumen ocupa menos alto.
const NAMED_CATEGORIES = 3;
// Retraso entre cifras al entrar, en milisegundos: entran una tras otra.
const KPI_STAGGER_MS = 90;
// Color de cada cifra, en «r g b» para que el CSS lo use con transparencia
// (--tone en styles/mando.css): cian, verde, violeta y azul cielo.
const KPI_TONES = {
  cyan: '0 210 255',
  green: '44 245 160',
  violet: '155 140 255',
  sky: '56 189 248',
} as const;

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

interface KpiProps {
  label: string;
  value: number;
  tone: keyof typeof KPI_TONES;
  order: number;
  format?: (value: number) => string;
}

/** Una cifra del resumen: vidrio teñido de su color, con un brillo que pasa. */
function Kpi({ label, value, tone, order, format }: KpiProps) {
  const style = {
    '--tone': KPI_TONES[tone],
    animationDelay: `${String(order * KPI_STAGGER_MS)}ms`,
    // El brillo de cada cifra pasa a destiempo de las demás.
    '--shine-delay': `${String(order * 0.7)}s`,
  } as CSSProperties;
  return (
    <div className="mando-kpi hud-reveal" style={style}>
      <dt className="hud-kpi-label">{label}</dt>
      <dd className="hud-kpi-value">
        <CountUp value={value} format={format} />
      </dd>
    </div>
  );
}

const usd = (value: number) => value.toFixed(3);

export function Dossier({ search, articles, relevant, shown, colors }: DossierProps) {
  const open = useMandoStore((s) => s.dossierOpen);
  const setOpen = useMandoStore((s) => s.setDossierOpen);
  const summaryOpen = useMandoStore((s) => s.summaryOpen);
  const setSummaryOpen = useMandoStore((s) => s.setSummaryOpen);
  const listOpen = useTimelineStore((s) => s.listOpen);
  const setListOpen = useTimelineStore((s) => s.setListOpen);
  const listFilter = useExplorerStore((s) => s.listFilter);

  // Cada consulta abre su cronología desplegada.
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
        title="Abrir el expediente de la consulta"
        className="hud-btn hud-btn--sm mando-edge-tab pointer-events-auto absolute right-0 top-1/2 -translate-y-1/2 bg-[#050d12]/90 px-2 py-4"
      >
        ‹ Expediente · {shown.length}
      </button>
    );
  }

  const states = statesIn(relevant);
  // El filtro de ubicación de «Filtro» vale para la cronología y la lista.
  const located = relevant.filter((a) => matchesListFilter(a, listFilter));
  const listed = shown.filter((a) => matchesListFilter(a, listFilter));
  const categories = categoriesIn(relevant).slice(0, TOP_CATEGORIES);
  const view: DossierView = listOpen ? 'list' : 'chrono';
  const title = `${search.concepts.map((c) => c.name).join(', ')} · ${search.region_name}`;
  const sources =
    search.providers && search.providers.length > 0 ? ` · ${providersLabel(search.providers)}` : '';
  return (
    <aside
      aria-label="Expediente de la consulta"
      className="mando-dossier pointer-events-none absolute inset-y-4 right-4 flex w-[calc(100%-2rem)] flex-col gap-2.5 sm:w-[30rem]"
    >
      <section
        aria-label="Resumen de la consulta"
        className={`${MANDO_GLASS} pointer-events-auto shrink-0 space-y-2 px-3.5 py-2.5`}
      >
        {/* Un haz recorre el resumen al llegar los resultados. */}
        <span aria-hidden="true" key={search.search_id} className="hud-scan" />
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            {/* Las corridas dicen sus horas: solo lo publicado desde la anterior. */}
            <p className="mando-kicker">
              Expediente · {windowLabel(search) ?? formatRange(search.date_from, search.date_to)}
            </p>
            <h2
              className="mt-1 truncate text-[14px] leading-snug font-semibold text-slate-50"
              title={`${title}${sources}`}
            >
              <DecodeText text={title} />
            </h2>
          </div>
          <div className="shrink-0">
            <DownloadButtons searchId={search.search_id} compact />
          </div>
          <button
            type="button"
            aria-expanded={summaryOpen}
            onClick={() => {
              setSummaryOpen(!summaryOpen);
            }}
            title={summaryOpen ? 'Plegar el resumen para ver más noticias' : 'Desplegar el resumen'}
            aria-label={summaryOpen ? 'Plegar el resumen' : 'Desplegar el resumen'}
            className="hud-icon-btn size-7 text-xs"
          >
            {summaryOpen ? '▴' : '▾'}
          </button>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
            }}
            title="Ocultar el expediente"
            aria-label="Ocultar el expediente"
            className="hud-icon-btn size-7 text-xs"
          >
            ›
          </button>
        </div>

        {summaryOpen ? (
          <div className="mando-summary space-y-2">
            <dl className="grid grid-cols-4 gap-1.5">
              <Kpi label="Relevantes" value={shown.length} tone="cyan" order={0} />
              <Kpi label="Estados" value={states.length} tone="green" order={1} />
              <Kpi label="Créditos" value={search.credits_used} tone="violet" order={2} />
              <Kpi label="IA USD" value={search.llm_cost_usd} tone="sky" order={3} format={usd} />
            </dl>
            {categories.length > 0 && (
              <div className="space-y-1.5">
                <div
                  className="mando-meter"
                  aria-hidden="true"
                  title={categories.map((c) => `${c.name}: ${String(c.count)}`).join(' · ')}
                >
                  {categories.map((category, i) => {
                    const color = categoryColor(category);
                    return (
                      <span
                        key={category.id}
                        style={{
                          flexGrow: category.count,
                          backgroundColor: color,
                          // El brillo del tramo (currentColor en mando.css) es de su color.
                          color,
                          animationDelay: `${String(i * KPI_STAGGER_MS)}ms`,
                        }}
                      />
                    );
                  })}
                </div>
                <ul
                  aria-label="Categorías que más salen"
                  className="flex flex-nowrap gap-x-3 overflow-hidden"
                >
                  {categories.slice(0, NAMED_CATEGORIES).map((category) => {
                    const color = categoryColor(category);
                    return (
                      <li
                        key={category.id}
                        className="flex min-w-0 shrink items-center gap-1.5 truncate text-[10.5px] text-slate-300"
                      >
                        <span
                          aria-hidden="true"
                          className="size-1.5 shrink-0 rounded-full"
                          style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}` }}
                        />
                        <span className="truncate">{category.name}</span>
                        <span className="text-slate-500">{category.count}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </div>
        ) : (
          // Plegado: las cifras en un renglón, para no perderlas de vista.
          <p className="text-[11px] text-slate-300">
            <span className="text-sky-300">{shown.length}</span> relevantes ·{' '}
            <span className="text-emerald-300">{states.length}</span> estados ·{' '}
            {search.credits_used} créditos · IA {usd(search.llm_cost_usd)} USD
          </p>
        )}
      </section>

      {/* Las pestañas van en el panel de las noticias, en el mismo lugar para la
          cronología y para la lista (Benji, 28/10/2026). */}
      <section
        aria-label="Listado de la consulta"
        className={`${GLASS} pointer-events-auto flex min-h-0 flex-1 flex-col`}
      >
        <div className="shrink-0 space-y-2 px-3 pt-2.5">
          <HudSegmented
            options={VIEWS}
            value={view}
            onChange={(next) => {
              setListOpen(next === 'list');
            }}
            label="Vista del expediente"
          />
          {/* Cuántas se ven y el botón «Filtro»: los mismos para las dos vistas. */}
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-slate-400">
              <span className="text-slate-200">{listed.length}</span> de {articles.length} notas
            </p>
            <FilterPopover articles={relevant} />
          </div>
          <ActivityTimeline articles={located} />
        </div>
        <div className="flex min-h-0 flex-1 flex-col">
          {listOpen ? (
            <ResultsList
              articles={shown}
              total={articles.length}
              colors={colors}
              variant="dossier"
            />
          ) : (
            <Chronology articles={located} variant="dossier" />
          )}
        </div>
      </section>
    </aside>
  );
}
