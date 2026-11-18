/**
 * Panel de la consola táctica (27/10/2026, styles/hud.css).
 *
 * La caja de todo el monitor, con la forma de la tarjeta de Oráculo core
 * (ADR-0108): superficie de consola, esquinas casi rectas y dos corchetes. Con
 * `interactive` su borde se enciende al pasar encima (para tarjetas que se
 * pueden abrir). Con `scan`, una línea de barrido lo cruza una vez al aparecer.
 *
 * No hace: no decide su contenido ni su tamaño.
 */
import type { HTMLAttributes, ReactNode } from 'react';

interface HudPanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  /** El borde se enciende al pasar el mouse (tarjeta que se abre). */
  interactive?: boolean;
  /** Línea de barrido al aparecer. */
  scan?: boolean;
}

export function HudPanel({
  children,
  interactive = false,
  scan = false,
  className = '',
  ...rest
}: HudPanelProps) {
  const classes = ['hud-panel', interactive ? 'hud-panel--interactive' : '', className]
    .filter(Boolean)
    .join(' ');
  return (
    <div className={classes} {...rest}>
      {scan && <span aria-hidden="true" className="hud-scan" />}
      {children}
    </div>
  );
}
