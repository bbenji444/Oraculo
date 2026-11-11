/**
 * Formulario de un envío programado (ADR-0046): nombre, qué temas, de qué
 * región, a qué horas (las que quiera, al minuto), qué días y a cuáles de sus
 * correos.
 *
 * Avisa antes de guardar si pasa del tope de corridas al día; quien decide es
 * el servidor, y sus errores aparecen junto a cada campo.
 *
 * No hace: no guarda; avisa con `onSubmit`.
 */
import { type ReactNode, useId, useState } from 'react';

import { useConcepts } from '../../hooks/useConcepts';
import { useRegionsByLevel } from '../../hooks/useRegions';
import { deliveryFieldErrors, type Recipient, type ScheduleInput } from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudSwitch } from '../ui/HudSwitch';
import { RegionField } from './RegionField';
import { addTime, DAYS, dailyRunsWith, toggleDay } from './schedule';

interface ScheduleFormProps {
  initial: ScheduleInput;
  /** Los correos del dueño del envío. */
  recipients: Recipient[];
  /** Horas y días de los demás envíos prendidos del dueño (para el tope). */
  others: { times: string[]; days: number[] }[];
  dailyLimit: number;
  /** Costo promedio de una corrida, si se sabe. */
  runCost: number | null;
  submitLabel: string;
  pending: boolean;
  error: Error | null;
  onSubmit: (input: ScheduleInput) => void;
  onCancel: () => void;
  extra?: ReactNode;
}

