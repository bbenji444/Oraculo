/**
 * Destinatarios: a quién se le manda (ADR-0039, ADR-0045).
 *
 * - «+ Agregar», arriba a la derecha, abre una ventana para registrar uno nuevo
 *   (un usuario normal, hasta su tope: dos correos).
 * - «Editar» despliega el perfil ahí mismo para cambiarlo, apagarlo o borrarlo.
 * - Cada persona ve solo los suyos; el superusuario ve todos, con su dueño.
 *
 * No hace: no decide desde qué correo se manda (eso es del superusuario).
 */
import { useState } from 'react';

import { useDeleteRecipient, useRecipients, useSaveRecipient } from '../../hooks/useDeliveries';
import type { Recipient } from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { Modal } from './Modal';
import { RecipientForm } from './RecipientForm';

interface Mode {
  /** Superusuario: ve todos, con su dueño, y el campo de WhatsApp. */
  isSuperuser: boolean;
}

function RecipientItem({
  recipient,
  open,
  onToggle,
  mode,
}: {
  recipient: Recipient;
  open: boolean;
  onToggle: () => void;
  mode: Mode;
}) {
  const save = useSaveRecipient();
  const remove = useDeleteRecipient();
  const [confirm, setConfirm] = useState(false);
  const contact = [recipient.email, recipient.phone && `WhatsApp ${recipient.phone}`]
    .filter(Boolean)
    .join(' · ');

  return (
    <li className="rounded-lg border border-sky-400/15">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        <span className="min-w-0 flex-1">
          <span className="block text-sm text-slate-100">{recipient.name}</span>
          <span className="block truncate text-xs text-slate-400">{contact}</span>
        </span>
        {mode.isSuperuser && recipient.owner && <HudChip tone="slate">{recipient.owner}</HudChip>}
        {!recipient.is_active && <HudChip tone="slate">Apagado</HudChip>}
        <HudButton size="sm" variant="ghost" aria-expanded={open} onClick={onToggle}>
          {open ? 'Cerrar' : 'Editar'}
        </HudButton>
      </div>
      {open && (
        <div className="border-t border-sky-400/10 px-3 py-3">
          <RecipientForm
            initial={recipient}
            showPhone={mode.isSuperuser}
            submitLabel="Guardar cambios"
            pending={save.isPending}
            error={save.error}
            onCancel={onToggle}
            onSubmit={(input) => {
              save.mutate({ input, id: recipient.id }, { onSuccess: onToggle });
            }}
            extra={
              confirm ? (
                <span className="ml-auto flex items-center gap-2 text-xs text-rose-200">
                  ¿Borrar a {recipient.name}?
                  <HudButton
                    size="sm"
                    variant="danger"
                    disabled={remove.isPending}
                    onClick={() => {
                      remove.mutate(recipient.id);
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

export function RecipientsPanel({
  isSuperuser,
  maxRecipients = null,
}: {
  isSuperuser: boolean;
  /** Tope de correos de la persona (`null` = sin tope). */
  maxRecipients?: number | null;
}) {
  const recipients = useRecipients();
  const create = useSaveRecipient();
  const mode: Mode = { isSuperuser };
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const count = recipients.data?.length ?? 0;
  const full = maxRecipients !== null && count >= maxRecipients;

  return (
    <HudPanel className="space-y-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase">
            {isSuperuser ? 'Destinatarios' : 'Mis correos'}
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            {isSuperuser ? 'A quién se le manda.' : 'A dónde te llega el reporte.'}
            {recipients.data
              ? ` ${String(recipients.data.filter((r) => r.is_active).length)} activos.`
              : ''}
            {maxRecipients !== null && ` Puedes tener hasta ${String(maxRecipients)}.`}
          </p>
        </div>
        <HudButton
          size="sm"
          variant="solid"
          disabled={full}
          title={full ? 'Ya tienes el máximo de correos' : undefined}
          onClick={() => {
            create.reset();
            setAdding(true);
          }}
        >
          + Agregar
        </HudButton>
      </div>

      {recipients.isPending && <p className="text-sm text-slate-400">Cargando destinatarios…</p>}
      {recipients.data?.length === 0 && (
        <p className="text-sm text-slate-400">
          {isSuperuser
            ? 'Todavía no hay destinatarios. Agrega el primero.'
            : 'Todavía no tienes correos. Agrega el tuyo y te empezará a llegar el reporte.'}
        </p>
      )}
      <ul className="space-y-2">
        {recipients.data?.map((r) => (
          <RecipientItem
            key={r.id}
            recipient={r}
            open={openId === r.id}
            mode={mode}
            onToggle={() => {
              setOpenId((current) => (current === r.id ? null : r.id));
            }}
          />
        ))}
      </ul>

      {adding && (
        <Modal
          title={isSuperuser ? 'Agregar destinatario' : 'Agregar mi correo'}
          onClose={() => {
            setAdding(false);
          }}
        >
          <RecipientForm
            showPhone={isSuperuser}
            submitLabel="Agregar"
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
