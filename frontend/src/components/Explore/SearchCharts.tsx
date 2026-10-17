/**
 * Gráficas de la búsqueda (imágenes de referencia de Benji): "Top 5 estados con
 * más noticias" (del mapa de calor de la API) y "Tipos de noticias" (por
 * concepto, con su color). SVG propio; las barras crecen al aparecer.
 */
import { useState } from 'react';

import type { AggregateItem } from '../../services/searches';
import { barHeights, donutSegments } from './charts';
import type { ConceptSlice } from './format';
import { GLASS, PANEL_TITLE } from './ui';

// Cuántos estados se muestran.
const TOP_STATES = 5;
// Alto útil de las barras, en unidades del SVG.
const BAR_AREA = 80;
const BAR_WIDTH = 30;
const BAR_GAP = 14;

interface PanelProps {
  title: string;
  children: React.ReactNode;
}

function Panel({ title, children }: PanelProps) {
  const [open, setOpen] = useState(true);
  return (
    <section className={`${GLASS} p-4`} aria-label={title}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => {
          setOpen((v) => !v);
        }}
        className={`${PANEL_TITLE} flex w-full items-center justify-between text-left focus-visible:outline-2 focus-visible:outline-sky-400`}
      >
        {title}
        <span aria-hidden="true" className="text-slate-500">
          {open ? '−' : '+'}
        </span>
      </button>
      {open && <div className="mt-3">{children}</div>}
    </section>
  );
}

export function TopStatesChart({ items }: { items: readonly AggregateItem[] }) {
  const top = items.slice(0, TOP_STATES);
  const heights = barHeights(
    top.map((i) => i.count),
    BAR_AREA,
  );
  const width = top.length * (BAR_WIDTH + BAR_GAP);
  return (
    <Panel title="Top 5 estados con más noticias">
      {top.length === 0 ? (
        <p className="text-xs text-slate-500">Sin notas ubicadas en estados.</p>
      ) : (
        <svg
          viewBox={`0 0 ${String(width)} ${String(BAR_AREA + 34)}`}
          className="w-full"
          role="img"
          aria-label={top.map((i) => `${i.name}: ${String(i.count)}`).join(', ')}
        >
          <defs>
            <linearGradient id="barra" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#67E8F9" />
              <stop offset="100%" stopColor="#0E7490" />
            </linearGradient>
          </defs>
          {top.map((item, index) => {
            const x = index * (BAR_WIDTH + BAR_GAP) + BAR_GAP / 2;
            const h = heights[index] ?? 0;
            return (
              <g key={item.code}>
                <text
                  x={x + BAR_WIDTH / 2}
                  y={BAR_AREA - h + 8}
                  textAnchor="middle"
                  className="fill-slate-200 text-[9px] tabular-nums"
                >
                  {item.count}
                </text>
                <rect
                  x={x}
                  y={BAR_AREA - h + 12}
                  width={BAR_WIDTH}
                  height={h}
                  rx={4}
                  fill="url(#barra)"
                  className="origin-bottom animate-[grow_700ms_ease-out] [transform-box:fill-box]"
                />
                <text
                  x={x + BAR_WIDTH / 2}
                  y={BAR_AREA + 26}
                  textAnchor="middle"
                  className="fill-slate-400 text-[8px]"
                >
                  {item.name.length > 9 ? `${item.name.slice(0, 8)}…` : item.name}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </Panel>
  );
}

export function ConceptDonut({ slices }: { slices: readonly ConceptSlice[] }) {
  const segments = donutSegments(slices.map((s) => s.count));
  return (
    <Panel title="Tipos de noticias">
      {slices.length === 0 ? (
        <p className="text-xs text-slate-500">Sin notas todavía.</p>
      ) : (
        <div className="flex items-center gap-4">
          <svg
            viewBox="0 0 96 96"
            className="size-24 shrink-0"
            role="img"
            aria-label="Notas por concepto"
          >
            {segments.map((segment, index) => (
              <path
                key={slices[index]?.name ?? index}
                d={segment.path}
                fill={slices[index]?.color}
                className="transition-opacity hover:opacity-80"
              />
            ))}
          </svg>
          <ul className="min-w-0 space-y-1 text-xs">
            {slices.map((slice) => (
              <li key={slice.name} className="flex items-center gap-2 text-slate-300">
                <span
                  aria-hidden="true"
                  className="size-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: slice.color }}
                />
                <span className="truncate">{slice.name}</span>
                <span className="ml-auto tabular-nums text-slate-500">{slice.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}
