/**
 * Destinatarios: a quién se le manda (ADR-0039).
 *
 * Lista con «Editar» y un formulario corto para agregar o editar (nombre,
 * correo y WhatsApp). Los errores del servidor aparecen junto a su campo.
 *
 * No hace: no decide qué recibe cada quien (eso son las reglas).
 */
import { useId, useState } from 'react';

import { useRecipients, useSaveRecipient } from '../../hooks/useDeliveries';
import { deliveryFieldErrors, type Recipient } from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { HudSwitch } from '../ui/HudSwitch';

interface Draft {
  name: string;
  email: string;
  phone: string;
  is_active: boolean;
}

const EMPTY: Draft = { name: '', email: '', phone: '', is_active: true };

function toDraft(r: Recipient): Draft {
  return { name: r.name, email: r.email ?? '', phone: r.phone ?? '', is_active: r.is_active };
}

export function RecipientsPanel() {
  const recipients = useRecipients();
  const save = useSaveRecipient();
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [editing, setEditing] = useState<number | null>(null);
  const id = useId();
  const fields = deliveryFieldErrors(save.error);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    save.mutate(
      {
        input: {
          name: draft.name,
          email: draft.email.trim() || null,
          phone: draft.phone.trim() || null,
          is_active: draft.is_active,
        },
        id: editing ?? undefined,
      },
      {
        onSuccess: () => {
          setDraft(EMPTY);
          setEditing(null);
        },
      },
    );
  }

  const errorText = (field: string) =>
    fields[field]?.map((m) => (
      <p key={m} className="mt-1 text-xs text-rose-300">
        {m}
      </p>
    ));

  return (
    <HudPanel className="space-y-4 p-5">
      <div>
        <h2 className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase">
          Destinatarios
        </h2>
        <p className="mt-1 text-xs text-slate-400">A quién se le manda.</p>
      </div>

      {recipients.data?.length === 0 && (
        <p className="text-sm text-slate-400">Todavía no hay destinatarios.</p>
      )}
      <ul className="space-y-2">
        {recipients.data?.map((r) => (
          <li
            key={r.id}
            className="flex flex-wrap items-center gap-2 rounded-lg border border-sky-400/15 px-3 py-2"
          >
            <span className="min-w-0 flex-1">
              <span className="block text-sm text-slate-100">{r.name}</span>
              <span className="block truncate text-xs text-slate-400">
                {[r.email, r.phone && `WhatsApp ${r.phone}`].filter(Boolean).join(' · ')}
              </span>
            </span>
            {!r.is_active && <HudChip tone="slate">Apagado</HudChip>}
            <HudButton
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(r.id);
                setDraft(toDraft(r));
              }}
            >
              Editar
            </HudButton>
          </li>
        ))}
      </ul>

      <form
        onSubmit={submit}
        aria-label={editing ? 'Editar destinatario' : 'Agregar destinatario'}
        className="space-y-3 border-t border-sky-400/10 pt-4"
      >
        <p className="hud-label mb-0">{editing ? 'Editar destinatario' : 'Agregar destinatario'}</p>
        <div>
          <label htmlFor={`${id}-name`} className="hud-label">
            Nombre
          </label>
          <input
            id={`${id}-name`}
            value={draft.name}
            maxLength={120}
            onChange={(e) => {
              set('name', e.target.value);
            }}
            className="hud-input"
          />
          {errorText('name')}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor={`${id}-email`} className="hud-label">
              Correo
            </label>
            <input
              id={`${id}-email`}
              type="email"
              value={draft.email}
              onChange={(e) => {
                set('email', e.target.value);
              }}
              className="hud-input"
            />
            {errorText('email')}
          </div>
          <div>
            <label htmlFor={`${id}-phone`} className="hud-label">
              WhatsApp <span className="font-normal text-slate-500">(opcional)</span>
            </label>
            <input
              id={`${id}-phone`}
              value={draft.phone}
              placeholder="525512345678"
              onChange={(e) => {
                set('phone', e.target.value);
              }}
              className="hud-input"
            />
            {errorText('phone')}
          </div>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-slate-200">Recibe envíos</span>
          <HudSwitch
            checked={draft.is_active}
            onChange={(checked) => {
              set('is_active', checked);
            }}
            label="Recibe envíos"
          />
        </div>
        {save.error && Object.keys(fields).length === 0 && (
          <p role="alert" className="text-xs text-rose-300">
            {save.error.message}
          </p>
        )}
        <div className="flex gap-2">
          <HudButton type="submit" variant="solid" size="sm" disabled={save.isPending}>
            {editing ? 'Guardar cambios' : 'Agregar'}
          </HudButton>
          {editing && (
            <HudButton
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(null);
                setDraft(EMPTY);
              }}
            >
              Cancelar
            </HudButton>
          )}
        </div>
      </form>
    </HudPanel>
  );
}
