/**
 * Aviso con la llave recién creada: se muestra **una sola vez** (ADR-0042).
 * Lo usan las llaves de sistema y la llave de API de cada persona (ADR-0120).
 *
 * Trae un botón para copiarla y el recordatorio de entregarla por un medio
 * seguro. Al cerrarlo, la llave desaparece de la pantalla y ya no se puede
 * volver a ver (el servidor solo guarda su huella).
 *
 * Con `autoCloseSeconds` se cierra solo al terminar la cuenta (la llave propia,
 * ver `ownKey.ts`).
 *
 * No hace: no la guarda en ningún lado.
 */
import { useEffect, useRef, useState } from 'react';

import { copyText } from '../../ui/copyText';
import { Modal } from '../Deliveries/Modal';
import { HudButton } from '../ui/HudButton';

interface NewKeyNoticeProps {
  fullKey: string;
  owner: string;
  onClose: () => void;
  /** Qué hacer si se pierde; cambia entre las llaves de sistema y la de API. */
  lostHint?: string;
  /** Si viene, el aviso se cierra solo después de estos segundos. */
  autoCloseSeconds?: number;
}

// Una sola llave vigente por persona (ADR-0124): crear otra revoca esta.
const SYSTEM_KEY_LOST_HINT = 'Si se pierde, crea otra: esta dejará de servir.';
const SECOND_MS = 1000;

export function NewKeyNotice({
  fullKey,
  owner,
  onClose,
  lostHint = SYSTEM_KEY_LOST_HINT,
  autoCloseSeconds,
}: NewKeyNoticeProps) {
  const [copied, setCopied] = useState<'si' | 'no' | null>(null);
  const [left, setLeft] = useState(autoCloseSeconds ?? 0);
  // La última `onClose`, para que la cuenta no se reinicie en cada render.
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    if (autoCloseSeconds === undefined) return;
    const started = Date.now();
    const timer = window.setInterval(() => {
      const remaining = autoCloseSeconds - Math.floor((Date.now() - started) / SECOND_MS);
      if (remaining <= 0) {
        window.clearInterval(timer);
        closeRef.current();
      } else {
        setLeft(remaining);
      }
    }, SECOND_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [autoCloseSeconds]);

  return (
    <Modal title={`Llave nueva de ${owner}`} onClose={onClose}>
      <p className="text-sm text-amber-200">
        Cópiala ahora: <strong>no se vuelve a mostrar</strong>. {lostHint}
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
            void copyText(fullKey).then((ok) => {
              setCopied(ok ? 'si' : 'no');
            });
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
      {autoCloseSeconds !== undefined && (
        <p role="timer" className="text-sm font-semibold text-rose-300">
          Este aviso se cierra solo en {left} s.
        </p>
      )}
      <p className="text-xs text-slate-500">
        Entrégala en persona o por un canal seguro. No la mandes por WhatsApp ni correo.
      </p>
    </Modal>
  );
}
