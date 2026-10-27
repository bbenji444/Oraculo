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

interface ConfirmDeleteProps {
  /** Qué se elimina, para el lector de pantalla («la búsqueda», «el caso»). */
  what: string;
  onConfirm: () => void;
  /** Mientras se elimina, los botones se apagan. */
  busy?: boolean;
  /** Texto del botón inicial. */
  label?: string;
}

const BASE =
  'rounded-lg px-3 py-1.5 text-xs font-medium focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50';

export function ConfirmDelete({
  what,
  onConfirm,
  busy = false,
  label = 'Eliminar',
}: ConfirmDeleteProps) {
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <button
        type="button"
        aria-label={`${label} ${what}`}
        onClick={() => {
          setAsking(true);
        }}
        className={`${BASE} border border-rose-400/25 text-rose-200 hover:bg-rose-500/15`}
      >
        {label}
      </button>
    );
  }
  return (
    <span
      role="group"
      aria-label={`Confirmar: eliminar ${what}`}
      className="flex items-center gap-1.5"
    >
      <span className="text-xs text-rose-200">¿Eliminar?</span>
      <button
        type="button"
        disabled={busy}
        onClick={onConfirm}
        className={`${BASE} bg-rose-500/80 text-white hover:bg-rose-500`}
      >
        Sí, eliminar
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          setAsking(false);
        }}
        className={`${BASE} border border-slate-600 text-slate-200 hover:bg-slate-800`}
      >
        Cancelar
      </button>
    </span>
  );
}
