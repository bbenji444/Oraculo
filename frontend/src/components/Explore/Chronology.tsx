/**
 * Cronología de Explorar (F12.7, ADR-0032; rediseño elegido por Benji el
 * 26/10/2026): en el panel izquierdo, debajo de la búsqueda, como un feed en
 * vivo. Al elegir un hecho se despliega su desglose: qué medios lo publicaron,
 * a qué hora, con qué titular y su link (el resumen, la categoría y quién
 * actúa los da la ficha que se abre en el globo; aquí no se repiten).
 *
 * - **Arriba**: cuántos hechos hay y una curva pequeña de cuántas notas se
 *   publicaron por hora (o por día), con los picos resaltados; un clic en la
 *   curva filtra esa hora. Filtros por categoría y estado.
 * - **La línea**: una línea vertical luminosa con la hora a la izquierda y
 *   cada hecho a la derecha, del más reciente al más viejo, agrupados por
 *   día. El mismo hecho en varios medios es una sola entrada («+7 medios»).
 *   Un clic vuela el globo hacia la nota.
 *
 * Los filtros viven en `useTimelineStore` y `ExplorePage` los aplica a la lista
 * que usa el globo, así todo queda sincronizado. El globo queda libre en el
 * centro; la lista de noticias del panel izquierdo solo sale con «☰ Lista».
 *
 * No hace: no pide datos ni calcula los tramos (eso es `timelineData.ts`).
 */
import { type Ref, useEffect, useMemo, useRef } from 'react';

import type { Article } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import {
  applyTimeline,
  buildTimeline,
  categoriesIn,
  noteMoment,
  statesIn,
  type StoryItem,
  storyItems,
  type TimelineBucket,
  type TimelineUnit,
} from './timelineData';
import { PANEL_TITLE } from './ui';

const MEXICO_CITY = 'America/Mexico_City';
const HOUR = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});
const DAY = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});
const SHORT_DAY = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  day: 'numeric',
  month: 'short',
});
/** Lienzo de la curva pequeña (se estira al ancho del panel). */
const SPARK_WIDTH = 300;
const SPARK_HEIGHT = 38;
/** Aire arriba del hecho elegido al desplazar la lista (deja ver el encabezado del día). */
const SCROLL_MARGIN_PX = 36;
/** Vidrio homologado con OSINT (`--vidrio`, `--borde`, desenfoque de 14 px). */
const GLASS_OSINT =
  'rounded-2xl border border-sky-400/15 bg-[#050505]/70 shadow-[0_26px_60px_-22px_rgb(0_0_0/0.9)] backdrop-blur-[14px]';
const PILL =
  'rounded-full border border-sky-400/15 bg-white/[0.03] px-2.5 py-1 text-[11px] text-slate-200 transition-colors hover:border-sky-400/40 focus-visible:outline-2 focus-visible:outline-sky-400';

function shortDay(ms: number): string {
  return SHORT_DAY.format(new Date(ms)).replace('.', '');
}

/** « ENTRE 05:17 Y 09:40» si las notas del hecho salieron a distintas horas. */
function spanLabel(notes: readonly Article[]): string {
  const times = notes
    .map((note) => (note.published_at ? Date.parse(note.published_at) : Number.NaN))
    .filter((ms) => Number.isFinite(ms));
  if (times.length < 2) return '';
  const first = HOUR.format(new Date(Math.min(...times)));
  const last = HOUR.format(new Date(Math.max(...times)));
  return first === last ? '' : ` ENTRE ${first} Y ${last}`;
}

function bucketLabel(bucket: TimelineBucket, unit: TimelineUnit): string {
  if (unit === 'day') return shortDay(bucket.start);
  return `${shortDay(bucket.start)}, ${HOUR.format(new Date(bucket.start))}`;
}

interface SparkProps {
  buckets: TimelineBucket[];
  unit: TimelineUnit;
  max: number;
  range: readonly [number, number] | null;
  onPick: (range: readonly [number, number]) => void;
}

