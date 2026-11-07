/**
 * Horario de las corridas y envío del reporte (ADR-0040).
 *
 * Benji, 06/11/2026: un solo horario para todos, que maneja el administrador.
 * A cada hora se hace una corrida **nueva** (búsqueda + IA + PDF) con lo
 * publicado desde la hora anterior, y su reporte se manda a todos los
 * destinatarios activos. Agregar las 19:00 entre las 15:00 y las 23:00 crea
 * un reporte de 15:00 a 19:00, y el de las 23:00 pasa a cubrir de 19:00 a 23:00.
 *
 * Los cambios se arman aquí y se guardan con «Guardar horario»; aplican en el
 * minuto siguiente. Cada hora extra cuesta una corrida: se avisa cuánto.
 *
 * No hace: no manda nada (eso pasa en el servidor al terminar cada corrida).
 */
import { useId, useState } from 'react';

import { useDeliveryAccounts, useRules, useSaveRule } from '../../hooks/useDeliveries';
import { useSaveSchedule, useSchedule } from '../../hooks/useSchedule';
import type { Schedule } from '../../services/schedule';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { HudSwitch } from '../ui/HudSwitch';
import { whenLabel } from './labels';
import { DAYS, daysLabel, scheduleProblem, sortTimes, weeklyCost, WORKDAYS } from './schedule';

const SOURCE = 'monitor.corrida_fgr';
// Hora que propone el campo «Agregar hora» al abrir la pantalla.
const DEFAULT_NEW_TIME = '19:00';

const usd = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});
const usdRun = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 3,
});

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

/** El horario guardado, para comparar con lo que se está editando. */
function sameSchedule(a: { times: string[]; days: number[] }, b: Schedule): boolean {
  return (
    sortTimes(a.times).join() === sortTimes(b.times).join() &&
    [...a.days].sort().join() === [...b.days].sort().join()
  );
}

