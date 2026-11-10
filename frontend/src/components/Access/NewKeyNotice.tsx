/**
 * Aviso con la llave recién creada: se muestra **una sola vez** (ADR-0042).
 *
 * Trae un botón para copiarla y el recordatorio de entregarla por un medio
 * seguro. Al cerrarlo, la llave desaparece de la pantalla y ya no se puede
 * volver a ver (el servidor solo guarda su huella).
 *
 * No hace: no la guarda en ningún lado.
 */
import { useState } from 'react';

import { Modal } from '../Deliveries/Modal';
import { HudButton } from '../ui/HudButton';

interface NewKeyNoticeProps {
  fullKey: string;
  owner: string;
  onClose: () => void;
}

export function NewKeyNotice({ fullKey, owner, onClose }: NewKeyNoticeProps) {
  const [copied, setCopied] = useState<'si' | 'no' | null>(null);

  return (
    <Modal title={`Llave nueva de ${owner}`} onClose={onClose}>
      <p className="text-sm text-amber-200">
        Cópiala ahora: <strong>no se vuelve a mostrar</strong>. Si se pierde, crea otra y revoca
        esta.
      </p>
      <code
        className="block rounded-lg border border-sky-400/30 bg-black/40 p-3 font-mono text-sm break-all text-sky-100 select-all"
        aria-label="Llave completa"
      >
        {fullKey}
      </code>
      <div className="flex flex-wrap items-center gap-2">
        <HudButton
          variant="solid"
          size="sm"
          onClick={() => {
            void navigator.clipboard.writeText(fullKey).then(
              () => {
                setCopied('si');
              },
              () => {
                setCopied('no');
              },
            );
          }}
        >
          Copiar llave
        </HudButton>
        <HudButton size="sm" variant="ghost" onClick={onClose}>
          Ya la copié, cerrar
        </HudButton>
        {copied === 'si' && <span className="text-xs text-emerald-300">Copiada.</span>}
        {copied === 'no' && (
          <span className="text-xs text-rose-300">
            No se pudo copiar: selecciónala y usa Ctrl+C.
          </span>
        )}
      </div>
      <p className="text-xs text-slate-500">
        Entrégala en persona o por un canal seguro. No la mandes por WhatsApp ni correo.
      </p>
    </Modal>
  );
}
