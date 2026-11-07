/**
 * Programación de envíos (ADR-0039): la regla general, las reglas
 * personalizadas y los próximos envíos.
 *
 * - **Regla general:** el reporte a todos los destinatarios activos, a las horas
 *   y días que elijas, con excepciones («todos menos Tadeo»).
 * - **Reglas personalizadas:** para unas cuantas personas, con sus propias
 *   horas y días. Se ven como tarjetas compactas que se despliegan para editar.
 * - **Próximos envíos:** qué va a salir, cuándo y a cuántas personas.
 *
 * No hace: no manda nada (eso pasa en el servidor a cada hora programada).
 */
import { useState } from 'react';

import {
  useDeleteRule,
  useDeliveryAccounts,
  useDeliveryOverview,
  useRecipients,
  useRules,
  useSaveRule,
} from '../../hooks/useDeliveries';
import { useNow } from '../../hooks/useNow';
import type { Rule, RuleInput } from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { HudSwitch } from '../ui/HudSwitch';
import { whenLabel } from './labels';
import { RuleEditor } from './RuleEditor';
import { daysLabel, ruleTargets, upcomingSends } from './schedule';

// Próximos envíos que se listan: lo que cabe sin desplazarse.
const UPCOMING = 6;

type Editing = { kind: 'none' } | { kind: 'new' } | { kind: 'rule'; id: number };

function toInput(rule: Rule): RuleInput {
  return {
    source: rule.source,
    name: rule.name,
    audience: rule.audience,
    recipient_ids: rule.recipient_ids,
    exclude_ids: rule.exclude_ids,
    channel: rule.channel,
    account_id: rule.account_id,
    times: rule.times,
    days: rule.days,
    is_active: rule.is_active,
  };
}