function ScheduleEditor({ schedule }: { schedule: Schedule }) {
  const save = useSaveSchedule();
  const [times, setTimes] = useState(schedule.times);
  const [days, setDays] = useState(schedule.days);
  const [newTime, setNewTime] = useState(DEFAULT_NEW_TIME);
  const id = useId();

  const sorted = sortTimes(times);
  const dirty = !sameSchedule({ times, days }, schedule);
  const problem = scheduleProblem(sorted, schedule.limits);
  const cost = weeklyCost(sorted, days, schedule.average_run_cost_usd);
  const extra = sorted.length - schedule.times.length;

  function toggleDay(value: number) {
    const all = DAYS.map((d) => d.value);
    const current = days.length === 0 ? all : days;
    const next = current.includes(value) ? current.filter((d) => d !== value) : [...current, value];
    setDays(next.length === all.length ? [] : next);
  }

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (!problem) save.mutate({ times: sorted, days });
      }}
    >
      <fieldset className="space-y-2">
        <legend className="hud-label">A qué horas se hace una corrida</legend>
        <div className="flex flex-wrap items-center gap-2">
          {sorted.map((time, index) => {
            const previous = sorted.at(index - 1) ?? time;
            return (
              <span
                key={time}
                className="inline-flex items-center gap-2 rounded-full border border-sky-300/50 bg-sky-400/15 px-3 py-1 text-xs text-white"
              >
                <span className="font-mono text-sm">{time}</span>
                <span className="text-[10px] text-sky-300">
                  {sorted.length > 1 ? `desde ${previous}` : 'últimas 24 h'}
                </span>
                <button
                  type="button"
                  aria-label={`Quitar ${time}`}
                  disabled={sorted.length === 1}
                  onClick={() => {
                    setTimes(sorted.filter((t) => t !== time));
                  }}
                  className="text-slate-300 hover:text-rose-300 disabled:opacity-30"
                >
                  ×
                </button>
              </span>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={`${id}-time`} className="sr-only">
            Hora nueva
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
            disabled={!newTime || sorted.includes(newTime)}
            onClick={() => {
              setTimes(sortTimes([...sorted, newTime]));
            }}
          >
            + Agregar hora
          </HudButton>
        </div>
        <p className="text-xs text-slate-400">
          Cada reporte cubre desde la hora anterior hasta la suya. Máximo{' '}
          {schedule.limits.max_runs_per_day} horas al día, con al menos{' '}
          {schedule.limits.min_gap_minutes} minutos entre una y otra.
        </p>
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="hud-label">Qué días</legend>
        <div className="flex flex-wrap gap-2">
          {DAYS.map((day) => (
            <Chip
              key={day.value}
              on={days.length === 0 || days.includes(day.value)}
              title={day.long}
              onClick={() => {
                toggleDay(day.value);
              }}
            >
              {day.short}
            </Chip>
          ))}
          <HudButton
            size="sm"
            variant="ghost"
            onClick={() => {
              setDays(WORKDAYS);
            }}
          >
            Lunes a viernes
          </HudButton>
          <HudButton
            size="sm"
            variant="ghost"
            onClick={() => {
              setDays([]);
            }}
          >
            Todos
          </HudButton>
        </div>
        <p className="text-xs text-slate-400">Se corre {daysLabel(days)}.</p>
      </fieldset>

      <div className="rounded-lg border border-sky-400/15 bg-sky-400/5 px-4 py-3 text-sm text-slate-200">
        <p>
          <b>
            {sorted.length} {sorted.length === 1 ? 'corrida' : 'corridas'} al día
          </b>{' '}
          · {daysLabel(days)}
          {cost !== null && <> · ≈ {usd.format(cost)} a la semana en IA</>}
        </p>
        {schedule.average_run_cost_usd !== null && (
          <p className="mt-1 text-xs text-slate-400">
            Cada hora extra es una corrida más (≈ {usdRun.format(schedule.average_run_cost_usd)}{' '}
            cada una, promedio de las últimas dos semanas).
          </p>
        )}
        {dirty && extra > 0 && (
          <p className="mt-1 text-xs text-amber-300">
            {extra === 1
              ? 'Agregaste 1 hora: será 1 corrida más al día.'
              : `Agregaste ${String(extra)} horas: serán ${String(extra)} corridas más al día.`}
          </p>
        )}
      </div>

      {problem && (
        <p role="alert" className="text-xs text-rose-300">
          {problem}
        </p>
      )}
      {save.error && (
        <p role="alert" className="text-xs text-rose-300">
          {save.error.message}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-sky-400/10 pt-4">
        <HudButton
          type="submit"
          variant="solid"
          size="sm"
          disabled={!dirty || problem !== null || save.isPending}
        >
          {save.isPending ? 'Guardando…' : 'Guardar horario'}
        </HudButton>
        {dirty && (
          <HudButton
            size="sm"
            variant="ghost"
            onClick={() => {
              setTimes(schedule.times);
              setDays(schedule.days);
              save.reset();
            }}
          >
            Descartar cambios
          </HudButton>
        )}
        <span className="ml-auto text-xs text-slate-500">
          {schedule.is_default
            ? 'Horario inicial del servidor.'
            : `Último cambio: ${schedule.updated_by ?? '—'}${
                schedule.updated_at ? `, ${whenLabel(schedule.updated_at)}` : ''
              }.`}
        </span>
      </div>
    </form>
  );
}

function SendSettings() {
  const rules = useRules();
  const accounts = useDeliveryAccounts().data ?? [];
  const save = useSaveRule();
  const id = useId();
  const rule = rules.data?.find((r) => r.source === SOURCE && r.channel === 'email');
  const emailAccounts = accounts.filter((a) => a.channel === 'email');
  const accountId =
    rule?.account_id ?? emailAccounts.find((a) => a.status === 'active')?.id ?? null;

  return (
    <section aria-label="Envío del reporte" className="space-y-3">
      <h3 className="font-display text-xs tracking-[0.16em] text-sky-200 uppercase">
        Envío del reporte
      </h3>
      <p className="text-xs text-slate-400">
        Al terminar cada corrida, su reporte (PDF) se manda por correo a todos los destinatarios con
        «Recibe envíos» prendido.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[14rem] flex-1">
          <label htmlFor={`${id}-account`} className="hud-label">
            Se manda desde
          </label>
          <select
            id={`${id}-account`}
            value={accountId ?? ''}
            onChange={(e) => {
              save.mutate({
                source: SOURCE,
                channel: 'email',
                account_id: Number(e.target.value),
                is_active: rule?.is_active ?? true,
              });
            }}
            className="hud-input"
          >
            {accountId === null && <option value="">Conecta una cuenta de correo</option>}
            {emailAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
                {a.address ? ` · ${a.address}` : ''}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2 pb-1">
          <span className="text-sm text-slate-200">Mandar el reporte</span>
          <HudSwitch
            checked={rule?.is_active ?? false}
            disabled={accountId === null || save.isPending}
            onChange={(checked) => {
              save.mutate({
                source: SOURCE,
                channel: 'email',
                account_id: accountId,
                is_active: checked,
              });
            }}
            label="Mandar el reporte de cada corrida"
          />
        </div>
      </div>
      {save.error && (
        <p role="alert" className="text-xs text-rose-300">
          {save.error.message}
        </p>
      )}
    </section>
  );
}

export function SchedulePanel() {
  const schedule = useSchedule();
  const data = schedule.data;

  return (
    <HudPanel className="space-y-6 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase">
            Horario de las corridas
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Un solo horario para todos. A cada hora se hace un reporte nuevo con lo publicado desde
            la hora anterior.
          </p>
        </div>
        {data && (
          <HudChip tone={data.enabled ? 'green' : 'amber'} dot live={data.enabled}>
            {data.enabled ? 'Corridas automáticas prendidas' : 'Corridas automáticas apagadas'}
          </HudChip>
        )}
      </div>

      {schedule.isPending && <p className="text-sm text-slate-400">Cargando horario…</p>}
      {schedule.error && (
        <p role="alert" className="text-sm text-rose-300">
          {schedule.error.message}
        </p>
      )}
      {data && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="space-y-6">
            {/* Si cambia lo guardado (otro administrador o recién guardado), el editor
                vuelve a empezar desde el servidor. */}
            <ScheduleEditor key={`${data.times.join()}|${data.days.join()}`} schedule={data} />
            <div className="border-t border-sky-400/10 pt-5">
              <SendSettings />
            </div>
          </div>
          <aside aria-label="Próximas corridas" className="space-y-3">
            <h3 className="font-display text-xs tracking-[0.16em] text-sky-200 uppercase">
              Próximas corridas
            </h3>
            <ol className="space-y-2">
              {data.upcoming.map((at) => (
                <li key={at} className="rounded-lg border border-sky-400/15 px-3 py-2">
                  <span className="block text-sm text-slate-100">{whenLabel(at)}</span>
                </li>
              ))}
            </ol>
          </aside>
        </div>
      )}
    </HudPanel>
  );
}
