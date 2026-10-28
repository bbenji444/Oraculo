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
 * - **Temas**: si un nombre propio sale en 5 hechos o más («Jáuregui»), esos
 *   hechos se juntan en un bloque que se despliega (`themes.ts`).
 * - **La línea**: una línea vertical luminosa con la hora a la izquierda y
 *   cada hecho a la derecha, del más reciente al más viejo, agrupados por
 *   día. El mismo hecho en varios medios es una sola entrada («+7 medios»).
 *   Un clic vuela el globo hacia la nota del hecho mejor ubicada
 *   (`mapLead`); si ninguna dice dónde pasó, el renglón lo avisa («sin
 *   lugar») y la ficha se abre sin vuelo.
 * - **Dos acomodos**: el panel de la columna (`variant="column"`) y el
 *   expediente del Centro de mando (`variant="dossier"`), más compacto para
 *   que quepan más noticias (Benji, 27/10/2026).
 *
 * Los filtros viven en `useTimelineStore` y `ExplorePage` los aplica a la lista
 * que usa el globo, así todo queda sincronizado. El globo queda libre en el
 * centro; la lista de noticias del panel izquierdo solo sale con «☰ Lista».
 *
 * No hace: no pide datos ni calcula los tramos (eso es `timelineData.ts`).
 */
import { createContext, type Ref, useContext, useEffect, useMemo, useRef, useState } from 'react';

import type { Article } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import { hasMapPoint } from '../../map/newsLayers';
import {
  applyTimeline,
  buildTimeline,
  categoriesIn,
  mapLead,
  statesIn,
  type StoryItem,
  storyItems,
  type TimelineBucket,
  type TimelineUnit,
} from './timelineData';
import { CategoryTag } from './CategoryTag';
import { categoryColor } from './categoryColor';
import { eventDateNote } from './format';
import { type ChronologyRow, groupThemes, type ThemeBlock } from './themes';
import { PANEL_TITLE } from './ui';
import { ExternalLink } from '../ExternalLink';
import { HudSelect } from '../ui/HudSelect';

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
// En el expediente del Centro de mando la curva es más baja: deja lugar a las
// noticias (Benji: «que tenga un buen margen de visión», 27/10/2026).
const SPARK_HEIGHT_COMPACT = 26;
/** Aire arriba del hecho elegido al desplazar la lista (deja ver el encabezado del día). */
const SCROLL_MARGIN_PX = 36;
/** Vidrio homologado con OSINT (`--vidrio`, `--borde`, desenfoque de 14 px). */
// Panel de la consola táctica (ADR-0036). Sin backdrop-blur: desenfocar el
// globo de atrás cada cuadro costaba en la tarjeta integrada.
const GLASS_OSINT = 'hud-panel hud-spot bg-[#050505]/90';
const PILL =
  'rounded-full border border-sky-400/15 bg-white/[0.03] px-2.5 py-1 text-[11px] text-slate-200 transition-all duration-300 hover:-translate-y-px hover:border-sky-400/50 hover:shadow-[0_0_12px_rgb(0_210_255/0.25)] focus-visible:outline-2 focus-visible:outline-sky-400';

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
  height?: number;
  /** Texto del centro, entre la primera y la última hora (por defecto, qué mide). */
  caption?: string;
}

/**
 * La curva pequeña de notas por hora: barras finas que brillan en los picos.
 * Debajo dice de cuándo a cuándo va, para leerla sin pasar el mouse.
 */
