/**
 * Insignia de estado (27/10/2026, styles/hud.css): «abierto», «reservado»,
 * «terminada», una categoría… Con `live` lleva un punto con pulso de radar,
 * para lo que está vivo (una corrida en curso, un servicio funcionando).
 *
 * No hace: no decide el color según el dato (lo elige quien la usa).
 */
import type { ReactNode } from 'react';

export type ChipTone = 'cyan' | 'green' | 'amber' | 'rose' | 'violet' | 'slate';

interface HudChipProps {
  children: ReactNode;
  tone?: ChipTone;
  /** Punto de color al inicio. */
  dot?: boolean;
  /** El punto late (algo que está pasando ahora). */
  live?: boolean;
  className?: string;
}

export function HudChip({
  children,
  tone = 'cyan',
  dot = false,
  live = false,
  className = '',
}: HudChipProps) {
  const toneClass = tone === 'cyan' ? '' : `hud-chip--${tone}`;
  return (
    <span className={`hud-chip ${toneClass} ${className}`}>
      {(dot || live) && (
        <span aria-hidden="true" className={`hud-dot ${live ? 'hud-dot--live' : ''}`} />
      )}
      {children}
    </span>
  );
}
