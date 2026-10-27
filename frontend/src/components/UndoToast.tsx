/**
 * Aviso «… eliminado · Deshacer» abajo de la pantalla (27/10/2026).
 *
 * Eliminar un caso o una búsqueda es reversible: este aviso deja deshacerlo
 * sin buscar nada. Se va solo después de UNDO_TOAST_MS o al cerrarlo.
 *
 * No hace: no llama a la API (recibe `onUndo`).
 */
import { useEffect } from 'react';

import { HudButton } from './ui/HudButton';

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
        className="hud-panel hud-reveal pointer-events-auto relative flex items-center gap-3 overflow-hidden px-4 py-3 text-sm text-slate-100"
      >
        <span aria-hidden="true" className="hud-dot hud-dot--live" />
        <span>{message}</span>
        <HudButton size="sm" disabled={busy} onClick={onUndo}>
          Deshacer
        </HudButton>
        <button
          type="button"
          aria-label="Cerrar aviso"
          onClick={onClose}
          className="hud-icon-btn size-8"
        >
          ✕
        </button>
        {/* Cuánto tiempo queda para deshacer: la barra se vacía en UNDO_TOAST_MS. */}
        <span
          aria-hidden="true"
          className="hud-countdown absolute inset-x-0 bottom-0 h-[2px]"
          style={{ animationDuration: `${String(UNDO_TOAST_MS)}ms` }}
        />
      </div>
    </div>
  );
}
