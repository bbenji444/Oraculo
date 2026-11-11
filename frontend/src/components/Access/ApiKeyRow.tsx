/**
 * La llave de API de una persona en «Accesos» (ADR-0047): para conectarla con
 * el resto de Oráculo.
 *
 * Benji, 11/11/2026: «cada usuario debe tener su propia API key… que tú puedas
 * copiar». Se ve enmascarada (orc_live_a1b2c3d4…) y tiene tres botones:
 * - «Ver»: la muestra completa ahí mismo (y otra vez la oculta);
 * - «Copiar»: la copia al portapapeles;
 * - «Generar nueva»: crea otra; la anterior deja de servir al instante, así
 *   que pide confirmar.
 *
 * Cada vez que se trae la llave completa queda en la bitácora del servidor.
 * La llave nunca se guarda en la caché ni en el navegador: solo vive en el
 * estado de este renglón mientras está a la vista.
 *
 * No hace: no decide quién puede verla (eso es del servidor: solo superusuarios).
 */
import { useState } from 'react';

import { useNewApiKey, useShowApiKey } from '../../hooks/useAccess';
import type { AccessUser } from '../../services/access';
import { copyText } from '../../ui/copyText';
import { HudButton } from '../ui/HudButton';

// Cuánto se queda el aviso «Copiada».
const COPIED_MS = 2000;

export function ApiKeyRow({ user }: { user: AccessUser }) {
  const show = useShowApiKey();
  const create = useNewApiKey();
  const [visible, setVisible] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const error = show.error ?? create.error;

  const copy = async () => {
    const key = visible ?? (await show.mutateAsync(user.id)).key;
    if (await copyText(key)) {
      setCopied(true);
      window.setTimeout(() => {
        setCopied(false);
      }, COPIED_MS);
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-sky-400/15 bg-sky-400/[0.03] px-3 py-2">
      <span className="font-display text-[10px] tracking-[0.18em] text-sky-300 uppercase">
        Llave de API
      </span>
      <code className="min-w-0 flex-1 break-all font-mono text-xs text-slate-200">
        {visible ?? user.api_key ?? 'Sin llave todavía'}
      </code>
      {user.api_key && (
        <>
          <HudButton
            size="sm"
            variant="ghost"
            disabled={show.isPending}
            onClick={() => {
              if (visible) {
                setVisible(null);
                return;
              }
              show.mutate(user.id, {
                onSuccess: (issued) => {
                  setVisible(issued.key);
                },
              });
            }}
          >
            {visible ? 'Ocultar' : 'Ver'}
          </HudButton>
          <HudButton
            size="sm"
            variant="ghost"
            disabled={show.isPending}
            onClick={() => {
              void copy();
            }}
          >
            {copied ? 'Copiada ✓' : 'Copiar'}
          </HudButton>
        </>
      )}
      {confirming ? (
        <span className="flex items-center gap-2 text-xs text-amber-200">
          La llave actual dejará de servir.
          <HudButton
            size="sm"
            variant="danger"
            disabled={create.isPending}
            onClick={() => {
              create.mutate(user.id, {
                onSuccess: (issued) => {
                  setVisible(issued.key);
                  setConfirming(false);
                },
              });
            }}
          >
            Sí, generar
          </HudButton>
          <HudButton
            size="sm"
            variant="ghost"
            onClick={() => {
              setConfirming(false);
            }}
          >
            No
          </HudButton>
        </span>
      ) : (
        <HudButton
          size="sm"
          disabled={create.isPending || !user.is_active}
          onClick={() => {
            if (user.api_key) setConfirming(true);
            else
              create.mutate(user.id, {
                onSuccess: (issued) => {
                  setVisible(issued.key);
                },
              });
          }}
        >
          {user.api_key ? 'Generar nueva' : 'Generar llave'}
        </HudButton>
      )}
      {error && (
        <p role="alert" className="basis-full text-xs text-rose-300">
          {error.message}
        </p>
      )}
    </div>
  );
}
