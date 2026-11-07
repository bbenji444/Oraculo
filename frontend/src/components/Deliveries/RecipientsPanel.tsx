/**
 * Destinatarios: a quién se le manda (ADR-0039).
 *
 * - «+ Agregar», arriba a la derecha, abre una ventana para registrar uno nuevo.
 * - «Editar» despliega el perfil ahí mismo para cambiarlo, apagarlo o borrarlo.
 *
 * No hace: no decide qué recibe cada quien (eso es la programación de envíos).
 */
import { useState } from 'react';

import { useDeleteRecipient, useRecipients, useSaveRecipient } from '../../hooks/useDeliveries';
import type { Recipient } from '../../services/deliveries';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { Modal } from './Modal';
import { RecipientForm } from './RecipientForm';

function RecipientItem({
  recipient,
  open,
  onToggle,
}: {
  recipient: Recipient;
  open: boolean;
  onToggle: () => void;
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
        {!recipient.is_active && <HudChip tone="slate">Apagado</HudChip>}
        <HudButton size="sm" variant="ghost" aria-expanded={open} onClick={onToggle}>
          {open ? 'Cerrar' : 'Editar'}
        </HudButton>
      </div>
      {open && (
        <div className="border-t border-sky-400/10 px-3 py-3">
          <RecipientForm
            initial={recipient}
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

export function RecipientsPanel() {
  const recipients = useRecipients();
  const create = useSaveRecipient();
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <HudPanel className="space-y-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase">
            Destinatarios
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            A quién se le manda.
            {recipients.data
              ? ` ${String(recipients.data.filter((r) => r.is_active).length)} activos.`
              : ''}
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
          + Agregar
        </HudButton>
      </div>

      {recipients.isPending && <p className="text-sm text-slate-400">Cargando destinatarios…</p>}
      {recipients.data?.length === 0 && (
        <p className="text-sm text-slate-400">Todavía no hay destinatarios. Agrega el primero.</p>
      )}
      <ul className="space-y-2">
        {recipients.data?.map((r) => (
          <RecipientItem
            key={r.id}
            recipient={r}
            open={openId === r.id}
            onToggle={() => {
              setOpenId((current) => (current === r.id ? null : r.id));
            }}
          />
        ))}
      </ul>

      {adding && (
        <Modal
          title="Agregar destinatario"
          onClose={() => {
            setAdding(false);
          }}
        >
          <RecipientForm
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
