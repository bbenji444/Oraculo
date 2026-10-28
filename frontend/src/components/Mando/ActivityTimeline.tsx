/**
 * Línea del tiempo del expediente (Benji, 28/10/2026: la curva anterior «no
 * se entiende»; «qué onda con la línea del tiempo pro»).
 *
 * Una barra por hora (o por día, si la consulta cubre más de 3 días), pintada
 * en capas con el color de cada categoría, así se ve de un vistazo a qué
 * hora salió qué tipo de noticia. Abajo, las horas. Al pasar el mouse (o con
 * el teclado) un aviso dice el tramo, cuántas notas y de qué categorías; un
 * clic filtra ese tramo en la cronología, la lista y el globo, y otro clic lo
 * quita.
 *
 * No hace: no calcula los tramos (`buildTimeline`) ni filtra (`applyTimeline`).
 */
import { type CSSProperties, useMemo, useState } from 'react';

import type { Article } from '../../services/searches';
import { useTimelineStore } from '../../store/timeline';
import { categoryColor } from '../Explore/categoryColor';
import { applyTimeline, bucketSlices, buildTimeline } from '../Explore/timelineData';

const MEXICO_CITY = 'America/Mexico_City';
const HOUR = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});
const DAY = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  day: 'numeric',
  month: 'short',
});
// Etiquetas de hora a lo más: con más se encimarían en el ancho del panel.
const MAX_TICKS = 7;
// Categorías que dice el aviso de un tramo (las demás van en «y N más»).
const TOOLTIP_SLICES = 3;
// Retraso entre barras al aparecer, en milisegundos: crecen una tras otra.
const BAR_STAGGER_MS = 35;

function day(ms: number): string {
  return DAY.format(new Date(ms)).replace('.', '');
}

interface ActivityTimelineProps {
  /** Las notas de la consulta (sin el filtro de tramo, que es esta línea). */
  articles: readonly Article[];
}

export function ActivityTimeline({ articles }: ActivityTimelineProps) {
  const range = useTimelineStore((s) => s.range);
  const categoryIds = useTimelineStore((s) => s.categoryIds);
  const stateCode = useTimelineStore((s) => s.stateCode);
  const toggleRange = useTimelineStore((s) => s.toggleRange);
  const [hover, setHover] = useState<number | null>(null);

  // La línea respeta las categorías y el estado elegidos, no su propio tramo.
  const notes = useMemo(
    () => applyTimeline(articles, { range: null, categoryIds, stateCode }),
    [articles, categoryIds, stateCode],
  );
  const timeline = useMemo(() => buildTimeline(notes), [notes]);
  const byId = useMemo(() => new Map(notes.map((a) => [a.article_id, a] as const)), [notes]);
  const { buckets, max, unit } = timeline;
  if (buckets.length === 0) return null;

  const label = (start: number) => (unit === 'hour' ? HOUR.format(new Date(start)) : day(start));
  const span = (start: number, end: number) =>
    unit === 'hour'
      ? `${day(start)} · ${HOUR.format(new Date(start))} – ${HOUR.format(new Date(end))}`
      : day(start);
  const step = Math.max(1, Math.ceil(buckets.length / MAX_TICKS));
  const peak = buckets.reduce((best, b) =>
    b.articleIds.length > best.articleIds.length ? b : best,
  );
  const shown = hover === null ? null : buckets[hover];
  const slices = shown ? bucketSlices(shown, byId) : [];

  return (
    <div className="mando-activity">
      <div className="mb-1 flex items-baseline justify-between text-[10px] text-slate-400">
        <span className="font-display tracking-[0.18em] text-sky-300/90 uppercase">
          Notas por {unit === 'hour' ? 'hora' : 'día'}
        </span>
        <span>
          Pico: <span className="text-slate-200">{label(peak.start)}</span> ·{' '}
          {peak.articleIds.length} notas
        </span>
      </div>
      <div className="relative">
        <div className="flex h-12 items-end gap-[3px]" role="group" aria-label="Notas por tramo">
          {buckets.map((bucket, i) => {
            const total = bucket.articleIds.length;
            const picked = range !== null && range[0] === bucket.start;
            const dim = range !== null && !picked;
            return (
              <button
                key={bucket.start}
                type="button"
                disabled={total === 0}
                aria-pressed={picked}
                aria-label={`${span(bucket.start, bucket.end)}: ${String(total)} notas`}
                onClick={() => {
                  toggleRange([bucket.start, bucket.end]);
                }}
                onMouseEnter={() => {
                  setHover(i);
                }}
                onMouseLeave={() => {
                  setHover(null);
                }}
                onFocus={() => {
                  setHover(i);
                }}
                onBlur={() => {
                  setHover(null);
                }}
                data-dim={dim ? '' : undefined}
                data-picked={picked ? '' : undefined}
                className="mando-activity-bar"
                style={
                  {
                    '--h': `${String(max ? Math.max(total ? 6 : 0, (total / max) * 100) : 0)}%`,
                    animationDelay: `${String(i * BAR_STAGGER_MS)}ms`,
                  } as CSSProperties
                }
              >
                {/* Capas de color de abajo hacia arriba: una por categoría. */}
                <span className="mando-activity-stack">
                  {bucketSlices(bucket, byId).map((slice) => (
                    <span
                      key={slice.id ?? 'sin'}
                      style={{
                        flexGrow: slice.count,
                        backgroundColor: categoryColor(slice),
                      }}
                    />
                  ))}
                </span>
              </button>
            );
          })}
        </div>
        {shown && (
          <div
            role="tooltip"
            className="mando-activity-tip"
            style={{ left: `${String(((hover ?? 0) + 0.5) * (100 / buckets.length))}%` }}
          >
            <p className="text-[11px] font-semibold text-slate-50">
              {span(shown.start, shown.end)}
            </p>
            <p className="text-[10.5px] text-slate-300">
              {shown.articleIds.length} notas
              {range !== null && range[0] === shown.start
                ? ' · clic para quitar'
                : ' · clic para filtrar'}
            </p>
            {slices.length > 0 && (
              <ul className="mt-1 space-y-0.5">
                {slices.slice(0, TOOLTIP_SLICES).map((slice) => (
                  <li
                    key={slice.id ?? 'sin'}
                    className="flex items-center gap-1.5 text-[10.5px] text-slate-200"
                  >
                    <span
                      aria-hidden="true"
                      className="size-1.5 shrink-0 rounded-full"
                      style={{ backgroundColor: categoryColor(slice) }}
                    />
                    <span className="truncate">{slice.name}</span>
                    <span className="ml-auto text-slate-400">{slice.count}</span>
                  </li>
                ))}
                {slices.length > TOOLTIP_SLICES && (
                  <li className="text-[10px] text-slate-500">
                    y {slices.length - TOOLTIP_SLICES} más
                  </li>
                )}
              </ul>
            )}
          </div>
        )}
      </div>
      <div className="relative mt-1 h-3 text-[9.5px] text-slate-500 tabular-nums">
        {buckets.map((bucket, i) =>
          i % step === 0 ? (
            <span
              key={bucket.start}
              className="absolute -translate-x-1/2"
              style={{ left: `${String((i + 0.5) * (100 / buckets.length))}%` }}
            >
              {label(bucket.start)}
            </span>
          ) : null,
        )}
      </div>
    </div>
  );
}