/** La curva pequeña de notas por hora: barras finas que brillan en los picos. */
function Spark({ buckets, unit, max, range, onPick }: SparkProps) {
  const n = buckets.length;
  const slot = SPARK_WIDTH / Math.max(1, n);
  return (
    <div className="relative" style={{ height: `${String(SPARK_HEIGHT)}px` }}>
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox={`0 0 ${String(SPARK_WIDTH)} ${String(SPARK_HEIGHT)}`}
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {buckets.map((bucket, index) => {
          const count = bucket.articleIds.length;
          const h = max ? Math.max(count ? 2 : 0.6, (count / max) * (SPARK_HEIGHT - 4)) : 0;
          const selected = range !== null && range[0] === bucket.start;
          const dim = range !== null && !selected;
          return (
            <rect
              key={bucket.start}
              x={index * slot + slot * 0.18}
              y={SPARK_HEIGHT - h}
              width={slot * 0.64}
              height={h}
              rx={Math.min(1.5, slot * 0.3)}
              fill="#00d2ff"
              fillOpacity={dim ? 0.15 : bucket.peak || selected ? 0.95 : 0.4}
            />
          );
        })}
      </svg>
      {/* Botones invisibles por tramo: un clic filtra esa hora. */}
      <div className="absolute inset-0 flex">
        {buckets.map((bucket) => {
          const count = bucket.articleIds.length;
          return (
            <button
              key={bucket.start}
              type="button"
              disabled={count === 0}
              aria-pressed={range !== null && range[0] === bucket.start}
              aria-label={`${bucketLabel(bucket, unit)}: ${String(count)} notas${bucket.peak ? ' (pico)' : ''}`}
              title={`${bucketLabel(bucket, unit)} · ${String(count)} notas`}
              onClick={() => {
                onPick([bucket.start, bucket.end]);
              }}
              className="h-full flex-1 focus-visible:outline-1 focus-visible:outline-sky-300 disabled:cursor-default"
            />
          );
        })}
      </div>
    </div>
  );
}

interface EntryProps {
  item: StoryItem;
  selected: boolean;
  selectedRef: Ref<HTMLButtonElement>;
  onSelect: (articleId: number) => void;
}