export function ScheduleForm({
  initial,
  recipients,
  others,
  dailyLimit,
  runCost,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
  extra,
}: ScheduleFormProps) {
  const id = useId();
  const concepts = (useConcepts().data ?? []).filter(
    (c) => c.is_active || initial.concept_ids.includes(c.id),
  );
  const [name, setName] = useState(initial.name);
  const [conceptIds, setConceptIds] = useState(initial.concept_ids);
  const [regionId, setRegionId] = useState<number | null>(initial.region_id || null);
  const [times, setTimes] = useState(initial.times);
  const [newTime, setNewTime] = useState('');
  const [days, setDays] = useState(initial.days);
  const [recipientIds, setRecipientIds] = useState(initial.recipient_ids);
  const [active, setActive] = useState(initial.is_active);
  const fields = deliveryFieldErrors(error);
  const runs = dailyRunsWith(others, { times: active ? times : [], days });
  // Sin región elegida vale «Todo México» (el país de los estados).
  const mexicoId = useRegionsByLevel('state').data?.[0]?.parent_id ?? null;
  const region = regionId ?? mexicoId;
  const overLimit = runs > dailyLimit;

  const errorText = (field: string) =>
    fields[field]?.map((m) => (
      <p key={m} className="mt-1 text-xs text-rose-300">
        {m}
      </p>
    ));

  const toggle = (list: number[], value: number) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (region === null) return;
        onSubmit({
          name,
          concept_ids: conceptIds,
          region_id: region,
          times,
          days,
          recipient_ids: recipientIds,
          is_active: active,
        });
      }}
    >
      <div>
        <label htmlFor={`${id}-name`} className="hud-label">
          Nombre del envío
        </label>
        <input
          id={`${id}-name`}
          value={name}
          maxLength={80}
          placeholder="Por ejemplo: Extorsión Jalisco tarde"
          onChange={(e) => {
            setName(e.target.value);
          }}
          className="hud-input"
        />
        {errorText('name')}
      </div>

      <fieldset>
        <legend className="hud-label">¿De qué temas?</legend>
        <div className="flex flex-wrap gap-2">
          {concepts.map((concept) => {
            const on = conceptIds.includes(concept.id);
            return (
              <button
                key={concept.id}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setConceptIds((current) => toggle(current, concept.id));
                }}
                className={`rounded-md border px-3 py-1 text-xs transition ${
                  on
                    ? 'border-cyan-300/60 bg-cyan-400/15 text-cyan-100'
                    : 'border-sky-400/20 text-slate-300 hover:border-sky-300/40'
                }`}
              >
                {concept.name}
              </button>
            );
          })}
        </div>
        {errorText('concept_ids')}
      </fieldset>

      <fieldset>
        <legend className="hud-label">¿De dónde?</legend>
        <RegionField value={region} onChange={setRegionId} />
        {errorText('region_id')}
      </fieldset>

      <fieldset>
        <legend className="hud-label">¿A qué horas? (hora de la Ciudad de México)</legend>
        <div className="flex flex-wrap items-center gap-2">
          {times.map((time) => (
            <span
              key={time}
              className="flex items-center gap-1 rounded-md border border-cyan-300/40 bg-cyan-400/10 px-2 py-1 font-mono text-xs text-cyan-100"
            >
              {time}
              <button
                type="button"
                aria-label={`Quitar las ${time}`}
                onClick={() => {
                  setTimes((current) => current.filter((t) => t !== time));
                }}
                className="text-slate-400 hover:text-rose-300"
              >
                ×
              </button>
            </span>
          ))}
          <input
            type="time"
            aria-label="Hora nueva"
            value={newTime}
            onChange={(e) => {
              setNewTime(e.target.value);
            }}
            className="hud-input w-32 px-2 py-1 text-xs"
          />
          <HudButton
            size="sm"
            variant="ghost"
            disabled={!newTime}
            onClick={() => {
              setTimes((current) => addTime(current, newTime));
              setNewTime('');
            }}
          >
            + Agregar hora
          </HudButton>
        </div>
        <p className={`mt-1 text-xs ${overLimit ? 'text-rose-300' : 'text-slate-400'}`}>
          Sumando todos tus envíos: {runs} de {dailyLimit} corridas al día.
          {runCost !== null && ` Cada hora es un reporte nuevo (≈ US$${runCost.toFixed(2)}).`}
        </p>
        {errorText('times')}
      </fieldset>

      <fieldset>
        <legend className="hud-label">¿Qué días?</legend>
        <div className="flex flex-wrap gap-1.5">
          {DAYS.map((day) => {
            const on = days.includes(day.value);
            return (
              <button
                key={day.value}
                type="button"
                aria-pressed={on}
                title={day.long}
                onClick={() => {
                  setDays((current) => toggleDay(current, day.value));
                }}
                className={`h-8 w-8 rounded-md border text-xs transition ${
                  on
                    ? 'border-cyan-300/60 bg-cyan-400/15 text-cyan-100'
                    : 'border-sky-400/20 text-slate-300 hover:border-sky-300/40'
                }`}
              >
                {day.short}
              </button>
            );
          })}
        </div>
        <p className="mt-1 text-xs text-slate-400">
          {days.length === 0 ? 'Todos los días.' : 'Solo los días marcados.'}
        </p>
        {errorText('days')}
      </fieldset>

      <fieldset>
        <legend className="hud-label">¿A qué correos?</legend>
        {recipients.length === 0 ? (
          <p className="text-xs text-amber-200">
            Primero agrega un correo en «Mis correos»: sin correos, el envío no se corre.
          </p>
        ) : (
          <div className="space-y-1">
            {recipients.map((r) => (
              <label key={r.id} className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={recipientIds.includes(r.id)}
                  onChange={() => {
                    setRecipientIds((current) => toggle(current, r.id));
                  }}
                />
                {r.name} <span className="text-xs text-slate-400">{r.email}</span>
              </label>
            ))}
          </div>
        )}
        {errorText('recipient_ids')}
      </fieldset>

      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-slate-200">Prendido</span>
        <HudSwitch checked={active} onChange={setActive} label="Envío prendido" />
      </div>

      {error && Object.keys(fields).length === 0 && (
        <p role="alert" className="text-xs text-rose-300">
          {error.message}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <HudButton
          type="submit"
          variant="solid"
          size="sm"
          disabled={pending || region === null || conceptIds.length === 0 || times.length === 0}
        >
          {pending ? 'Guardando…' : submitLabel}
        </HudButton>
        <HudButton size="sm" variant="ghost" onClick={onCancel}>
          Cancelar
        </HudButton>
        {extra}
      </div>
    </form>
  );
}
