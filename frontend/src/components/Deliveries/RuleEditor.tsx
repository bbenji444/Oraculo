/**
 * Editor de una regla de envío (ADR-0039): a quién, desde qué cuenta, por qué
 * canal, a qué horas y qué días.
 *
 * - **A quién:** «Todos» (con excepciones: «todos menos Tadeo») o «Solo algunos».
 * - **Horas:** se agregan o quitan libremente; las de las corridas (07:00,
 *   15:00 y 23:00) están a un clic. En una hora sin corrida se manda el
 *   reporte más reciente.
 * - **Días:** de lunes a domingo; sin ninguno, todos.
 *
 * No hace: no guarda; avisa con `onSave`.
 */
import { useId, useState } from 'react';

import {
  type DeliveryAccount,
  deliveryFieldErrors,
  type Recipient,
  type RuleAudience,
  type RuleInput,
} from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudSegmented } from '../ui/HudSegmented';
import { HudSelect } from '../ui/HudSelect';
import { HudSwitch } from '../ui/HudSwitch';
import { DAYS, sortTimes } from './schedule';

interface RuleEditorProps {
  initial: RuleInput;
  recipients: readonly Recipient[];
  accounts: readonly DeliveryAccount[];
  runTimes: readonly string[];
  pending: boolean;
  error: Error | null;
  onSave: (input: RuleInput) => void;
  onCancel?: () => void;
  onDelete?: () => void;
  /** La regla general: siempre «a todos». */
  general?: boolean;
}

const AUDIENCES = [
  { value: 'all', label: 'Todos' },
  { value: 'selected', label: 'Solo algunos' },
] as const satisfies readonly { value: RuleAudience; label: string }[];

function Chip({
  on,
  children,
  onClick,
  title,
}: {
  on: boolean;
  children: React.ReactNode;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      title={title}
      onClick={onClick}
      className={`hud-btn hud-btn--sm ${on ? 'hud-btn--solid' : ''}`}
    >
      {children}
    </button>
  );
}