function Entry({ item, selected, selectedRef, onSelect }: EntryProps) {
  const article = item.lead;
  const others = item.articleIds.length - 1;
  const event = noteMoment(article);
  const place = article.primary_location?.place;
  return (
    <li className="relative pl-[3.6rem]">
      {/* La hora, a la izquierda de la línea. */}
      <span className="absolute left-0 top-[0.55rem] w-10 text-right font-display text-[10px] tabular-nums text-sky-300/90">
        {HOUR.format(new Date(item.at))}
      </span>
      {/* El nodo sobre la línea: más grande y brillante si lo publicaron varios medios. */}
      <span
        aria-hidden="true"
        className={`absolute left-[2.95rem] top-[0.7rem] -translate-x-1/2 rounded-full ${
          selected
            ? 'size-3 bg-white shadow-[0_0_12px_rgb(255_255_255/0.9)]'
            : others > 0
              ? 'size-2.5 bg-sky-300 shadow-[0_0_10px_rgb(0_210_255/0.9)]'
              : 'size-2 bg-sky-400/80 shadow-[0_0_6px_rgb(0_210_255/0.6)]'
        }`}
      />
      <div
        className={`rounded-lg transition-colors ${selected ? 'bg-sky-400/[0.1] ring-1 ring-sky-400/30' : ''}`}
      >
        <button
          ref={selected ? selectedRef : undefined}
          type="button"
          aria-expanded={selected}
          onClick={() => {
            onSelect(article.article_id);
          }}
          className={`w-full rounded-lg px-2 py-1.5 text-left focus-visible:outline-2 focus-visible:outline-sky-400 ${
            selected ? '' : 'hover:bg-white/[0.05]'
          }`}
        >
          <span className="line-clamp-2 text-[12.5px] leading-snug text-slate-100">
            {article.title}
          </span>
          <span className="mt-0.5 block truncate text-[10.5px] text-slate-400">
            {others > 0 && (
              <span className="text-sky-300">
                +{others} medio{others === 1 ? '' : 's'} ·{' '}
              </span>
            )}
            {place ?? article.source_name ?? article.source_domain ?? ''}
            {article.category ? ` · ${article.category.name}` : ''}
          </span>
          {event?.kind === 'event' && (
            <span className="mt-0.5 block text-[10.5px] text-amber-200/80">
              ◆ El hecho ocurrió el {shortDay(event.at)}
            </span>
          )}
        </button>
        {selected && (
          // Desglose: solo lo que la ficha del globo no dice. El resumen, la
          // categoría y quién actúa ya salen en la ficha; repetirlos era leer lo
          // mismo dos veces (Benji, 26/10). Aquí va cómo se contó: qué medios lo
          // publicaron, a qué hora y con qué titular (si es otro).
          <div className="px-2 pb-2.5 pt-0.5 text-[11.5px]">
            <p className="font-display text-[9px] tracking-wider text-slate-400">
              {item.notes.length === 1
                ? 'SOLO LO PUBLICÓ UN MEDIO'
                : `LO PUBLICARON ${String(item.notes.length)} MEDIOS${spanLabel(item.notes)}`}
            </p>
            <ul className="mt-1 space-y-1">
              {item.notes.map((note) => (
                <li key={note.article_id} className="flex items-baseline gap-1.5">
                  <span className="w-8 shrink-0 tabular-nums text-[10px] text-slate-500">
                    {note.published_at ? HOUR.format(new Date(note.published_at)) : '—'}
                  </span>
                  <span className="min-w-0">
                    <a
                      href={note.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-sky-300 hover:text-sky-100 hover:underline"
                    >
                      {note.source_name ?? note.source_domain ?? 'Medio sin nombre'} ↗
                    </a>
                    {note.title !== article.title && (
                      <span
                        className="block truncate text-[10.5px] text-slate-400"
                        title={note.title}
                      >
                        {note.title}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </li>
  );
}

interface ChronologyProps {
  /** Notas que se ven (ya sin las no relevantes si así lo pidió), antes de estos filtros. */
  articles: Article[];
}

export function Chronology({ articles }: ChronologyProps) {
  const {
    open,
    listOpen,
    range,
    categoryId,
    stateCode,
    setOpen,
    setListOpen,
    toggleRange,
    setCategory,
    setState,
    clear,
  } = useTimelineStore();
  const selectedId = useExplorerStore((s) => s.articleId);
  const selectArticle = useExplorerStore((s) => s.selectArticle);
  const selectedRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // La curva respeta categoría y estado; la lista, además, el tramo elegido.
  const forSpark = useMemo(
    () => applyTimeline(articles, { range: null, categoryId, stateCode }),
    [articles, categoryId, stateCode],
  );
  const timeline = useMemo(() => buildTimeline(forSpark), [forSpark]);
  const items = useMemo(
    () => storyItems(applyTimeline(articles, { range, categoryId, stateCode })),
    [articles, range, categoryId, stateCode],
  );
  const days = useMemo(() => {
    const groups: { day: string; at: number; items: StoryItem[] }[] = [];
    for (const item of items) {
      const last = groups[groups.length - 1];
      if (last?.day === item.day) last.items.push(item);
      else groups.push({ day: item.day, at: item.at, items: [item] });
    }
    return groups;
  }, [items]);
  const categories = useMemo(() => categoriesIn(articles), [articles]);
  const states = useMemo(() => statesIn(articles), [articles]);
  const filtered = range !== null || categoryId !== null || stateCode !== null;
  const notes = items.reduce((total, item) => total + item.articleIds.length, 0);

  // Solo se desplaza la lista: `scrollIntoView` también movía la página entera
  // (el globo se subía y quedaba una franja negra abajo).
  useEffect(() => {
    const list = listRef.current;
    const row = selectedRef.current;
    if (!list || !row) return;
    const box = list.getBoundingClientRect();
    const target = row.getBoundingClientRect();
    if (target.top < box.top || target.bottom > box.bottom) {
      list.scrollBy({ top: target.top - box.top - SCROLL_MARGIN_PX, behavior: 'smooth' });
    }
  }, [selectedId]);

  if (!open) {
    return (
      <button
        type="button"
        aria-expanded={false}
        onClick={() => {
          setOpen(true);
        }}
        className={`${GLASS_OSINT} px-3 py-2 text-xs text-slate-100 hover:border-sky-400/40 focus-visible:outline-2 focus-visible:outline-sky-400`}
      >
        <span className={PANEL_TITLE}>Cronología</span>{' '}
        <span className="text-slate-400">· {items.length} hechos ‹</span>
      </button>
    );
  }

  return (
    <section
      aria-label="Cronología"
      className={`${GLASS_OSINT} flex max-h-full w-full min-w-0 flex-col`}
    >
      <div className="space-y-2 border-b border-sky-400/10 px-4 pb-3 pt-3">
        <div className="flex items-center gap-2">
          <h2 className={`${PANEL_TITLE} drop-shadow-[0_0_8px_rgb(0_210_255/0.55)]`}>Cronología</h2>
          <span className="text-[11px] text-slate-400">
            {items.length} hechos · {notes} notas
          </span>
          <button
            type="button"
            aria-expanded
            onClick={() => {
              setOpen(false);
            }}
            title="Ocultar la cronología"
            className="ml-auto rounded-md px-1.5 text-sm text-slate-400 hover:text-slate-100 focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            ›
          </button>
        </div>
        {timeline.buckets.length > 0 && (
          <div>
            <Spark
              buckets={timeline.buckets}
              unit={timeline.unit}
              max={timeline.max}
              range={range}
              onPick={toggleRange}
            />
            <p className="mt-1 text-[10px] text-slate-500">
              Notas publicadas por {timeline.unit === 'hour' ? 'hora' : 'día'} (CDMX) · un clic
              filtra ese momento
            </p>
          </div>
        )}
        <div className="flex flex-wrap gap-1.5">
          <select
            aria-label="Filtrar por categoría"
            value={categoryId ?? ''}
            onChange={(event) => {
              setCategory(event.target.value ? Number(event.target.value) : null);
            }}
            className={`${PILL} max-w-[11rem] bg-[#050505]`}
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
            className={`${PILL} max-w-[9rem] bg-[#050505]`}
          >
            <option value="">Todos los estados</option>
            {states.map((s) => (
              <option key={s.code} value={s.code}>
                {s.name} ({s.count})
              </option>
            ))}
          </select>
          {filtered && (
            <button type="button" onClick={clear} className={`${PILL} text-sky-300`}>
              ✕ Quitar
            </button>
          )}
          <button
            type="button"
            aria-pressed={listOpen}
            onClick={() => {
              setListOpen(!listOpen);
            }}
            title="Mostrar u ocultar la lista de noticias del panel izquierdo"
            className={`${PILL} ${listOpen ? 'border-sky-400/50 text-sky-200' : ''}`}
          >
            ☰ Lista
          </button>
        </div>
      </div>

      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {days.length === 0 && (
          <p className="px-1 py-4 text-xs text-slate-400">No hay notas con estos filtros.</p>
        )}
        {days.map((group) => (
          <div key={group.day} className="relative">
            <p className="sticky top-0 z-10 -mx-3 bg-[#050505]/85 px-4 py-1.5 font-display text-[10px] font-bold uppercase tracking-[0.16em] text-sky-200/90 backdrop-blur">
              {DAY.format(new Date(group.at))}
            </p>
            {/* La línea vertical luminosa que une los hechos del día. */}
            <span
              aria-hidden="true"
              className="absolute bottom-2 left-[2.95rem] top-9 w-px -translate-x-1/2 bg-gradient-to-b from-sky-400/70 via-sky-400/30 to-sky-400/0"
            />
            <ol className="space-y-0.5" aria-label={`Hechos del ${DAY.format(new Date(group.at))}`}>
              {group.items.map((item) => (
                <Entry
                  key={item.lead.article_id}
                  item={item}
                  selected={selectedId !== null && item.articleIds.includes(selectedId)}
                  selectedRef={selectedRef}
                  onSelect={selectArticle}
                />
              ))}
            </ol>
          </div>
        ))}
      </div>
    </section>
  );
}
