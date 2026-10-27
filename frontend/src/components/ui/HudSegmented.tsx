/**
 * Control segmentado («Hoy · 7 días · 30 días»), 27/10/2026.
 *
 * Una pastilla de luz se desliza a la opción elegida (styles/hud.css, la mueve
 * CSS con --seg-i). Cada opción es un botón con `aria-pressed`.
 *
 * No hace: no guarda la opción (la recibe y avisa con `onChange`).
 */
import type { CSSProperties } from 'react';

interface Option<T extends string> {
  value: T;
  label: string;
}

interface HudSegmentedProps<T extends string> {
  options: readonly Option<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Qué se elige, para el lector de pantalla. */
  label: string;
}

export function HudSegmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: HudSegmentedProps<T>) {
  const index = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );
  const style = { '--seg-i': index, '--seg-n': options.length } as CSSProperties;
  return (
    <div role="group" aria-label={label} className="hud-seg" style={style}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          onClick={() => {
            onChange(option.value);
          }}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
