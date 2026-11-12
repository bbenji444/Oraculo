/**
 * Barra de acciones en bloque de un caso (F12, ADR-0107).
 *
 * Aparece en cuanto hay algo elegido: dice cuánto («5 entidades (3 personas
 * y 2 lugares)») y ofrece «Confirmar», «Descartar» y «Quitar selección».
 *
 * Descartar pide confirmación en el mismo lugar, como `ConfirmDelete`: el
 * primer clic solo pregunta. Confirmar no pregunta porque nada se pierde y
 * cada elemento queda firmado en la bitácora; las personas quedan con el
 * estatus legal que se ve en su renglón (D1).
 *
 * No hace: no llama a la API (avisa con `onConfirm` y `onDiscard`).
 */
import { useState } from 'react';

import { HudButton } from '../ui/HudButton';

interface BulkBarProps {
  /** Cuánto se eligió: «5 entidades», «1 vínculo». */
  count: string;
  /** Detalle por tipo: «3 personas y 2 lugares». */
  detail?: string;
  /** Aviso junto a «Confirmar» (p. ej. qué estatus legal quedará). */
  confirmHint?: string;
  /** Dónde quedan al descartar: «Descartadas» (entidades) o «Descartados» (vínculos). */
  discardedTab?: string;
  canConfirm: boolean;
  canDiscard: boolean;
  busy: boolean;
  onConfirm: () => void;
  onDiscard: () => void;
  onClear: () => void;
}

export function BulkBar({
  count,
  detail,
  confirmHint,
  discardedTab = 'Descartadas',
  canConfirm,
  canDiscard,
  busy,
  onConfirm,
  onDiscard,
  onClear,
}: BulkBarProps) {
  const [asking, setAsking] = useState(false);

  return (
    <div
      role="region"
      aria-label="Acciones en bloque"
      className="hud-reveal flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-sky-400/20 bg-sky-400/[0.06] px-5 py-2.5 text-xs"
    >
      <p className="text-slate-100">
        Selección: <span className="font-medium">{count}</span>
        {detail && <span className="text-slate-400"> ({detail})</span>}
      </p>
      {asking ? (
        <span
          role="group"
          aria-label={`Confirmar: descartar ${count}`}
          className="flex flex-wrap items-center gap-2"
        >
          <span className="text-rose-200">
            ¿Descartar {count}? Quedan en «{discardedTab}» y se pueden volver a confirmar.
          </span>
          <HudButton
            variant="danger"
            size="sm"
            disabled={busy}
            onClick={() => {
              setAsking(false);
              onDiscard();
            }}
          >
            Sí, descartar
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
      ) : (
        <span className="flex flex-wrap items-center gap-2">
          {canConfirm && (
            <button
              type="button"
              disabled={busy}
              onClick={onConfirm}
              className="hud-btn hud-btn--sm border-emerald-400/50 text-emerald-100"
            >
              Confirmar {count}
            </button>
          )}
          {canDiscard && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setAsking(true);
              }}
              className="hud-btn hud-btn--sm hud-btn--danger"
            >
              Descartar {count}
            </button>
          )}
          <HudButton variant="ghost" size="sm" disabled={busy} onClick={onClear}>
            Quitar selección
          </HudButton>
        </span>
      )}
      {confirmHint && canConfirm && !asking && (
        <p className="w-full text-slate-400">{confirmHint}</p>
      )}
    </div>
  );
}
