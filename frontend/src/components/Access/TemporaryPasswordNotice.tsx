/**
 * Aviso con la contraseña temporal de una persona: se muestra **una sola vez**.
 *
 * Sale al darla de alta o al restablecer su contraseña. La persona entra con
 * ella, la cambia por una propia y da de alta su Microsoft Authenticator
 * (ADR-0043). Al cerrar el aviso ya no se puede volver a ver: el servidor
 * solo guarda su huella.
 *
 * No hace: no la guarda en ningún lado.
 */
import { useState } from 'react';

import { Modal } from '../Deliveries/Modal';
import { HudButton } from '../ui/HudButton';

interface TemporaryPasswordNoticeProps {
  password: string;
  owner: string;
  username: string;
  onClose: () => void;
}

export function TemporaryPasswordNotice({
  password,
  owner,
  username,
  onClose,
}: TemporaryPasswordNoticeProps) {
  const [copied, setCopied] = useState<'si' | 'no' | null>(null);

  return (
    <Modal title={`Contraseña temporal de ${owner}`} onClose={onClose}>
      <p className="text-sm text-amber-200">
        Cópiala ahora: <strong>no se vuelve a mostrar</strong>.
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-slate-400">Usuario</dt>
        <dd className="font-mono text-slate-100">{username}</dd>
        <dt className="text-slate-400">Contraseña</dt>
        <dd>
          <code
            className="font-mono text-base break-all text-sky-100 select-all"
            aria-label="Contraseña temporal"
          >
            {password}
          </code>
        </dd>
      </dl>
      <div className="flex flex-wrap items-center gap-2">
        <HudButton
          variant="solid"
          size="sm"
          onClick={() => {
            void navigator.clipboard.writeText(password).then(
              () => {
                setCopied('si');
              },
              () => {
                setCopied('no');
              },
            );
          }}
        >
          Copiar contraseña
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
        Al entrar, el monitor le pedirá cambiarla y conectar Microsoft Authenticator. Entrégala en
        persona o por un canal seguro.
      </p>
    </Modal>
  );
}
