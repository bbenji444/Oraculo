/**
 * Línea del tiempo de Explorar (F12.7, plan F12 §4.6): la pieza central del
 * monitor FGR. Abajo, sobre el globo:
 *
 * - **Histograma** de cuándo se publicaron las notas, por hora (si la búsqueda
 *   cubre hasta 3 días) o por día, en hora de la CDMX, con los 3 picos
 *   resaltados en cian. Elegir una barra filtra ese tramo; otra vez lo quita.
 * - **Filtros** por categoría (el delito, F12.4) y por estado.
 * - **Tira cronológica**: las notas en orden de cuándo ocurrieron (la fecha del
 *   hecho si la IA la dedujo, ◆; si no, la de publicación, ●), o de cuándo se
 *   publicaron. Elegir una es lo mismo que elegirla en el globo: el mapa vuela
 *   hacia ella.
 *
 * Los filtros viven en `useTimelineStore` y `ExplorePage` los aplica a la lista
 * que usan el globo y la lista de noticias, así todo queda sincronizado.
 *
 * No hace: no pide datos ni calcula los tramos (eso es `timelineData.ts`).
 */
import { type Ref, useEffect, useMemo, useRef } from 'react';

import type { Article } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import { CategoryTag } from './CategoryTag';
import {
  applyTimeline,
  buildTimeline,
  categoriesIn,
  chronological,
  momentFor,
  type OrderBasis,
  statesIn,
  type TimelineBucket,
  type TimelineUnit,
} from './timelineData';
import { GLASS, PANEL_TITLE } from './ui';

const MEXICO_CITY = 'America/Mexico_City';
const HOUR_LABEL = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});
const DAY_LABEL = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  day: 'numeric',
  month: 'short',
});
const DAY_AND_HOUR = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});
/** Notas en la tira: más no se alcanzan a ver y vuelven lenta la página. */
const STRIP_LIMIT = 80;
/** Cada cuántas barras se rotula el eje para que los rótulos no se encimen. */
const LABEL_EVERY_HOURS = 6;
const LABEL_EVERY_DAYS = 2;

function day(ms: number): string {
  return DAY_LABEL.format(new Date(ms)).replace('.', '');
}

function bucketLabel(bucket: TimelineBucket, unit: TimelineUnit): string {
  const start = new Date(bucket.start);
  if (unit === 'day') return day(bucket.start);
  return `${day(bucket.start)}, ${HOUR_LABEL.format(start)}`;
}

function axisLabel(bucket: TimelineBucket, unit: TimelineUnit, index: number): string | null {
  if (unit === 'day') return index % LABEL_EVERY_DAYS === 0 ? day(bucket.start) : null;
  if (index % LABEL_EVERY_HOURS !== 0) return null;
  const hour = HOUR_LABEL.format(new Date(bucket.start));
  // A medianoche se dice el día; si no, la hora.
  return hour === '00:00' ? day(bucket.start) : hour.replace(':00', ' h');
}

interface HistogramProps {
  buckets: TimelineBucket[];
  unit: TimelineUnit;
  max: number;
  range: readonly [number, number] | null;
  onPick: (range: readonly [number, number]) => void;
}

