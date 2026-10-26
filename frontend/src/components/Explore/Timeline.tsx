/**
 * Línea del tiempo de Explorar (F12.7, ADR-0032; rediseño del 26/10/2026).
 *
 * Abajo, sobre el globo y casi sin fondo (solo un degradado para leerla):
 *
 * - **Curva de densidad**: cuántas notas se publicaron por hora (o por día),
 *   en hora de la CDMX. Los 3 picos llevan su número brillando. Un clic en un
 *   tramo filtra esa hora; otro clic lo quita.
 * - **Un punto por historia**: el mismo hecho publicado por varios medios es
 *   un solo punto (más grande si lo publicaron más medios), así nada se ve
 *   repetido. Al pasar el mouse sale su ficha; un clic lo elige y el globo
 *   vuela hacia la nota.
 * - **Filtros** por categoría (el delito) y estado, y el botón «Lista» para
 *   volver a mostrar la lista de noticias del panel izquierdo si hace falta.
 *
 * Los filtros viven en `useTimelineStore` y `ExplorePage` los aplica a la lista
 * que usa el globo, así todo queda sincronizado.
 *
 * No hace: no pide datos ni calcula los tramos (eso es `timelineData.ts`).
 */
import { useMemo, useState } from 'react';

import type { Article } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import {
  applyTimeline,
  type Bead,
  buildTimeline,
  categoriesIn,
  layoutBeads,
  MAX_BEADS_PER_BUCKET,
  noteMoment,
  statesIn,
  type TimelineBucket,
  type TimelineUnit,
} from './timelineData';
import { PANEL_TITLE } from './ui';

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
/** Cada cuántos tramos se rotula el eje para que los rótulos no se encimen. */
const LABEL_EVERY_HOURS = 3;
const LABEL_EVERY_DAYS = 1;
/** Alto de la curva, del eje y separación de los puntos apilados (px). */
const CURVE_HEIGHT = 34;
const AXIS_HEIGHT = 16;
const BEAD_GAP = 15;
/** Tamaño de un punto según cuántos medios publicaron la historia (px). */
const BEAD_MIN = 7;
const BEAD_MAX = 15;
const BEAD_PER_OUTLET = 2;
/** Ancho del lienzo de la curva (se estira al ancho real). */
const CANVAS_WIDTH = 1000;
/** La ficha flotante no se sale por los lados (porcentaje del ancho). */
const TOOLTIP_MIN_X = 12;
const TOOLTIP_MAX_X = 88;

const PILL =
  'rounded-full border border-white/10 bg-black/45 px-2.5 py-1 text-[11px] text-slate-200 backdrop-blur-md transition-colors hover:border-sky-400/40 focus-visible:outline-2 focus-visible:outline-sky-400';

function day(ms: number): string {
  return DAY_LABEL.format(new Date(ms)).replace('.', '');
}

function axisLabel(bucket: TimelineBucket, unit: TimelineUnit, index: number): string | null {
  if (unit === 'day') return index % LABEL_EVERY_DAYS === 0 ? day(bucket.start) : null;
  const hour = HOUR_LABEL.format(new Date(bucket.start));
  if (hour === '00:00') return day(bucket.start);
  return index % LABEL_EVERY_HOURS === 0 ? hour.replace(':00', ' h') : null;
}

function bucketLabel(bucket: TimelineBucket, unit: TimelineUnit): string {
  if (unit === 'day') return day(bucket.start);
  return `${day(bucket.start)}, ${HOUR_LABEL.format(new Date(bucket.start))}`;
}

