/**
 * Botón «Eliminar» que pide confirmación en el mismo lugar (27/10/2026).
 *
 * El primer clic no borra nada: cambia el botón por «¿Eliminar? · Sí, eliminar
 * · Cancelar». Así un clic por error no se lleva un caso o una búsqueda. Lo
 * eliminado además se puede deshacer (`UndoToast`).
 *
 * Lo usan el Historial y el detalle de un caso. No hace: no llama a la API
 * (recibe `onConfirm`).
 */
import { useState } from 'react';

import { HudButton } from './ui/HudButton';

interface ConfirmDeleteProps {
  /** Qué se elimina, para el lector de pantalla («la búsqueda», «el caso»). */
  what: string;
  onConfirm: () => void;
  /** Mientras se elimina, los botones se apagan. */
  busy?: boolean;
  /** Texto del botón inicial. */
  label?: string;
}

export function ConfirmDelete({
  what,
  onConfirm,
  busy = false,
  label = 'Eliminar',
}: ConfirmDeleteProps) {
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <HudButton
        variant="danger"
        size="sm"
        aria-label={`${label} ${what}`}
        onClick={() => {
          setAsking(true);
        }}
      >
        {label}
      </HudButton>
    );
  }
  return (
    <span
      role="group"
      aria-label={`Confirmar: eliminar ${what}`}
      className="hud-reveal flex items-center gap-2"
    >
      <span className="font-display text-[10px] tracking-[0.18em] text-rose-200 uppercase">
        ¿Eliminar?
      </span>
      <HudButton variant="danger" size="sm" disabled={busy} onClick={onConfirm}>
        Sí, eliminar
      </HudButton>
      <HudButton
        variant="ghost"
        size="sm"
        disabled={busy}
        onClick={() => {
          setAsking(false);
        }}
      >
        Cancelar
      </HudButton>
    </span>
  );
}