function Histogram({ buckets, unit, max, range, onPick }: HistogramProps) {
  return (
    <div className="flex h-20 items-end gap-px" role="group" aria-label="Notas por tramo">
      {buckets.map((bucket, index) => {
        const count = bucket.articleIds.length;
        const selected = range !== null && range[0] === bucket.start;
        const dimmed = range !== null && !selected;
        const label = axisLabel(bucket, unit, index);
        return (
          <button
            key={bucket.start}
            type="button"
            disabled={count === 0}
            aria-pressed={selected}
            aria-label={`${bucketLabel(bucket, unit)}: ${String(count)} notas${bucket.peak ? ' (pico)' : ''}`}
            title={`${bucketLabel(bucket, unit)} · ${String(count)} notas`}
            onClick={() => {
              onPick([bucket.start, bucket.end]);
            }}
            className="group relative flex h-full min-w-[3px] flex-1 flex-col justify-end focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-default"
          >
            <span
              className={`block w-full rounded-t-sm transition-[height,background-color] duration-300 ${
                bucket.peak
                  ? 'bg-sky-400 shadow-[0_0_10px_rgb(0_210_255/0.6)]'
                  : 'bg-sky-400/45 group-hover:bg-sky-300/70'
              } ${selected ? 'ring-1 ring-sky-100' : ''} ${dimmed ? 'opacity-30' : ''}`}
              style={{
                height: count === 0 ? '1px' : `${String(Math.max(8, (count / max) * 100))}%`,
              }}
            />
            {label && (
              <span className="pointer-events-none absolute -bottom-4 left-0 whitespace-nowrap text-[9px] text-slate-500">
                {label}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

interface StripProps {
  articles: Article[];
  basis: OrderBasis;
  selectedId: number | null;
  selectedRef: Ref<HTMLButtonElement>;
  onSelect: (articleId: number) => void;
}

function Strip({ articles, basis, selectedId, selectedRef, onSelect }: StripProps) {
  if (articles.length === 0) {
    return <p className="py-3 text-xs text-slate-400">No hay notas con estos filtros.</p>;
  }
  return (
    <ol className="flex gap-2 overflow-x-auto pb-1" aria-label="Notas en orden cronológico">
      {articles.slice(0, STRIP_LIMIT).map((article) => {
        const moment = momentFor(article, basis);
        const isSelected = article.article_id === selectedId;
        return (
          <li key={article.article_id} className="w-56 shrink-0">
            <button
              ref={isSelected ? selectedRef : undefined}
              type="button"
              aria-current={isSelected}
              onClick={() => {
                onSelect(article.article_id);
              }}
              className={`flex h-full w-full flex-col gap-1 rounded-xl border px-2.5 py-2 text-left transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 ${
                isSelected
                  ? 'border-sky-400/60 bg-sky-500/15 shadow-glow'
                  : 'border-white/10 bg-white/[0.03] hover:bg-white/[0.07]'
              }`}
            >
              <span
                className="font-display text-[10px] tracking-wider text-sky-300"
                title={
                  moment?.kind === 'event'
                    ? 'Fecha del hecho (según la nota)'
                    : 'Fecha de publicación'
                }
              >
                {moment?.kind === 'event' ? '◆ ' : '● '}
                {moment
                  ? moment.kind === 'event'
                    ? day(moment.at)
                    : DAY_AND_HOUR.format(new Date(moment.at)).replace('.', '')
                  : 'sin fecha'}
              </span>
              <span className="line-clamp-2 text-[12px] leading-snug text-slate-100">
                {article.title}
              </span>
              <CategoryTag article={article} />
            </button>
          </li>
        );
      })}
    </ol>
  );
}

interface TimelineProps {
  /** Notas que se ven (ya sin las no relevantes si así lo pidió), antes de estos filtros. */
  articles: Article[];
}

export function Timeline({ articles }: TimelineProps) {
  const {
    open,
    orderBasis,
    range,
    categoryId,
    stateCode,
    setOpen,
    setOrderBasis,
    toggleRange,
    setCategory,
    setState,
    clear,
  } = useTimelineStore();
  const selectedId = useExplorerStore((s) => s.articleId);
  const selectArticle = useExplorerStore((s) => s.selectArticle);
  const selectedRef = useRef<HTMLButtonElement>(null);

  // Las barras respetan categoría y estado, pero no el tramo: así se ve dónde cae.
  const forBars = useMemo(
    () => applyTimeline(articles, { range: null, categoryId, stateCode }),
    [articles, categoryId, stateCode],
  );
  const timeline = useMemo(() => buildTimeline(forBars), [forBars]);
  const strip = useMemo(
    () => chronological(applyTimeline(articles, { range, categoryId, stateCode }), orderBasis),
    [articles, range, categoryId, stateCode, orderBasis],
  );
  const categories = useMemo(() => categoriesIn(articles), [articles]);
  const states = useMemo(() => statesIn(articles), [articles]);
  const filtered = range !== null || categoryId !== null || stateCode !== null;

  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }, [selectedId]);

  return (
    <section aria-label="Línea del tiempo" className={`${GLASS} flex flex-col gap-2 px-4 py-3`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <h2 className={PANEL_TITLE}>Línea del tiempo</h2>
        <span className="text-[11px] text-slate-400">
          {strip.length} notas · publicadas por {timeline.unit === 'hour' ? 'hora' : 'día'} (CDMX)
          {timeline.undated > 0 ? ` · ${String(timeline.undated)} sin fecha` : ''}
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {open && (
            <>
              <button
                type="button"
                onClick={() => {
                  setOrderBasis(orderBasis === 'event' ? 'published' : 'event');
                }}
                title="Cómo se ordenan las notas de abajo"
                className="rounded-lg border border-white/10 px-2 py-1 text-[11px] text-slate-200 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-sky-400"
              >
                {orderBasis === 'event' ? '◆ Orden: cuándo ocurrió' : '● Orden: cuándo se publicó'}
              </button>
              <select
                aria-label="Filtrar por categoría"
                value={categoryId ?? ''}
                onChange={(event) => {
                  setCategory(event.target.value ? Number(event.target.value) : null);
                }}
                className="max-w-[13rem] rounded-lg border border-white/10 bg-slate-900/80 px-2 py-1 text-[11px] text-slate-200"
              >
                <option value="">Todas las categorías</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.count})
                  </option>
                ))}
              </select>
              <select
                aria-label="Filtrar por estado"
                value={stateCode ?? ''}
                onChange={(event) => {
                  setState(event.target.value || null);
                }}
                className="max-w-[11rem] rounded-lg border border-white/10 bg-slate-900/80 px-2 py-1 text-[11px] text-slate-200"
              >
                <option value="">Todos los estados</option>
                {states.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.name} ({s.count})
                  </option>
                ))}
              </select>
              {filtered && (
                <button
                  type="button"
                  onClick={clear}
                  className="rounded-lg px-2 py-1 text-[11px] text-sky-300 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-sky-400"
                >
                  Quitar filtros
                </button>
              )}
            </>
          )}
          <button
            type="button"
            aria-expanded={open}
            onClick={() => {
              setOpen(!open);
            }}
            className="rounded-lg px-2 py-1 text-[11px] text-slate-300 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            {open ? '▾ Ocultar' : '▸ Mostrar'}
          </button>
        </div>
      </div>
      {open && (
        <>
          {timeline.buckets.length > 0 ? (
            <div className="pb-4">
              <Histogram
                buckets={timeline.buckets}
                unit={timeline.unit}
                max={timeline.max}
                range={range}
                onPick={toggleRange}
              />
            </div>
          ) : (
            <p className="text-xs text-slate-400">Estas notas no traen fecha.</p>
          )}
          <Strip
            articles={strip}
            basis={orderBasis}
            selectedId={selectedId}
            selectedRef={selectedRef}
            onSelect={selectArticle}
          />
        </>
      )}
    </section>
  );
}
