/**
 * Encabezado de pantalla (27/10/2026): un rótulo chico con una línea que se
 * dibuja, el título que se descifra y, debajo, la explicación en una línea.
 *
 * No hace: no pone acciones (se pasan como `actions` y van a la derecha).
 */
import type { ReactNode } from 'react';

import { DecodeText } from './DecodeText';

interface SectionHeadingProps {
  kicker: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}

export function SectionHeading({ kicker, title, description, actions }: SectionHeadingProps) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <p className="hud-kicker">{kicker}</p>
        <h2 className="hud-title mt-3">
          <DecodeText text={title} />
        </h2>
        {description && (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-400">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
