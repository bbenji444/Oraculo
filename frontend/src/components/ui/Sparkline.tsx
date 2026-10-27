/**
 * Mini gráfica de línea para las cifras (27/10/2026): se dibuja de izquierda
 * a derecha al aparecer y su último punto late.
 *
 * No hace: no tiene ejes ni etiquetas (es un adorno con datos reales: notas
 * por hora, costo por día).
 */
import { useId } from 'react';

import { sparklinePoints } from '../../ui/sparkline';

interface SparklineProps {
  values: readonly number[];
  width?: number;
  height?: number;
  className?: string;
}

export function Sparkline({ values, width = 120, height = 32, className }: SparklineProps) {
  const id = useId();
  const points = sparklinePoints(values, width, height);
  const last = points[points.length - 1];
  if (!last) return null;
  const line = points.map(([x, y]) => `${String(x)},${String(y)}`).join(' ');
  const area = `0,${String(height)} ${line} ${String(width)},${String(height)}`;
  return (
    <svg
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      width={width}
      height={height}
      aria-hidden="true"
      className={`hud-sparkline ${className ?? ''}`}
    >
      <defs>
        <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#00d2ff" stopOpacity="0.35" />
          <stop offset="1" stopColor="#00d2ff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#${id}-fill)`} className="hud-sparkline-area" />
      <polyline
        points={line}
        fill="none"
        stroke="#00d2ff"
        strokeWidth="1.5"
        strokeLinejoin="round"
        pathLength={1}
        className="hud-sparkline-line"
      />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill="#e6fbff" className="hud-sparkline-dot" />
    </svg>
  );
}