/** La curva de densidad: un trazo suave (Bézier) y su relleno. */
function curvePath(buckets: TimelineBucket[], max: number): { line: string; area: string } {
  const n = buckets.length;
  const points: [number, number][] = buckets.map((b, i) => [
    ((i + 0.5) / n) * CANVAS_WIDTH,
    CURVE_HEIGHT - 2 - (max ? (b.articleIds.length / max) * (CURVE_HEIGHT - 6) : 0),
  ]);
  const first = points[0] ?? [0, CURVE_HEIGHT];
  // Los extremos llegan a los bordes para que la curva no quede flotando.
  const all: [number, number][] = [
    [0, first[1]],
    ...points,
    [CANVAS_WIDTH, points[points.length - 1]?.[1] ?? first[1]],
  ];
  let line = `M 0 ${String(first[1])}`;
  for (let i = 1; i < all.length; i += 1) {
    const [x0, y0] = all[i - 1] ?? first;
    const [x1, y1] = all[i] ?? first;
    const mid = (x0 + x1) / 2;
    line += ` C ${String(mid)} ${String(y0)}, ${String(mid)} ${String(y1)}, ${String(x1)} ${String(y1)}`;
  }
  const area = `${line} L ${String(CANVAS_WIDTH)} ${String(CURVE_HEIGHT)} L 0 ${String(CURVE_HEIGHT)} Z`;
  return { line, area };
}

function beadSize(bead: Bead): number {
  return Math.min(BEAD_MAX, BEAD_MIN + (bead.articleIds.length - 1) * BEAD_PER_OUTLET);
}

interface TooltipProps {
  bead: Bead;
  left: number;
  bottom: number;
}

function Tooltip({ bead, left, bottom }: TooltipProps) {
  const article = bead.lead;
  const event = noteMoment(article);
  const others = bead.articleIds.length - 1;
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-30 w-72 -translate-x-1/2 rounded-xl border border-sky-400/30 bg-black/80 px-3 py-2 shadow-glow backdrop-blur-md"
      style={{ left: `${String(left)}%`, bottom: `${String(bottom)}px` }}
    >
      <p className="font-display text-[10px] tracking-wider text-sky-300">
        {HOUR_LABEL.format(new Date(bead.at))} · {day(bead.at)}
        {others > 0 ? ` · +${String(others)} medio${others === 1 ? '' : 's'}` : ''}
      </p>
      <p className="mt-0.5 line-clamp-3 text-[12px] leading-snug text-slate-50">{article.title}</p>
      <p className="mt-1 text-[10.5px] text-slate-400">
        {article.source_name ?? article.source_domain ?? 'Medio sin nombre'}
        {article.category ? ` · ${article.category.name}` : ''}
        {article.primary_location?.place ? ` · ${article.primary_location.place}` : ''}
      </p>
      {event?.kind === 'event' && (
        <p className="mt-0.5 text-[10.5px] text-amber-200/90">
          ◆ El hecho ocurrió el {day(event.at)}
        </p>
      )}
    </div>
  );
}

interface TimelineProps {
  /** Notas que se ven (ya sin las no relevantes si así lo pidió), antes de estos filtros. */
  articles: Article[];
}