export function SchedulePanel() {
  const overview = useDeliveryOverview().data;
  const rules = useRules();
  const recipients = useRecipients().data ?? [];
  const accounts = useDeliveryAccounts().data ?? [];
  const save = useSaveRule();
  const remove = useDeleteRule();
  const now = useNow();
  const [editing, setEditing] = useState<Editing>({ kind: 'none' });
  const [creatingGeneral, setCreatingGeneral] = useState(false);

  const source = overview?.sources[0]?.id ?? 'monitor.corrida_fgr';
  const runTimes = overview?.run_times ?? ['07:00', '15:00', '23:00'];
  const firstAccount =
    accounts.find((a) => a.channel === 'email' && a.status === 'active')?.id ?? null;
  const list = rules.data ?? [];
  const general = list.find((r) => r.audience === 'all');
  const custom = list.filter((r) => r !== general);
  const upcoming = upcomingSends(list, recipients, now, UPCOMING);

  const blank = (audience: 'all' | 'selected'): RuleInput => ({
    source,
    name: audience === 'all' ? 'Regla general' : 'Regla personalizada',
    audience,
    recipient_ids: [],
    exclude_ids: [],
    channel: 'email',
    account_id: firstAccount,
    times: audience === 'all' ? [...runTimes] : [],
    days: [],
    is_active: true,
  });

  const editorProps = {
    recipients,
    accounts,
    runTimes,
    pending: save.isPending,
    error: save.error,
  };

  function saveRule(input: RuleInput, id?: number, done?: () => void) {
    save.mutate({ input, id }, { onSuccess: () => done?.() });
  }

  return (
    <HudPanel className="space-y-6 p-5">
      <div>
        <h2 className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase">
          Programación de envíos
        </h2>
        <p className="mt-1 text-xs text-slate-400">
          Qué se manda, a quién, a qué horas y qué días. Hoy: el reporte de la corrida FGR.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-6">
          <section aria-label="Regla general" className="rounded-xl border border-sky-400/25 p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <h3 className="font-display text-xs tracking-[0.16em] text-sky-200 uppercase">
                Regla general · a todos
              </h3>
              {general && (
                <HudChip tone={general.is_active ? 'green' : 'slate'} dot>
                  {general.is_active ? 'Prendida' : 'Apagada'}
                </HudChip>
              )}
            </div>
            {general ? (
              <RuleEditor
                key={`${String(general.id)}:${general.times.join()}:${String(general.is_active)}`}
                {...editorProps}
                general
                initial={toInput(general)}
                onSave={(input) => {
                  saveRule(input, general.id);
                }}
                onDelete={() => {
                  remove.mutate(general.id);
                }}
              />
            ) : creatingGeneral ? (
              <RuleEditor
                {...editorProps}
                general
                initial={blank('all')}
                onSave={(input) => {
                  saveRule(input, undefined, () => {
                    setCreatingGeneral(false);
                  });
                }}
                onCancel={() => {
                  setCreatingGeneral(false);
                }}
              />
            ) : (
              <div className="space-y-2">
                <p className="text-sm text-slate-300">
                  Todavía no hay una regla general. Con ella, el reporte llega a todos los
                  destinatarios activos a las horas que elijas.
                </p>
                <HudButton
                  size="sm"
                  variant="solid"
                  onClick={() => {
                    save.reset();
                    setCreatingGeneral(true);
                  }}
                >
                  Crear regla general
                </HudButton>
              </div>
            )}
          </section>

          <section aria-label="Reglas personalizadas" className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-display text-xs tracking-[0.16em] text-sky-200 uppercase">
                  Reglas personalizadas
                </h3>
                <p className="text-xs text-slate-400">
                  Para unas cuantas personas, con sus propias horas y días.
                </p>
              </div>
              <HudButton
                size="sm"
                onClick={() => {
                  save.reset();
                  setEditing({ kind: 'new' });
                }}
              >
                + Regla personalizada
              </HudButton>
            </div>

            {editing.kind === 'new' && (
              <div className="rounded-xl border border-sky-400/25 p-4">
                <RuleEditor
                  {...editorProps}
                  initial={blank('selected')}
                  onSave={(input) => {
                    saveRule(input, undefined, () => {
                      setEditing({ kind: 'none' });
                    });
                  }}
                  onCancel={() => {
                    setEditing({ kind: 'none' });
                  }}
                />
              </div>
            )}

            {custom.length === 0 && editing.kind !== 'new' && (
              <p className="text-sm text-slate-400">No hay reglas personalizadas.</p>
            )}
            <ul className="space-y-2">
              {custom.map((rule) => {
                const open = editing.kind === 'rule' && editing.id === rule.id;
                const people = ruleTargets(rule, recipients);
                return (
                  <li key={rule.id} className="rounded-xl border border-sky-400/15">
                    <div className="flex flex-wrap items-center gap-3 px-4 py-3">
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm text-slate-100">{rule.name}</span>
                        <span className="block text-xs text-slate-400">
                          {rule.audience === 'all'
                            ? `Todos (${String(people.length)})`
                            : people.map((p) => p.name).join(', ') ||
                              'Sin destinatarios activos'}{' '}
                          · {rule.times.join(', ')} · {daysLabel(rule.days)}
                        </span>
                      </span>
                      <HudSwitch
                        checked={rule.is_active}
                        onChange={() => {
                          saveRule({ ...toInput(rule), is_active: !rule.is_active }, rule.id);
                        }}
                        label={`Prender o apagar ${rule.name}`}
                      />
                      <HudButton
                        size="sm"
                        variant="ghost"
                        aria-expanded={open}
                        onClick={() => {
                          save.reset();
                          setEditing(open ? { kind: 'none' } : { kind: 'rule', id: rule.id });
                        }}
                      >
                        {open ? 'Cerrar' : 'Editar'}
                      </HudButton>
                    </div>
                    {open && (
                      <div className="border-t border-sky-400/10 p-4">
                        <RuleEditor
                          {...editorProps}
                          initial={toInput(rule)}
                          onSave={(input) => {
                            saveRule(input, rule.id, () => {
                              setEditing({ kind: 'none' });
                            });
                          }}
                          onCancel={() => {
                            setEditing({ kind: 'none' });
                          }}
                          onDelete={() => {
                            remove.mutate(rule.id, {
                              onSuccess: () => {
                                setEditing({ kind: 'none' });
                              },
                            });
                          }}
                        />
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        </div>

        <aside aria-label="Próximos envíos" className="space-y-3">
          <h3 className="font-display text-xs tracking-[0.16em] text-sky-200 uppercase">
            Próximos envíos
          </h3>
          {upcoming.length === 0 ? (
            <p className="text-sm text-slate-400">No hay envíos programados.</p>
          ) : (
            <ol className="space-y-2">
              {upcoming.map((send) => (
                <li
                  key={`${String(send.rule.id)}-${send.at.toISOString()}`}
                  className="rounded-lg border border-sky-400/15 px-3 py-2"
                >
                  <span className="block text-sm text-slate-100">
                    {whenLabel(send.at.toISOString())}
                  </span>
                  <span className="block text-xs text-slate-400">
                    {send.rule.name} · a {send.recipients}{' '}
                    {send.recipients === 1 ? 'persona' : 'personas'}
                  </span>
                </li>
              ))}
            </ol>
          )}
          {overview && !overview.enabled && (
            <p className="text-xs text-amber-300">
              Los envíos automáticos están apagados: esto es lo que saldría al encenderlos.
            </p>
          )}
          {remove.error && (
            <p role="alert" className="text-xs text-rose-300">
              {remove.error.message}
            </p>
          )}
        </aside>
      </div>
    </HudPanel>
  );
}
