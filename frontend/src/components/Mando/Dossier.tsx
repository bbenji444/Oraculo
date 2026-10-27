/**
 * Expediente de la misión (Centro de mando): los resultados a la derecha,
 * para que el globo quede a la izquierda con las notas.
 *
 * Arriba va el resumen, de vidrio y con color:
 * - un título que se descifra;
 * - cuatro cifras que corren, cada una con su color: relevantes, estados,
 *   créditos y costo de la IA;
 * - una barra con las categorías que más salen;
 * - las descargas.
 *
 * «▴» pliega el resumen a un renglón para que la lista de abajo tenga casi
 * todo el alto. Benji pidió poder cerrar lo de arriba por separado y ver
 * «un listado mucho más grande» (27/10/2026).
 *
 * Abajo va la misma cronología o lista del diseño de columna, más grande y
 * con letra más clara (`.mando-feed`). «›» oculta todo el expediente (el
 * globo se recentra) y una pestaña en el borde lo vuelve a abrir.
 *
 * No hace: no filtra por su cuenta; muestra las mismas notas que el globo.
 */
import { type CSSProperties, useEffect } from 'react';

import type { Article, Search } from '../../services/searches';
import { useMandoStore } from '../../store/mando';
import { useTimelineStore } from '../../store/timeline';
import { Chronology } from '../Explore/Chronology';
import { DownloadButtons } from '../Explore/Controls';
import { formatRange, providersLabel } from '../Explore/format';
import { ResultsList } from '../Explore/ResultsList';
import { categoriesIn, statesIn } from '../Explore/timelineData';
import { CountUp } from '../ui/CountUp';
import { DecodeText } from '../ui/DecodeText';
import { HudSegmented } from '../ui/HudSegmented';
import { MANDO_GLASS } from './ui';

// Categorías en la barra: las que más salen; el resto no se distinguiría.
const TOP_CATEGORIES = 5;
// Colores de la consola para los tramos de la barra: cian, verde, violeta,
// azul cielo y turquesa. Sin ámbar ni naranja (Benji, 27/10/2026).
const CATEGORY_COLORS = ['#00d2ff', '#2cf5a0', '#9b8cff', '#38bdf8', '#5eead4'];
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
      <dd className="hud-kpi-value mt-1.5">
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
  const title = `${search.concepts.map((c) => c.name).join(', ')} · ${search.region_name}`;
  return (
    <aside
      aria-label="Expediente de la misión"
      className="mando-dossier pointer-events-none absolute inset-y-4 right-4 flex w-[calc(100%-2rem)] flex-col gap-3 sm:w-[30rem]"
    >
      <section
        aria-label="Resumen de la misión"
        className={`${MANDO_GLASS} pointer-events-auto shrink-0 space-y-3 p-4`}
      >
        {/* Un haz recorre el resumen al llegar los resultados. */}
        <span aria-hidden="true" key={search.search_id} className="hud-scan" />
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="mando-kicker">Expediente</p>
            <h2
              className="mt-1.5 truncate text-[15px] leading-snug font-semibold text-slate-50"
              title={title}
            >
              <DecodeText text={title} />
            </h2>
            {summaryOpen ? (
              <p className="mt-1 text-[11px] text-slate-400">
                {formatRange(search.date_from, search.date_to)}
                {search.providers && search.providers.length > 0
                  ? ` · ${providersLabel(search.providers)}`
                  : ''}
              </p>
            ) : (
              // Plegado: las cifras en un renglón, para no perderlas de vista.
              <p className="mt-1 text-[11px] text-slate-300">
                <span className="text-sky-300">{shown.length}</span> relevantes ·{' '}
                <span className="text-emerald-300">{states.length}</span> estados ·{' '}
                {search.credits_used} créditos · IA {usd(search.llm_cost_usd)} USD
              </p>
            )}
          </div>
          <button
            type="button"
            aria-expanded={summaryOpen}
            onClick={() => {
              setSummaryOpen(!summaryOpen);
            }}
            title={summaryOpen ? 'Plegar el resumen para ver más noticias' : 'Desplegar el resumen'}
            aria-label={summaryOpen ? 'Plegar el resumen' : 'Desplegar el resumen'}
            className="hud-icon-btn size-8 text-sm"
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
            className="hud-icon-btn size-8 text-sm"
          >
            ›
          </button>
        </div>

        {summaryOpen && (
          <div className="mando-summary space-y-3">
            <dl className="grid grid-cols-4 gap-2">
              <Kpi label="Relevantes" value={shown.length} tone="cyan" order={0} />
              <Kpi label="Estados" value={states.length} tone="green" order={1} />
              <Kpi label="Créditos" value={search.credits_used} tone="violet" order={2} />
              <Kpi label="IA USD" value={search.llm_cost_usd} tone="sky" order={3} format={usd} />
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
                        // El brillo del tramo (currentColor en mando.css) es de su color.
                        color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                        animationDelay: `${String(i * KPI_STAGGER_MS)}ms`,
                      }}
                    />
                  ))}
                </div>
                <ul
                  aria-label="Categorías que más salen"
                  className="flex flex-wrap gap-x-3 gap-y-1"
                >
                  {categories.map((category, i) => (
                    <li
                      key={category.id}
                      className="flex items-center gap-1.5 text-[10.5px] text-slate-300"
                    >
                      <span
                        aria-hidden="true"
                        className="size-1.5 rounded-full"
                        style={{
                          backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                          boxShadow: `0 0 6px ${CATEGORY_COLORS[i % CATEGORY_COLORS.length] ?? ''}`,
                        }}
                      />
                      {category.name} <span className="text-slate-500">{category.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <DownloadButtons searchId={search.search_id} />
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
      </section>

      {/* Más grande y con letra más clara que en la columna (styles/mando.css). */}
      <div className="mando-feed pointer-events-auto flex min-h-0 flex-1 flex-col">
        {listOpen ? (
          <ResultsList articles={shown} total={articles.length} colors={colors} />
        ) : (
          <Chronology articles={relevant} />
        )}
      </div>
    </aside>
  );
}
