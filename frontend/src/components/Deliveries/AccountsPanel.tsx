/**
 * Cuentas de envío: desde dónde salen los correos (ADR-0039).
 *
 * «Conectar Outlook / Hotmail» o «Conectar Gmail» crea la cuenta como
 * pendiente y abre el link de autorización de Composio. Al volver, «Ya
 * autoricé» pregunta si quedó lista. WhatsApp aparece, pero «Próximamente».
 *
 * No hace: no manda nada.
 */
import { useId, useState } from 'react';

import {
  useConnectAccount,
  useDeliveryAccounts,
  useRefreshAccount,
} from '../../hooks/useDeliveries';
import type { AccountProvider } from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { ACCOUNT_STATUS, PROVIDER_LABEL } from './labels';

export function AccountsPanel({ emailConfigured }: { emailConfigured: boolean }) {
  const accounts = useDeliveryAccounts();
  const connect = useConnectAccount();
  const refresh = useRefreshAccount();
  const [label, setLabel] = useState('');
  const [link, setLink] = useState<string | null>(null);
  const labelId = useId();

  function start(provider: AccountProvider) {
    connect.mutate(
      { provider, label: label.trim() || PROVIDER_LABEL[provider] },
      {
        onSuccess: ({ connect_url }) => {
          setLink(connect_url);
          setLabel('');
          window.open(connect_url, '_blank', 'noopener');
        },
      },
    );
  }

  return (
    <HudPanel className="space-y-4 p-5">
      <div>
        <h2 className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase">
          Cuentas de envío
        </h2>
        <p className="mt-1 text-xs text-slate-400">Desde dónde salen los reportes.</p>
      </div>

      {accounts.isPending && <p className="text-sm text-slate-400">Cargando cuentas…</p>}
      {accounts.data?.length === 0 && (
        <p className="text-sm text-slate-400">Todavía no hay cuentas. Conecta una abajo.</p>
      )}
      <ul className="space-y-2">
        {accounts.data?.map((account) => {
          const status = ACCOUNT_STATUS[account.status];
          return (
            <li
              key={account.id}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-sky-400/15 px-3 py-2"
            >
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-slate-100">{account.label}</span>
                <span className="block text-xs text-slate-400">
                  {PROVIDER_LABEL[account.provider]}
                  {account.address ? ` · ${account.address}` : ''}
                </span>
              </span>
              <HudChip tone={status.tone} dot>
                {status.label}
              </HudChip>
              {account.status !== 'active' && (
                <HudButton
                  size="sm"
                  variant="ghost"
                  disabled={refresh.isPending}
                  onClick={() => {
                    refresh.mutate(account.id);
                  }}
                >
                  Ya autoricé
                </HudButton>
              )}
            </li>
          );
        })}
      </ul>

      <div className="space-y-2 border-t border-sky-400/10 pt-4">
        <label htmlFor={labelId} className="hud-label">
          Nombre de la cuenta nueva <span className="font-normal text-slate-500">(opcional)</span>
        </label>
        <input
          id={labelId}
          value={label}
          maxLength={80}
          placeholder="Por ejemplo: Reportes Oráculo"
          onChange={(event) => {
            setLabel(event.target.value);
          }}
          className="hud-input"
        />
        <div className="flex flex-wrap gap-2">
          <HudButton
            size="sm"
            disabled={!emailConfigured || connect.isPending}
            onClick={() => {
              start('outlook');
            }}
          >
            Conectar Outlook / Hotmail
          </HudButton>
          <HudButton
            size="sm"
            disabled={!emailConfigured || connect.isPending}
            onClick={() => {
              start('gmail');
            }}
          >
            Conectar Gmail
          </HudButton>
          <HudButton size="sm" variant="ghost" disabled title="Llega en una siguiente etapa">
            WhatsApp · Próximamente
          </HudButton>
        </div>
        {!emailConfigured && (
          <p className="text-xs text-amber-300">
            Falta <code className="font-mono">COMPOSIO_API_KEY</code> en el .env para conectar
            cuentas.
          </p>
        )}
        {link && (
          <p className="text-xs text-slate-300">
            Se abrió la autorización en otra pestaña. Si no se abrió,{' '}
            <a href={link} target="_blank" rel="noreferrer" className="text-sky-300 underline">
              ábrela aquí
            </a>
            . Al terminar, pulsa «Ya autoricé».
          </p>
        )}
        {(connect.error ?? refresh.error) && (
          <p role="alert" className="text-xs text-rose-300">
            {(connect.error ?? refresh.error)?.message}
          </p>
        )}
      </div>
    </HudPanel>
  );
}
