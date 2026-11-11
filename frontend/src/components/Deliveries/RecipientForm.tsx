/**
 * Formulario de un destinatario (nombre, correo, WhatsApp, a qué horas y si
 * recibe envíos).
 *
 * Lo usan la ventana «Agregar destinatario» y el perfil desplegable de cada
 * destinatario. Los errores del servidor aparecen junto a su campo. Las horas
 * salen del horario vigente: sin elegir ninguna, recibe todas (ADR-0045).
 *
 * No hace: no guarda; avisa con `onSubmit`.
 */
import { type ReactNode, useId, useState } from 'react';

import { deliveryFieldErrors, type RecipientInput } from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudSwitch } from '../ui/HudSwitch';
import { hoursLabel, toggleHour } from './schedule';

interface RecipientFormProps {
  initial?: RecipientInput;
  submitLabel: string;
  pending: boolean;
  error: Error | null;
  onSubmit: (input: RecipientInput) => void;
  onCancel?: () => void;
  /** Botones extra al final (por ejemplo, «Eliminar»). */
  extra?: ReactNode;
  /** Horas del horario vigente («HH:MM») entre las que se elige. */
  times?: string[];
  /** WhatsApp todavía no se manda: el campo solo lo ve el superusuario. */
  showPhone?: boolean;
}

const EMPTY: RecipientInput = { name: '', email: null, phone: null, is_active: true, hours: [] };

export function RecipientForm({
  initial = EMPTY,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
  extra,
  times = [],
  showPhone = true,
}: RecipientFormProps) {
  const [name, setName] = useState(initial.name);
  const [email, setEmail] = useState(initial.email ?? '');
  const [phone, setPhone] = useState(initial.phone ?? '');
  const [active, setActive] = useState(initial.is_active);
  const [hours, setHours] = useState<string[]>(initial.hours ?? []);
  const id = useId();
  const fields = deliveryFieldErrors(error);

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
        onSubmit({
          name,
          email: email.trim() || null,
          phone: phone.trim() || null,
          is_active: active,
          // Horas que ya no están en el horario no se mandan: el servidor las rechazaría.
          hours: hours.filter((h) => times.includes(h)),
        });
      }}
      className="space-y-3"
    >
      <div>
        <label htmlFor={`${id}-name`} className="hud-label">
          Nombre
        </label>
        <input
          id={`${id}-name`}
          value={name}
          maxLength={120}
          onChange={(e) => {
            setName(e.target.value);
          }}
          className="hud-input"
        />
        {errorText('name')}
      </div>
      <div className={showPhone ? 'grid gap-3 sm:grid-cols-2' : ''}>
        <div>
          <label htmlFor={`${id}-email`} className="hud-label">
            Correo
          </label>
          <input
            id={`${id}-email`}
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
            }}
            className="hud-input"
          />
          {errorText('email')}
        </div>
        {showPhone && (
          <div>
            <label htmlFor={`${id}-phone`} className="hud-label">
              WhatsApp <span className="font-normal text-slate-500">(opcional)</span>
            </label>
            <input
              id={`${id}-phone`}
              value={phone}
              placeholder="525512345678"
              onChange={(e) => {
                setPhone(e.target.value);
              }}
              className="hud-input"
            />
            {errorText('phone')}
          </div>
        )}
      </div>
      {times.length > 0 && (
        <fieldset>
          <legend className="hud-label">¿A qué horas te llega?</legend>
          <div className="flex flex-wrap gap-2">
            {times.map((time) => {
              const on = hours.includes(time);
              return (
                <button
                  key={time}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    setHours((current) => toggleHour(current, time));
                  }}
                  className={`rounded-md border px-3 py-1 font-mono text-xs transition ${
                    on
                      ? 'border-cyan-300/60 bg-cyan-400/15 text-cyan-100'
                      : 'border-sky-400/20 text-slate-300 hover:border-sky-300/40'
                  }`}
                >
                  {time}
                </button>
              );
            })}
          </div>
          <p className="mt-1 text-xs text-slate-400">
            {hoursLabel(hours, times)}. Si no eliges ninguna, te llegan todas.
          </p>
          {errorText('hours')}
        </fieldset>
      )}
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-slate-200">Recibe envíos</span>
        <HudSwitch checked={active} onChange={setActive} label="Recibe envíos" />
      </div>
      {error && Object.keys(fields).length === 0 && (
        <p role="alert" className="text-xs text-rose-300">
          {error.message}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <HudButton type="submit" variant="solid" size="sm" disabled={pending}>
          {pending ? 'Guardando…' : submitLabel}
        </HudButton>
        {onCancel && (
          <HudButton size="sm" variant="ghost" onClick={onCancel}>
            Cancelar
          </HudButton>
        )}
        {extra}
      </div>
    </form>
  );
}
