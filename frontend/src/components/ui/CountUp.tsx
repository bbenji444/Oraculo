/**
 * Cifra que sube hasta su valor al aparecer y al cambiar (27/10/2026).
 *
 * «175 notas» no aparece de golpe: corre de 0 a 175 en menos de un segundo.
 * Si cambia (llegan notas nuevas), corre desde el valor anterior. Con
 * «reducir animaciones» del sistema, sale directo.
 *
 * No hace: no da formato de moneda (para eso `format`).
 */
import { useEffect, useRef, useState } from 'react';

import { COUNT_UP_MS, countAt, prefersReducedMotion } from '../../ui/motion';

interface CountUpProps {
  value: number;
  /** Cómo se escribe la cifra (por defecto, entero con separador de miles). */
  format?: (value: number) => string;
  className?: string;
}

const INTEGER = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 0 });

export function CountUp({ value, format, className }: CountUpProps) {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? value : 0));
  const fromRef = useRef(shown);

  // Sin animaciones, se muestra el valor tal cual y el efecto no corre.
  const reduced = prefersReducedMotion();

  useEffect(() => {
    if (reduced) {
      fromRef.current = value;
      return;
    }
    const from = fromRef.current;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = (now - start) / COUNT_UP_MS;
      const next = countAt(from, value, t);
      fromRef.current = next;
      setShown(next);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
    };
  }, [value, reduced]);

  const current = reduced ? value : shown;
  const text = format ? format(current) : INTEGER.format(Math.round(current));
  return (
    <span className={className} aria-label={format ? format(value) : INTEGER.format(value)}>
      <span aria-hidden="true">{text}</span>
    </span>
  );
}
