/**
 * Las llaves de una persona en «Accesos»: crear una nueva y revocar.
 *
 * De cada llave se ve solo su parte pública (`orc_live_a1b2c3d4…`), para
 * qué es, su estado y su último uso. Revocar pide confirmación y la deja sin
 * servir al instante (cierra las sesiones que entraron con ella).
 *
 * No hace: no muestra la llave completa (eso es de `NewKeyNotice`, una vez).
 */
import { useId, useState } from 'react';

import { useAccessKeys, useIssueKey, useRevokeKey } from '../../hooks/useAccess';
import { type AccessKey, type AccessUser, keyStatus } from '../../services/access';
import { ConfirmDelete } from '../ConfirmDelete';
import { formatMexicoCity } from '../Explore/format';
import { HudButton } from '../ui/HudButton';
import { type ChipTone, HudChip } from '../ui/HudChip';
import { HudSelect } from '../ui/HudSelect';
import { NewKeyNotice } from './NewKeyNotice';

const STATUS_TONE: Record<ReturnType<typeof keyStatus>, ChipTone> = {
  vigente: 'green',
  revocada: 'rose',
  vencida: 'amber',
};

// Vigencias que se ofrecen (la API acepta de 1 a 365 días o sin vencimiento).
const VALIDITY = [
  { value: '30', label: '30 días' },
  { value: '90', label: '90 días (recomendado)' },
  { value: '180', label: '6 meses' },
  { value: '365', label: '1 año' },
  { value: 'never', label: 'Sin vencimiento' },
] as const;
type Validity = (typeof VALIDITY)[number]['value'];

function KeyRow({
  item,
  onRevoke,
  busy,
}: {
  item: AccessKey;
  onRevoke: () => void;
  busy: boolean;
}) {
  const status = keyStatus(item);
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-white/5 py-3 first:border-t-0">
      <div className="min-w-0 flex-1 basis-56">
        <p className="font-mono text-sm text-slate-100">{item.masked}</p>
        <p className="mt-0.5 text-xs text-slate-400">
          {item.label || 'Sin etiqueta'} · creada el {formatMexicoCity(item.created_at)} por{' '}
          {item.created_by}
        </p>
        <p className="mt-0.5 text-[11px] text-slate-500">
          {item.expires_at ? `Vence el ${formatMexicoCity(item.expires_at)}` : 'No vence'} ·{' '}
          {item.last_used_at
            ? `último uso ${formatMexicoCity(item.last_used_at)}${
                item.last_used_ip ? ` desde ${item.last_used_ip}` : ''
              }`
            : 'nunca usada'}
        </p>
      </div>
      <HudChip tone={STATUS_TONE[status]} dot>
        {status}
      </HudChip>
      {status === 'vigente' && (
        <ConfirmDelete
          what={`la llave ${item.masked}`}
          label="Revocar"
          verb="revocar"
          busy={busy}
          onConfirm={onRevoke}
        />
      )}
    </li>
  );
}

export function UserKeys({ user }: { user: AccessUser }) {
  const keys = useAccessKeys(user.id);
  const issue = useIssueKey();
  const revoke = useRevokeKey();
  const [label, setLabel] = useState('');
  const [validity, setValidity] = useState<Validity>('90');
  const [fullKey, setFullKey] = useState<string | null>(null);
  const id = useId();

  return (
    <div className="mt-4 rounded-lg border border-white/5 bg-black/20 p-4">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          issue.mutate(
            {
              userId: user.id,
              label: label.trim(),
              days: validity === 'never' ? null : Number(validity),
            },
            {
              onSuccess: (issued) => {
                setLabel('');
                setFullKey(issued.key);
              },
            },
          );
        }}
      >
        <div className="min-w-0 flex-1 basis-48">
          <label htmlFor={`${id}-label`} className="hud-label">
            Para qué es <span className="font-normal text-slate-500">(opcional)</span>
          </label>
          <input
            id={`${id}-label`}
            value={label}
            maxLength={80}
            placeholder="Laptop de la oficina"
            onChange={(e) => {
              setLabel(e.target.value);
            }}
            className="hud-input"
          />
        </div>
        <HudSelect
          label="Vigencia"
          size="sm"
          value={validity}
          options={VALIDITY}
          onChange={setValidity}
        />
        <HudButton
          type="submit"
          size="sm"
          variant="solid"
          disabled={issue.isPending || !user.is_active}
        >
          {issue.isPending ? 'Creando…' : '+ Nueva llave'}
        </HudButton>
      </form>
      {!user.is_active && (
        <p className="mt-2 text-xs text-slate-500">Activa a la persona para darle una llave.</p>
      )}
      {issue.error && (
        <p role="alert" className="mt-2 text-xs text-rose-300">
          {issue.error.message}
        </p>
      )}
      {revoke.error && (
        <p role="alert" className="mt-2 text-xs text-rose-300">
          {revoke.error.message}
        </p>
      )}
      {keys.isPending && <p className="mt-3 text-xs text-slate-400">Cargando llaves…</p>}
      {keys.error && <p className="mt-3 text-xs text-rose-300">{keys.error.message}</p>}
      {keys.data?.length === 0 && (
        <p className="mt-3 text-xs text-slate-400">Todavía no tiene llaves.</p>
      )}
      {keys.data && keys.data.length > 0 && (
        <ul className="mt-3" aria-label={`Llaves de ${user.display_name}`}>
          {keys.data.map((item) => (
            <KeyRow
              key={item.id}
              item={item}
              busy={revoke.isPending && revoke.variables === item.id}
              onRevoke={() => {
                revoke.mutate(item.id);
              }}
            />
          ))}
        </ul>
      )}
      {fullKey && (
        <NewKeyNotice
          fullKey={fullKey}
          owner={user.display_name}
          onClose={() => {
            setFullKey(null);
          }}
        />
      )}
    </div>
  );
}
