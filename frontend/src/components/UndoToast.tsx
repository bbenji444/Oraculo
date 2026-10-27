/**
 * Aviso «… eliminado · Deshacer» abajo de la pantalla (27/10/2026).
 *
 * Eliminar un caso o una búsqueda es reversible: este aviso deja deshacerlo
 * sin buscar nada. Se va solo después de UNDO_TOAST_MS o al cerrarlo.
 *
 * No hace: no llama a la API (recibe `onUndo`).
 */
import { useEffect } from 'react';

// Tiempo para alcanzar a deshacer sin que el aviso estorbe.
export const UNDO_TOAST_MS = 8000;

interface UndoToastProps {
  message: string;
  onUndo: () => void;
  onClose: () => void;
  /** Mientras se deshace, el botón se apaga. */
  busy?: boolean;
}

export function UndoToast({ message, onUndo, onClose, busy = false }: UndoToastProps) {
  useEffect(() => {
    const timer = window.setTimeout(onClose, UNDO_TOAST_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [onClose]);
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center px-4">
      <div
        role="status"
        className="pointer-events-auto flex animate-[fadeIn_200ms_ease-out] items-center gap-3 rounded-xl border border-slate-700/80 bg-slate-900/95 px-4 py-2.5 text-sm text-slate-100 shadow-lg shadow-black/40 backdrop-blur"
      >
        <span>{message}</span>
        <button
          type="button"
          disabled={busy}
          onClick={onUndo}
          className="rounded-lg bg-sky-500/20 px-3 py-1 text-xs font-semibold text-sky-100 hover:bg-sky-500/30 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50"
        >
          Deshacer
        </button>
        <button
          type="button"
          aria-label="Cerrar aviso"
          onClick={onClose}
          className="text-slate-400 hover:text-slate-100"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
