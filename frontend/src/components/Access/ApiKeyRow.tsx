/**
 * La llave de API de una persona en «Accesos» (ADR-0047): para conectarla con
 * el resto de Oráculo (el gateway la manda en cada petición, ADR-0119).
 *
 * Se ve enmascarada (orc_live_a1b2c3d4…). La completa aparece **una sola vez**,
 * en el aviso que sale al generarla (ADR-0120). Benji, 20/11/2026: «ver una sola
 * vez la api key y después no se pueda ver de nuevo bajo ningún motivo, solo
 * generar una nueva». El servidor solo guarda su huella, así que no hay botón
 * para volver a verla: si se pierde, «Generar nueva», que deja sin servir la
 * anterior al instante y por eso pide confirmar.
 *
 * La llave nunca se guarda en la caché ni en el navegador: solo vive en el
 * estado de este renglón mientras el aviso está abierto.
 *
 * No hace: no decide quién puede generarla (eso es del servidor: solo superusuarios).
 */
import { useState } from 'react';

import { useNewApiKey } from '../../hooks/useAccess';
import type { AccessUser } from '../../services/access';
import { HudButton } from '../ui/HudButton';
import { NewKeyNotice } from './NewKeyNotice';

// La llave de API es una por persona: generar otra ya revoca la anterior.
const API_KEY_LOST_HINT = 'Si se pierde, genera una nueva: esta dejará de servir.';

export function ApiKeyRow({ user }: { user: AccessUser }) {
  const create = useNewApiKey();
  const [fresh, setFresh] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const generate = () => {
    create.mutate(user.id, {
      onSuccess: (issued) => {
        setFresh(issued.key);
        setConfirming(false);
      },
    });
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-sky-400/15 bg-sky-400/[0.03] px-3 py-2">
      <span className="font-display text-[10px] tracking-[0.18em] text-sky-300 uppercase">
        Llave de API
      </span>
      <code className="min-w-0 flex-1 break-all font-mono text-xs text-slate-200">
        {user.api_key ?? 'Sin llave todavía'}
      </code>
      {confirming ? (
        <span className="flex items-center gap-2 text-xs text-amber-200">
          La llave actual dejará de servir.
          <HudButton size="sm" variant="danger" disabled={create.isPending} onClick={generate}>
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
            else generate();
          }}
        >
          {user.api_key ? 'Generar nueva' : 'Generar llave'}
        </HudButton>
      )}
      {create.error && (
        <p role="alert" className="basis-full text-xs text-rose-300">
          {create.error.message}
        </p>
      )}
      {fresh && (
        <NewKeyNotice
          fullKey={fresh}
          owner={user.display_name}
          lostHint={API_KEY_LOST_HINT}
          onClose={() => {
            setFresh(null);
          }}
        />
      )}
    </div>
  );
}
