/**
 * Panel de la consola táctica (27/10/2026, styles/hud.css).
 *
 * La caja de todo el monitor: vidrio oscuro, esquinas de mira y, con `spot`,
 * un halo y un borde de luz que siguen al mouse. Con `interactive` se eleva al
 * pasar encima (para tarjetas que se pueden abrir). Con `scan`, una línea de
 * barrido lo cruza una vez al aparecer.
 *
 * No hace: no decide su contenido ni su tamaño.
 */
import type { HTMLAttributes, ReactNode } from 'react';

interface HudPanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  /** Halo y borde de luz que siguen al mouse. */
  spot?: boolean;
  /** Se eleva y enciende al pasar el mouse (tarjeta que se abre). */
  interactive?: boolean;
  /** Línea de barrido al aparecer. */
  scan?: boolean;
}

export function HudPanel({
  children,
  spot = true,
  interactive = false,
  scan = false,
  className = '',
  ...rest
}: HudPanelProps) {
  const classes = [
    'hud-panel',
    spot ? 'hud-spot' : '',
    interactive ? 'hud-panel--interactive' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <div className={classes} {...rest}>
      {spot && <span aria-hidden="true" className="hud-spot-ring" />}
      {scan && <span aria-hidden="true" className="hud-scan" />}
      {children}
    </div>
  );
}