function Spark({ buckets, unit, max, range, onPick, height = SPARK_HEIGHT, caption }: SparkProps) {
  const n = buckets.length;
  const slot = SPARK_WIDTH / Math.max(1, n);
  const first = buckets[0];
  const last = buckets[n - 1];
  return (
    <div>
      <div className="relative" style={{ height: `${String(height)}px` }}>
        <svg
          className="absolute inset-0 h-full w-full"
          viewBox={`0 0 ${String(SPARK_WIDTH)} ${String(height)}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {buckets.map((bucket, index) => {
            const count = bucket.articleIds.length;
            const h = max ? Math.max(count ? 2 : 0.6, (count / max) * (height - 4)) : 0;
            const selected = range !== null && range[0] === bucket.start;
            const dim = range !== null && !selected;
            return (
              <rect
                key={bucket.start}
                x={index * slot + slot * 0.18}
                y={height - h}
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
      {first && last && (
        <p className="mt-1 flex justify-between gap-2 text-[9.5px] tabular-nums text-slate-500">
          <span>{bucketLabel(first, unit)}</span>
          <span className="truncate text-slate-400">
            {caption ?? `notas por ${unit === 'hour' ? 'hora' : 'día'} · clic para filtrar`}
          </span>
          <span>{bucketLabel(last, unit)}</span>
        </p>
      )}
    </div>
  );
}

/**
 * Renglones de una línea (expediente del Centro de mando): el título completo
 * se ve al elegir el hecho o al pasar el mouse; así caben muchos más (Benji,
 * 28/10/2026). Se pasa por contexto para no cruzar todos los renglones.
 */
const DenseRows = createContext(false);

interface EntryProps {
  item: StoryItem;
  selected: boolean;
  selectedRef: Ref<HTMLButtonElement>;
  onSelect: (articleId: number) => void;
  /** Dentro de un tema los hechos son de varios días: se dice el día. */
  showDay?: boolean;
}

function Entry({ item, selected, selectedRef, onSelect, showDay = false }: EntryProps) {
  const dense = useContext(DenseRows);
  const article = item.lead;
  // Al elegirlo se abre la nota mejor ubicada del hecho (timelineData.mapLead).
  const target = mapLead(item);
  const located = hasMapPoint(target);
  const others = item.articleIds.length - 1;
  // Igual que la ficha: solo si se aleja de la publicación, y sin decir que
  // «ocurrió» ese día (la IA suele dar la fecha de los antecedentes).
  const background = eventDateNote(article.event_date, article.published_at);
  const place = target.primary_location?.place;
  return (
    // Dentro de un tema no hay columna de hora ni nodo (no cabrían dos
    // sangrías en el panel): el día y la hora van en el renglón de datos.
    <li className={showDay ? 'relative pl-1' : 'relative pl-[3.6rem]'}>
      {!showDay && (
        <>
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
                  ? 'size-2.5'
                  : 'size-2'
            }`}
            // Del color de su categoría (el delito), como en la lista y el globo.
            style={
              selected
                ? undefined
                : {
                    backgroundColor: categoryColor(article.category),
                    boxShadow: `0 0 ${others > 0 ? '10px' : '6px'} ${categoryColor(article.category)}`,
                  }
            }
          />
        </>
      )}
      <div
        className={`rounded-xl border transition-colors duration-300 ${
          selected
            ? 'border-sky-300/40 bg-sky-400/[0.1] shadow-[0_0_18px_-6px_rgb(0_210_255/0.6)]'
            : 'border-transparent'
        }`}
      >
        <button
          ref={selected ? selectedRef : undefined}
          type="button"
          aria-expanded={selected}
          onClick={() => {
            onSelect(target.article_id);
          }}
          className={`w-full rounded-xl px-2.5 ${dense ? 'py-1' : 'py-1.5'} text-left transition-all duration-300 focus-visible:outline-2 focus-visible:outline-sky-400 ${
            selected ? '' : 'hover:translate-x-0.5 hover:bg-white/[0.045]'
          }`}
        >
          <span
            title={dense ? `${article.title}${background ? ` · ◆ ${background}` : ''}` : undefined}
            className={`${dense && !selected ? 'block truncate' : 'line-clamp-2'} text-[12.5px] font-medium leading-snug text-slate-50`}
          >
            {article.title}
          </span>
          {/* Los datos como etiquetas: medio, lugar, categoría y cuántos medios. */}
          <span
            className={`${dense ? 'mt-0.5' : 'mt-1'} flex items-center gap-x-2 gap-y-0.5 text-[10.5px] text-slate-400 ${
              dense ? 'flex-nowrap overflow-hidden' : 'flex-wrap'
            }`}
          >
            {showDay && (
              <span className="tabular-nums">
                {shortDay(item.at)} {HOUR.format(new Date(item.at))}
              </span>
            )}
            <span className="max-w-[12rem] truncate text-sky-200/90">
              {article.source_name ?? article.source_domain ?? 'Medio sin nombre'}
            </span>
            {located ? (
              place && <span className="max-w-[11rem] truncate">⌖ {place}</span>
            ) : (
              <span
                className="rounded border border-white/10 px-1 text-slate-500"
                title="La nota no dice dónde pasó: su ficha se abre sin volar el globo"
              >
                sin lugar
              </span>
            )}
            <CategoryTag article={article} />
            {others > 0 && (
              <span className="shrink-0 whitespace-nowrap rounded-full border border-sky-400/30 bg-sky-400/10 px-1.5 text-sky-200">
                +{others} medio{others === 1 ? '' : 's'}
              </span>
            )}
          </span>
          {/* Compacto: la nota de antecedentes va en la ayuda del renglón. */}
          {background && !dense && (
            <span className="mt-0.5 block text-[10.5px] text-amber-200/80">◆ {background}</span>
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
                    <ExternalLink
                      href={note.url}
                      className="text-sky-300 hover:text-sky-100 hover:underline"
                    >
                      {note.source_name ?? note.source_domain ?? 'Medio sin nombre'} ↗
                    </ExternalLink>
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

interface ThemeEntryProps {
  block: ThemeBlock;
  selectedId: number | null;
  selectedRef: Ref<HTMLButtonElement>;
  onSelect: (articleId: number) => void;
}

/**
 * Un tema: los hechos que nombran a la misma persona o caso, en un solo
 * renglón que se despliega (ver `themes.ts`). Se abre solo si la nota elegida
 * está adentro, para que se vea en la lista.
 */
function ThemeEntry({ block, selectedId, selectedRef, onSelect }: ThemeEntryProps) {
  const dense = useContext(DenseRows);
  const containsSelected =
    selectedId !== null && block.items.some((item) => item.articleIds.includes(selectedId));
  const [expanded, setExpanded] = useState(false);
  const open = expanded || containsSelected;
  const oldest = block.items[block.items.length - 1];
  const span =
    oldest && oldest.day !== block.day
      ? `del ${shortDay(oldest.at)} al ${shortDay(block.at)}`
      : shortDay(block.at);
  return (
    <li className="relative pl-[3.6rem]">
      <span className="absolute left-0 top-[0.55rem] w-10 text-right font-display text-[10px] tabular-nums text-amber-200/90">
        {HOUR.format(new Date(block.at))}
      </span>
      {/* Un rombo ámbar en la línea: aquí hay varios hechos juntos. */}
      <span
        aria-hidden="true"
        className="absolute left-[2.95rem] top-[0.65rem] size-2.5 -translate-x-1/2 rotate-45 bg-amber-300 shadow-[0_0_10px_rgb(252_211_77/0.8)]"
      />
      <div className="rounded-lg border border-amber-300/20 bg-amber-300/[0.04]">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => {
            setExpanded(!open);
          }}
          className="w-full rounded-lg px-2 py-1.5 text-left transition-colors duration-300 hover:bg-amber-300/[0.07] focus-visible:outline-2 focus-visible:outline-amber-300"
        >
          <span className="flex items-baseline gap-1.5 text-[12.5px] leading-snug text-slate-100">
            <span className="font-display text-[9px] tracking-wider text-amber-200/90">TEMA</span>
            <span className="font-semibold">{block.label}</span>
            <span className="ml-auto text-[11px] text-slate-400">{open ? '▾' : '▸'}</span>
          </span>
          <span className="mt-0.5 block text-[10.5px] text-slate-400">
            {block.items.length} hechos · {block.notes} notas · {span}
          </span>
          {!open && !dense && (
            <span className="mt-0.5 block truncate text-[10.5px] text-slate-300">
              Lo último: {block.items[0]?.lead.title}
            </span>
          )}
        </button>
        {open && (
          <ol className="space-y-0.5 pb-1 pr-1" aria-label={`Hechos del tema ${block.label}`}>
            {block.items.map((item) => (
              <Entry
                key={item.lead.article_id}
                item={item}
                selected={selectedId !== null && item.articleIds.includes(selectedId)}
                selectedRef={selectedRef}
                onSelect={onSelect}
                showDay
              />
            ))}
          </ol>
        )}
      </div>
    </li>
  );
}

interface ChronologyProps {
  /** Notas que se ven (ya sin las no relevantes si así lo pidió), antes de estos filtros. */
  articles: Article[];
  /**
   * `column`: el panel del diseño de columna, con su título y «☰ Lista».
   * `dossier`: dentro del expediente del Centro de mando, que ya dice
   * «Cronología» en sus pestañas: sin título repetido, sin plegarse y con la
   * curva más baja, para dejarle el alto a las noticias.
   */
  variant?: 'column' | 'dossier';
}

export function Chronology({ articles, variant = 'column' }: ChronologyProps) {
  const dossier = variant === 'dossier';
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
  // Los hechos de la misma persona o caso se juntan en un tema (themes.ts).
  const days = useMemo(() => {
    const groups: { day: string; at: number; rows: ChronologyRow[] }[] = [];
    for (const row of groupThemes(items)) {
      const last = groups[groups.length - 1];
      if (last?.day === row.day) last.rows.push(row);
      else groups.push({ day: row.day, at: row.at, rows: [row] });
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

  if (!open && !dossier) {
    return (
      <button
        type="button"
        aria-expanded={false}
        onClick={() => {
          setOpen(true);
        }}
        className={`${GLASS_OSINT} w-full px-3 py-1.5 text-left text-xs text-slate-100 hover:border-sky-400/40 focus-visible:outline-2 focus-visible:outline-sky-400`}
      >
        <span className={PANEL_TITLE}>Cronología</span>{' '}
        <span className="text-slate-400">· {items.length} hechos ‹</span>
      </button>
    );
  }

  return (
    <section
      aria-label="Cronología"
      // En el expediente ya va dentro de un panel: sin marco propio.
      className={`${dossier ? 'min-h-0 flex-1' : `${GLASS_OSINT} max-h-full`} flex w-full min-w-0 flex-col`}
    >
      <div
        className={`space-y-2 border-b border-sky-400/10 px-4 ${dossier ? 'pb-2.5 pt-2.5' : 'pb-3 pt-3'}`}
      >
        {!dossier && (
          <div className="flex items-center gap-2">
            <h2 className={`${PANEL_TITLE} drop-shadow-[0_0_8px_rgb(0_210_255/0.55)]`}>
              Cronología
            </h2>
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
              className="hud-icon-btn ml-auto size-7 text-sm"
            >
              ›
            </button>
          </div>
        )}
        {timeline.buckets.length > 0 && (
          <div>
            <Spark
              buckets={timeline.buckets}
              unit={timeline.unit}
              max={timeline.max}
              range={range}
              onPick={toggleRange}
              height={dossier ? SPARK_HEIGHT_COMPACT : SPARK_HEIGHT}
              // En el expediente no hay título: el conteo va en medio de la curva.
              caption={
                dossier ? `${String(items.length)} hechos · ${String(notes)} notas` : undefined
              }
            />
          </div>
        )}
        <div className="flex flex-wrap gap-1.5">
          <HudSelect
            label="Filtrar por categoría"
            size="sm"
            className="w-auto max-w-[11rem] rounded-full"
            value={categoryId === null ? '' : String(categoryId)}
            options={[
              { value: '', label: 'Todas las categorías' },
              ...categories.map((c) => ({
                value: String(c.id),
                label: `${c.name} (${String(c.count)})`,
              })),
            ]}
            onChange={(next) => {
              setCategory(next ? Number(next) : null);
            }}
          />
          <HudSelect
            label="Filtrar por estado"
            size="sm"
            className="w-auto max-w-[9rem] rounded-full"
            value={stateCode ?? ''}
            options={[
              { value: '', label: 'Todos los estados' },
              ...states.map((s) => ({ value: s.code, label: `${s.name} (${String(s.count)})` })),
            ]}
            onChange={(next) => {
              setState(next || null);
            }}
          />
          {filtered && (
            <button type="button" onClick={clear} className={`${PILL} text-sky-300`}>
              ✕ Quitar
            </button>
          )}
          {/* En el expediente, la lista va en sus pestañas. */}
          {!dossier && (
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
          )}
        </div>
      </div>

      <DenseRows.Provider value={dossier}>
        <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          {days.length === 0 && (
            <p className="px-1 py-4 text-xs text-slate-400">No hay notas con estos filtros.</p>
          )}
          {days.map((group) => (
            <div key={group.day} className="relative">
              <p className="sticky top-0 z-10 -mx-3 border-b border-sky-400/10 bg-[#050505]/95 px-4 py-1.5 font-display text-[10px] font-bold uppercase tracking-[0.16em] text-sky-200/90">
                {DAY.format(new Date(group.at))}
                <span className="ml-2 font-sans text-[10px] font-normal normal-case tracking-normal text-slate-500">
                  {group.rows.length} {group.rows.length === 1 ? 'entrada' : 'entradas'}
                </span>
              </p>
              {/* La línea vertical luminosa que une los hechos del día. */}
              <span
                aria-hidden="true"
                className="absolute bottom-2 left-[2.95rem] top-9 w-px -translate-x-1/2 bg-gradient-to-b from-sky-400/70 via-sky-400/30 to-sky-400/0"
              />
              <ol
                className="space-y-0.5"
                aria-label={`Hechos del ${DAY.format(new Date(group.at))}`}
              >
                {group.rows.map((row) =>
                  row.kind === 'theme' ? (
                    <ThemeEntry
                      key={`tema-${row.key}`}
                      block={row}
                      selectedId={selectedId}
                      selectedRef={selectedRef}
                      onSelect={selectArticle}
                    />
                  ) : (
                    <Entry
                      key={row.lead.article_id}
                      item={row}
                      selected={selectedId !== null && row.articleIds.includes(selectedId)}
                      selectedRef={selectedRef}
                      onSelect={selectArticle}
                    />
                  ),
                )}
              </ol>
            </div>
          ))}
        </div>
      </DenseRows.Provider>
    </section>
  );
}
