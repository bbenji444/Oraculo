/**
 * Confirmación para borrar un concepto.
 *
 * Recuerda la alternativa más segura: desactivar lo oculta del panel de
 * búsqueda sin borrarlo.
 */
interface DeleteConfirmProps {
  name: string;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteConfirm({ name, pending, error, onConfirm, onCancel }: DeleteConfirmProps) {
  return (
    <div
      role="alertdialog"
      aria-label={`Borrar «${name}»`}
      className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3"
    >
      <p className="text-sm text-rose-100">
        ¿Borrar «{name}»? Si solo quieres que deje de aparecer en las búsquedas, desmarca «Activo» y
        guarda.
      </p>
      {error && <p className="mt-2 text-sm text-rose-200">{error}</p>}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={onConfirm}
          className="rounded-lg bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-500 focus-visible:outline-2 focus-visible:outline-rose-300 disabled:opacity-50"
        >
          {pending ? 'Borrando…' : 'Sí, borrar'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          No
        </button>
      </div>
    </div>
  );
}
