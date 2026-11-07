/**
 * Reglas de envío: qué, a quién, por dónde, desde qué cuenta y a qué hora (ADR-0039).
 *
 * Cada regla se lee como una frase («Reporte FGR → Benjamin → por correo
 * desde Ovitech → 07:00 y 15:00») y se prende o apaga con su interruptor.
 * WhatsApp aparece como canal, pero desactivado hasta la siguiente etapa.
 *
 * No hace: no manda nada (eso pasa al terminar cada corrida).
 */
import { useId, useState } from 'react';

import {
  useDeliveryAccounts,
  useDeliveryOverview,
  useRecipients,
  useRules,
  useSaveRule,
} from '../../hooks/useDeliveries';
import { deliveryFieldErrors, type Rule } from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudPanel } from '../ui/HudPanel';
import { HudSelect } from '../ui/HudSelect';
import { HudSwitch } from '../ui/HudSwitch';
import { hoursLabel } from './labels';

export function RulesPanel() {
  const overview = useDeliveryOverview().data;
  const rules = useRules();
  const recipients = useRecipients().data ?? [];
  const accounts = (useDeliveryAccounts().data ?? []).filter((a) => a.channel === 'email');
  const save = useSaveRule();
  const id = useId();
  const source = overview?.sources[0]?.id ?? 'monitor.corrida_fgr';
  const runHours = overview?.run_hours ?? [7, 15, 23];
  const [recipientId, setRecipientId] = useState<number>(0);
  const [accountId, setAccountId] = useState<number>(0);
  const [hours, setHours] = useState<number[]>([]);
  const fields = deliveryFieldErrors(save.error);

  const nameOf = (rid: number) => recipients.find((r) => r.id === rid)?.name ?? '—';
  const accountOf = (aid: number | null) => accounts.find((a) => a.id === aid)?.label ?? '—';

  function toggleHour(hour: number) {
    setHours((current) =>
      current.includes(hour) ? current.filter((h) => h !== hour) : [...current, hour].sort(),
    );
  }

  function add(event: React.FormEvent) {
    event.preventDefault();
    save.mutate(
      {
        input: {
          source,
          recipient_id: recipientId,
          channel: 'email',
          account_id: accountId || null,
          hours,
          is_active: true,
        },
      },
      {
        onSuccess: () => {
          setHours([]);
        },
      },
    );
  }

  function toggleRule(rule: Rule) {
    save.mutate({ input: { ...rule, is_active: !rule.is_active }, id: rule.id });
  }

  return (
    <HudPanel className="space-y-4 p-5">
      <div>
        <h2 className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase">
          Reglas de envío
        </h2>
        <p className="mt-1 text-xs text-slate-400">Qué se manda, a quién, por dónde y cuándo.</p>
      </div>

      {rules.data?.length === 0 && <p className="text-sm text-slate-400">Todavía no hay reglas.</p>}
      <ul className="space-y-2">
        {rules.data?.map((rule) => (
          <li
            key={rule.id}
            className="flex flex-wrap items-center gap-3 rounded-lg border border-sky-400/15 px-3 py-2"
          >
            <span className="min-w-0 flex-1 text-sm text-slate-200">
              <span className="text-slate-400">Reporte FGR</span> ›{' '}
              <b className="font-medium text-slate-50">{nameOf(rule.recipient_id)}</b> › por{' '}
              {rule.channel === 'email' ? 'correo' : 'WhatsApp'} desde {accountOf(rule.account_id)}{' '}
              › {hoursLabel(rule.hours, runHours)}
            </span>
            <HudSwitch
              checked={rule.is_active}
              onChange={() => {
                toggleRule(rule);
              }}
              label={`Regla de ${nameOf(rule.recipient_id)}`}
            />
          </li>
        ))}
      </ul>

      <form
        onSubmit={add}
        aria-label="Agregar regla"
        className="space-y-3 border-t border-sky-400/10 pt-4"
      >
        <p className="hud-label mb-0">Agregar regla</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor={`${id}-recipient`} className="hud-label">
              A quién
            </label>
            <HudSelect
              id={`${id}-recipient`}
              size="sm"
              value={recipientId}
              invalid={fields.recipient_id !== undefined}
              options={[
                { value: 0, label: 'Elige un destinatario' },
                ...recipients
                  .filter((r) => r.is_active)
                  .map((r) => ({ value: r.id, label: r.name })),
              ]}
              onChange={setRecipientId}
            />
          </div>
          <div>
            <label htmlFor={`${id}-account`} className="hud-label">
              Desde qué cuenta
            </label>
            <HudSelect
              id={`${id}-account`}
              size="sm"
              value={accountId}
              invalid={fields.account_id !== undefined}
              options={[
                { value: 0, label: 'Elige la cuenta' },
                ...accounts
                  .filter((a) => a.status === 'active')
                  .map((a) => ({ value: a.id, label: a.label })),
              ]}
              onChange={setAccountId}
            />
          </div>
        </div>
        <fieldset>
          <legend className="hud-label">Canal</legend>
          <div className="flex gap-2">
            <HudButton size="sm" variant="solid" aria-pressed="true">
              Correo
            </HudButton>
            <HudButton size="sm" variant="ghost" disabled title="Llega en una siguiente etapa">
              WhatsApp · Próximamente
            </HudButton>
          </div>
        </fieldset>
        <fieldset>
          <legend className="hud-label">En qué corridas</legend>
          <div className="flex flex-wrap gap-2">
            {runHours.map((hour) => {
              const on = hours.includes(hour);
              return (
                <button
                  key={hour}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    toggleHour(hour);
                  }}
                  className={`hud-btn hud-btn--sm ${on ? 'hud-btn--solid' : ''}`}
                >
                  {String(hour).padStart(2, '0')}:00
                </button>
              );
            })}
          </div>
          <p className="mt-1 text-xs text-slate-500">Sin ninguna elegida: todas las corridas.</p>
        </fieldset>
        {Object.values(fields)
          .flat()
          .map((message) => (
            <p key={message} className="text-xs text-rose-300">
              {message}
            </p>
          ))}
        {save.error && Object.keys(fields).length === 0 && (
          <p role="alert" className="text-xs text-rose-300">
            {save.error.message}
          </p>
        )}
        <HudButton type="submit" variant="solid" size="sm" disabled={save.isPending}>
          Agregar regla
        </HudButton>
      </form>
    </HudPanel>
  );
}