export function RuleEditor({
  initial,
  recipients,
  accounts,
  runTimes,
  pending,
  error,
  onSave,
  onCancel,
  onDelete,
  general = false,
}: RuleEditorProps) {
  const [draft, setDraft] = useState<RuleInput>(initial);
  const [newTime, setNewTime] = useState('09:00');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const id = useId();
  const fields = deliveryFieldErrors(error);
  const active = recipients.filter((r) => r.is_active);
  const emailAccounts = accounts.filter((a) => a.channel === 'email' && a.status === 'active');

  function set<K extends keyof RuleInput>(key: K, value: RuleInput[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function toggle(list: 'recipient_ids' | 'exclude_ids' | 'days', value: number) {
    const current = draft[list];
    set(list, current.includes(value) ? current.filter((v) => v !== value) : [...current, value]);
  }

  function addTime(time: string) {
    if (time) set('times', sortTimes([...draft.times, time]));
  }

  const errorText = (field: string) =>
    fields[field]?.map((m) => (
      <p key={m} className="mt-1 text-xs text-rose-300">
        {m}
      </p>
    ));

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSave(draft);
      }}
      className="space-y-4"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-name`} className="hud-label">
            Nombre de la regla
          </label>
          <input
            id={`${id}-name`}
            value={draft.name}
            maxLength={80}
            onChange={(e) => {
              set('name', e.target.value);
            }}
            className="hud-input"
          />
          {errorText('name')}
        </div>
        <div>
          <label htmlFor={`${id}-account`} className="hud-label">
            Desde qué cuenta
          </label>
          <HudSelect
            id={`${id}-account`}
            size="sm"
            value={draft.account_id ?? 0}
            invalid={fields.account_id !== undefined}
            options={[
              { value: 0, label: 'Elige la cuenta' },
              ...emailAccounts.map((a) => ({ value: a.id, label: a.label })),
            ]}
            onChange={(value) => {
              set('account_id', value || null);
            }}
          />
          {errorText('account_id')}
        </div>
      </div>

      <fieldset className="space-y-2">
        <legend className="hud-label">A quién</legend>
        {!general && (
          <HudSegmented
            options={AUDIENCES}
            value={draft.audience}
            onChange={(value) => {
              set('audience', value);
            }}
            label="A quién manda la regla"
          />
        )}
        {draft.audience === 'all' ? (
          <div className="space-y-2">
            <p className="text-xs text-slate-400">
              A todos los destinatarios activos ({active.length}). Toca a alguien para excluirlo:
            </p>
            <div className="flex flex-wrap gap-2">
              {active.map((r) => {
                const excluded = draft.exclude_ids.includes(r.id);
                return (
                  <button
                    key={r.id}
                    type="button"
                    aria-pressed={!excluded}
                    title={excluded ? `${r.name} no recibe` : `${r.name} recibe`}
                    onClick={() => {
                      toggle('exclude_ids', r.id);
                    }}
                    className={`hud-btn hud-btn--sm ${excluded ? 'line-through opacity-50' : 'hud-btn--solid'}`}
                  >
                    {r.name}
                  </button>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-slate-400">Elige quién recibe:</p>
            <div className="flex flex-wrap gap-2">
              {active.map((r) => (
                <Chip
                  key={r.id}
                  on={draft.recipient_ids.includes(r.id)}
                  onClick={() => {
                    toggle('recipient_ids', r.id);
                  }}
                >
                  {r.name}
                </Chip>
              ))}
            </div>
            {errorText('recipient_ids')}
          </div>
        )}
      </fieldset>

      <fieldset className="space-y-2">
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

      <fieldset className="space-y-2">
        <legend className="hud-label">A qué horas</legend>
        <div className="flex flex-wrap items-center gap-2">
          {draft.times.length === 0 && (
            <span className="text-xs text-amber-300">Agrega al menos una hora.</span>
          )}
          {draft.times.map((time) => (
            <span
              key={time}
              className="inline-flex items-center gap-1 rounded-full border border-sky-300/50 bg-sky-400/15 px-3 py-1 text-xs text-white"
            >
              {time}
              {runTimes.includes(time) && <span className="text-[10px] text-sky-300">corrida</span>}
              <button
                type="button"
                aria-label={`Quitar ${time}`}
                onClick={() => {
                  set(
                    'times',
                    draft.times.filter((t) => t !== time),
                  );
                }}
                className="ml-1 text-slate-300 hover:text-rose-300"
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {runTimes
            .filter((t) => !draft.times.includes(t))
            .map((time) => (
              <HudButton
                key={time}
                size="sm"
                variant="ghost"
                onClick={() => {
                  addTime(time);
                }}
              >
                + {time}
              </HudButton>
            ))}
          <label htmlFor={`${id}-time`} className="sr-only">
            Otra hora
          </label>
          <input
            id={`${id}-time`}
            type="time"
            value={newTime}
            onChange={(e) => {
              setNewTime(e.target.value);
            }}
            className="hud-input w-32 py-1"
          />
          <HudButton
            size="sm"
            onClick={() => {
              addTime(newTime);
            }}
          >
            Agregar hora
          </HudButton>
        </div>
        <p className="text-xs text-slate-500">
          En las horas con corrida se manda el reporte recién hecho; en las demás, el más reciente.
        </p>
        {errorText('times')}
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="hud-label">Qué días</legend>
        <div className="flex flex-wrap gap-2">
          {DAYS.map((day) => (
            <Chip
              key={day.value}
              on={draft.days.length === 0 || draft.days.includes(day.value)}
              title={day.long}
              onClick={() => {
                const all = DAYS.map((d) => d.value);
                const current = draft.days.length === 0 ? all : draft.days;
                const next = current.includes(day.value)
                  ? current.filter((d) => d !== day.value)
                  : [...current, day.value];
                set('days', next.length === all.length ? [] : next);
              }}
            >
              {day.short}
            </Chip>
          ))}
          <HudButton
            size="sm"
            variant="ghost"
            onClick={() => {
              set('days', [1, 2, 3, 4, 5]);
            }}
          >
            Lunes a viernes
          </HudButton>
          <HudButton
            size="sm"
            variant="ghost"
            onClick={() => {
              set('days', []);
            }}
          >
            Todos
          </HudButton>
        </div>
        {errorText('days')}
      </fieldset>

      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-slate-200">Regla prendida</span>
        <HudSwitch
          checked={draft.is_active}
          onChange={(checked) => {
            set('is_active', checked);
          }}
          label="Regla prendida"
        />
      </div>

      {error && Object.keys(fields).length === 0 && (
        <p role="alert" className="text-xs text-rose-300">
          {error.message}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-sky-400/10 pt-4">
        <HudButton type="submit" variant="solid" size="sm" disabled={pending}>
          {pending ? 'Guardando…' : 'Guardar regla'}
        </HudButton>
        {onCancel && (
          <HudButton size="sm" variant="ghost" onClick={onCancel}>
            Cancelar
          </HudButton>
        )}
        {onDelete &&
          (confirmDelete ? (
            <span className="ml-auto flex items-center gap-2 text-xs text-rose-200">
              ¿Borrar esta regla?
              <HudButton size="sm" variant="danger" onClick={onDelete}>
                Sí, borrar
              </HudButton>
              <HudButton
                size="sm"
                variant="ghost"
                onClick={() => {
                  setConfirmDelete(false);
                }}
              >
                No
              </HudButton>
            </span>
          ) : (
            <HudButton
              size="sm"
              variant="danger"
              className="ml-auto"
              onClick={() => {
                setConfirmDelete(true);
              }}
            >
              Borrar regla
            </HudButton>
          ))}
      </div>
    </form>
  );
}