export function Timeline({ articles }: TimelineProps) {
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
  const [hovered, setHovered] = useState<Bead | null>(null);

  // La curva y los puntos respetan categoría y estado; el tramo solo atenúa.
  const visible = useMemo(
    () => applyTimeline(articles, { range: null, categoryId, stateCode }),
    [articles, categoryId, stateCode],
  );
  const timeline = useMemo(() => buildTimeline(visible), [visible]);
  const layout = useMemo(() => layoutBeads(visible, timeline), [visible, timeline]);
  const curve = useMemo(
    () => curvePath(timeline.buckets, timeline.max),
    [timeline.buckets, timeline.max],
  );
  const categories = useMemo(() => categoriesIn(articles), [articles]);
  const states = useMemo(() => statesIn(articles), [articles]);
  const filtered = range !== null || categoryId !== null || stateCode !== null;
  const stories = layout.beads.length + [...layout.overflow.values()].reduce((a, b) => a + b, 0);
  const n = timeline.buckets.length;
  const xOf = (bucket: number) => ((bucket + 0.5) / Math.max(1, n)) * 100;
  const inRange = (at: number) => range === null || (at >= range[0] && at < range[1]);
  const selectedIndex = range ? timeline.buckets.findIndex((b) => b.start === range[0]) : -1;
  const beadsBase = AXIS_HEIGHT + CURVE_HEIGHT + 4;

  return (
    <section aria-label="Línea del tiempo" className="relative">
      {/* Solo un degradado: deja ver el globo y hace legible lo de encima. */}
      <div className="pointer-events-none absolute -inset-x-4 -bottom-4 -top-10 -z-10 bg-gradient-to-t from-black/75 via-black/35 to-transparent" />
      <div className="pointer-events-auto flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <h2 className={`${PANEL_TITLE} drop-shadow-[0_0_8px_rgb(0_210_255/0.6)]`}>
          Línea del tiempo
        </h2>
        <span className="text-[11px] text-slate-300/80">
          {stories} historias · {visible.length} notas · publicadas por{' '}
          {timeline.unit === 'hour' ? 'hora' : 'día'} (CDMX)
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {open && (
            <>
              <select
                aria-label="Filtrar por categoría"
                value={categoryId ?? ''}
                onChange={(event) => {
                  setCategory(event.target.value ? Number(event.target.value) : null);
                }}
                className={`${PILL} max-w-[12rem]`}
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
                className={`${PILL} max-w-[10rem]`}
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
                  ✕ Quitar filtros
                </button>
              )}
            </>
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
          <button
            type="button"
            aria-expanded={open}
            onClick={() => {
              setOpen(!open);
            }}
            className={PILL}
          >
            {open ? '▾ Ocultar' : '▴ Mostrar'}
          </button>
        </div>
      </div>

      {open && n > 0 && (
        <div
          className="pointer-events-auto relative mt-3"
          style={{ height: `${String(beadsBase + BEAD_GAP * MAX_BEADS_PER_BUCKET + 8)}px` }}
          onMouseLeave={() => {
            setHovered(null);
          }}
        >
          {/* Curva de densidad con brillo cian. */}
          <svg
            className="pointer-events-none absolute inset-x-0 overflow-visible"
            style={{ bottom: `${String(AXIS_HEIGHT)}px`, height: `${String(CURVE_HEIGHT)}px` }}
            viewBox={`0 0 ${String(CANVAS_WIDTH)} ${String(CURVE_HEIGHT)}`}
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="timeline-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#00d2ff" stopOpacity="0.45" />
                <stop offset="100%" stopColor="#00d2ff" stopOpacity="0" />
              </linearGradient>
              <filter id="timeline-glow" x="-5%" y="-50%" width="110%" height="200%">
                <feGaussianBlur stdDeviation="2.2" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            {selectedIndex >= 0 && (
              <rect
                x={(selectedIndex / n) * CANVAS_WIDTH}
                width={CANVAS_WIDTH / n}
                y="0"
                height={CURVE_HEIGHT}
                fill="#00d2ff"
                fillOpacity="0.14"
              />
            )}
            <path d={curve.area} fill="url(#timeline-fill)" />
            <path
              d={curve.line}
              fill="none"
              stroke="#7ee9ff"
              strokeWidth="1.6"
              vectorEffect="non-scaling-stroke"
              filter="url(#timeline-glow)"
            />
          </svg>

          {/* Eje: una línea fina con los rótulos de hora. */}
          <div
            className="pointer-events-none absolute inset-x-0 border-t border-sky-300/25"
            style={{ bottom: `${String(AXIS_HEIGHT)}px` }}
          />
          {timeline.buckets.map((bucket, index) => {
            const label = axisLabel(bucket, timeline.unit, index);
            return label ? (
              <span
                key={`l-${String(bucket.start)}`}
                className="pointer-events-none absolute bottom-0 -translate-x-1/2 whitespace-nowrap text-[9.5px] tabular-nums text-slate-400"
                style={{ left: `${String(xOf(index))}%` }}
              >
                {label}
              </span>
            ) : null;
          })}

          {/* Tramos: un clic filtra esa hora (o ese día). */}
          {timeline.buckets.map((bucket, index) => {
            const count = bucket.articleIds.length;
            const selected = range !== null && range[0] === bucket.start;
            return (
              <button
                key={`t-${String(bucket.start)}`}
                type="button"
                disabled={count === 0}
                aria-pressed={selected}
                aria-label={`${bucketLabel(bucket, timeline.unit)}: ${String(count)} notas${bucket.peak ? ' (pico)' : ''}`}
                title={`${bucketLabel(bucket, timeline.unit)} · ${String(count)} notas`}
                onClick={() => {
                  toggleRange([bucket.start, bucket.end]);
                }}
                className="absolute bottom-0 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-default"
                style={{
                  left: `${String((index / n) * 100)}%`,
                  width: `${String(100 / n)}%`,
                  height: `${String(AXIS_HEIGHT + CURVE_HEIGHT)}px`,
                }}
              >
                {bucket.peak && (
                  <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 font-display text-[9px] font-bold text-sky-200 drop-shadow-[0_0_6px_rgb(0_210_255/0.9)]">
                    {count}
                  </span>
                )}
              </button>
            );
          })}

          {/* Un punto por historia, apilados sobre la curva. */}
          {layout.beads.map((bead) => {
            const size = beadSize(bead);
            const selected = selectedId !== null && bead.articleIds.includes(selectedId);
            const dim = !inRange(bead.at);
            const several = bead.articleIds.length > 1;
            return (
              <button
                key={bead.lead.article_id}
                type="button"
                aria-label={`${bead.lead.title}${several ? ` (+${String(bead.articleIds.length - 1)} medios)` : ''}`}
                aria-current={selected}
                onMouseEnter={() => {
                  setHovered(bead);
                }}
                onFocus={() => {
                  setHovered(bead);
                }}
                onBlur={() => {
                  setHovered(null);
                }}
                onClick={() => {
                  selectArticle(bead.lead.article_id);
                }}
                className={`absolute -translate-x-1/2 rounded-full transition-[transform,opacity] duration-200 hover:scale-150 focus-visible:outline-2 focus-visible:outline-sky-300 ${
                  selected
                    ? 'z-20 scale-150 bg-white shadow-[0_0_14px_rgb(255_255_255/0.9)] ring-2 ring-sky-300'
                    : several
                      ? 'bg-sky-300 shadow-[0_0_10px_rgb(0_210_255/0.85)] ring-1 ring-sky-100/60'
                      : 'bg-sky-400/90 shadow-[0_0_7px_rgb(0_210_255/0.7)]'
                } ${dim ? 'opacity-20' : ''}`}
                style={{
                  left: `${String(xOf(bead.bucket))}%`,
                  bottom: `${String(beadsBase + bead.row * BEAD_GAP)}px`,
                  width: `${String(size)}px`,
                  height: `${String(size)}px`,
                }}
              />
            );
          })}
          {[...layout.overflow.entries()].map(([bucket, extra]) => (
            <span
              key={`o-${String(bucket)}`}
              className="pointer-events-none absolute -translate-x-1/2 font-display text-[9px] text-sky-200/80"
              style={{
                left: `${String(xOf(bucket))}%`,
                bottom: `${String(beadsBase + MAX_BEADS_PER_BUCKET * BEAD_GAP)}px`,
              }}
            >
              +{extra}
            </span>
          ))}

          {hovered && (
            <Tooltip
              bead={hovered}
              left={Math.min(TOOLTIP_MAX_X, Math.max(TOOLTIP_MIN_X, xOf(hovered.bucket)))}
              bottom={beadsBase + 20 + hovered.row * BEAD_GAP}
            />
          )}
        </div>
      )}
      {open && n === 0 && (
        <p className="mt-2 text-xs text-slate-400">Estas notas no traen fecha.</p>
      )}
    </section>
  );
}
