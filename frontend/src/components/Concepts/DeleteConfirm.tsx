/**
 * Confirmación para borrar un concepto o una subdivisión.
 *
 * Recuerda la alternativa más segura: desactivar lo oculta del panel de
 * búsqueda sin borrarlo. Quien la usa puede dar su propio mensaje.
 */
import { HudButton } from '../ui/HudButton';

interface DeleteConfirmProps {
  name: string;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
  /** Texto propio; sin él, el de los conceptos. */
  message?: string;
}

export function DeleteConfirm({
  name,
  pending,
  error,
  onConfirm,
  onCancel,
  message,
}: DeleteConfirmProps) {
  return (
    <div
      role="alertdialog"
      aria-label={`Borrar «${name}»`}
      className="hud-reveal rounded-xl border border-rose-500/40 bg-rose-500/[0.07] p-4 shadow-[0_0_24px_rgb(255_77_109/0.12)]"
    >
      <p className="text-sm text-rose-100">
        {message ??
          `¿Borrar «${name}»? Si solo quieres que deje de aparecer en las búsquedas, desmarca «Activo» y guarda.`}
      </p>
      {error && <p className="mt-2 text-sm text-rose-200">{error}</p>}
      <div className="mt-3 flex gap-2">
        <HudButton variant="danger" size="sm" disabled={pending} onClick={onConfirm}>
          {pending ? 'Borrando…' : 'Sí, borrar'}
        </HudButton>
        <HudButton variant="ghost" size="sm" onClick={onCancel}>
          No
        </HudButton>
      </div>
    </div>
  );
}
