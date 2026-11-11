/**
 * Envíos programados («Mis envíos», ADR-0046).
 *
 * Una tarjeta por envío: qué temas, de dónde, a qué horas, qué días, a qué
 * correos y cuándo es la próxima corrida. «+ Nuevo envío» abre el formulario
 * y «Editar» lo despliega ahí mismo para cambiarlo, apagarlo o borrarlo.
 *
 * Cada persona ve los suyos; el superusuario ve los de todos, con su dueño.
 *
 * No hace: no manda nada; el reloj lanza las corridas a su hora.
 */
import { useState } from 'react';

import {
  useDeleteSchedule,
  useRecipients,
  useSaveSchedule,
  useSchedules,
} from '../../hooks/useDeliveries';
import type { DeliverySchedule, Recipient, ScheduleInput } from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { Modal } from './Modal';
import { ScheduleForm } from './ScheduleForm';
import { daysLabel } from './schedule';
import { whenLabel } from './labels';

const EMPTY: ScheduleInput = {
  name: '',
  concept_ids: [],
  region_id: 0,
  times: [],
  days: [],
  recipient_ids: [],
  is_active: true,
};

interface PanelProps {
  isSuperuser: boolean;
  /** Quién está viendo (para saber cuáles son suyos). */
  username: string;
}

function ScheduleCard({
  schedule,
  open,
  onToggle,
  isSuperuser,
  form,
}: {
  schedule: DeliverySchedule;
  open: boolean;
  onToggle: () => void;
  isSuperuser: boolean;
  form: FormContext;
}) {
  const save = useSaveSchedule();
  const remove = useDeleteSchedule();
  const [confirm, setConfirm] = useState(false);
  const mails = form
    .recipientsOf(schedule.owner)
    .filter((r) => schedule.recipient_ids.includes(r.id));
  const next = schedule.upcoming[0];

  return (
    <li className="rounded-lg border border-sky-400/15">
      <div className="flex flex-wrap items-start gap-2 px-3 py-2">
        <span className="min-w-0 flex-1 space-y-0.5">
          <span className="block text-sm text-slate-100">{schedule.name}</span>
          <span className="block text-xs text-slate-300">
            {schedule.concept_names.join(', ')} · {schedule.region_name ?? '—'}
          </span>
          <span className="block font-mono text-xs text-cyan-200">
            {schedule.times.join(' · ')}{' '}
            <span className="font-sans text-slate-400">({daysLabel(schedule.days)})</span>
          </span>
          <span className="block truncate text-xs text-slate-400">
            {mails.length > 0
              ? `A: ${mails.map((m) => m.email ?? m.name).join(', ')}`
              : 'Sin correos: no se corre hasta que elijas uno.'}
          </span>
          {schedule.is_active && next && mails.length > 0 && (
            <span className="block text-xs text-slate-500">Próxima: {whenLabel(next)}</span>
          )}
        </span>
        {isSuperuser && <HudChip tone="slate">{schedule.owner}</HudChip>}
        {!schedule.is_active && <HudChip tone="slate">Apagado</HudChip>}
        <HudButton size="sm" variant="ghost" aria-expanded={open} onClick={onToggle}>
          {open ? 'Cerrar' : 'Editar'}
        </HudButton>
      </div>
      {open && (
        <div className="border-t border-sky-400/10 px-3 py-3">
          <ScheduleForm
            initial={schedule}
            recipients={form.recipientsOf(schedule.owner)}
            others={form.othersOf(schedule.owner, schedule.id)}
            dailyLimit={form.dailyLimit}
            runCost={form.runCost}
            submitLabel="Guardar cambios"
            pending={save.isPending}
            error={save.error}
            onCancel={onToggle}
            onSubmit={(input) => {
              save.mutate({ input, id: schedule.id }, { onSuccess: onToggle });
            }}
            extra={
              confirm ? (
                <span className="ml-auto flex items-center gap-2 text-xs text-rose-200">
                  ¿Borrar «{schedule.name}»?
                  <HudButton
                    size="sm"
                    variant="danger"
                    disabled={remove.isPending}
                    onClick={() => {
                      remove.mutate(schedule.id);
                    }}
                  >
                    Sí, borrar
                  </HudButton>
                  <HudButton
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setConfirm(false);
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
                    setConfirm(true);
                  }}
                >
                  Borrar
                </HudButton>
              )
            }
          />
        </div>
      )}
    </li>
  );
}

/** Lo que el formulario necesita saber del resto de los envíos y correos. */
interface FormContext {
  recipientsOf: (owner: string) => Recipient[];
  othersOf: (owner: string, exceptId: number | null) => { times: string[]; days: number[] }[];
  dailyLimit: number;
  runCost: number | null;
}

export function SchedulesPanel({ isSuperuser, username }: PanelProps) {
  const schedules = useSchedules();
  const recipients = useRecipients().data ?? [];
  const create = useSaveSchedule();
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const items = schedules.data?.items ?? [];
  const form: FormContext = {
    recipientsOf: (owner) => recipients.filter((r) => r.owner === owner),
    othersOf: (owner, exceptId) =>
      items
        .filter((s) => s.owner === owner && s.id !== exceptId && s.is_active)
        .map((s) => ({ times: s.times, days: s.days })),
    dailyLimit: schedules.data?.daily_limit ?? 0,
    runCost: schedules.data?.average_run_cost_usd ?? null,
  };

  return (
    <HudPanel className="space-y-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase">
            {isSuperuser ? 'Envíos programados' : 'Mis envíos programados'}
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Qué reporte te llega, de dónde, a qué horas y qué días.
            {schedules.data &&
              ` Usas ${String(schedules.data.daily_runs)} de ${String(schedules.data.daily_limit)} corridas al día.`}
          </p>
        </div>
        <HudButton
          size="sm"
          variant="solid"
          onClick={() => {
            create.reset();
            setAdding(true);
          }}
        >
          + Nuevo envío
        </HudButton>
      </div>

      {schedules.isPending && <p className="text-sm text-slate-400">Cargando envíos…</p>}
      {schedules.error && (
        <p role="alert" className="text-sm text-rose-300">
          {schedules.error.message}
        </p>
      )}
      {schedules.data && items.length === 0 && (
        <p className="text-sm text-slate-400">
          Todavía no tienes envíos programados. Crea el primero con «+ Nuevo envío».
        </p>
      )}
      <ul className="space-y-2">
        {items.map((s) => (
          <ScheduleCard
            key={s.id}
            schedule={s}
            open={openId === s.id}
            isSuperuser={isSuperuser}
            form={form}
            onToggle={() => {
              setOpenId((current) => (current === s.id ? null : s.id));
            }}
          />
        ))}
      </ul>

      {adding && (
        <Modal
          title="Nuevo envío programado"
          onClose={() => {
            setAdding(false);
          }}
        >
          <ScheduleForm
            initial={EMPTY}
            recipients={form.recipientsOf(username)}
            others={form.othersOf(username, null)}
            dailyLimit={form.dailyLimit}
            runCost={form.runCost}
            submitLabel="Programar"
            pending={create.isPending}
            error={create.error}
            onCancel={() => {
              setAdding(false);
            }}
            onSubmit={(input) => {
              create.mutate(
                { input },
                {
                  onSuccess: () => {
                    setAdding(false);
                  },
                },
              );
            }}
          />
        </Modal>
      )}
    </HudPanel>
  );
}
