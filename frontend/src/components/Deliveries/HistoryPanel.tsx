/**
 * Historial de envíos y «Mandar prueba» (ADR-0039).
 *
 * Cada fila es la guía de un envío: a quién, cuándo, estado, intentos y el
 * error en español. Las fallidas tienen «Reintentar». Arriba, «Mandar prueba»
 * manda ya la última corrida a un destinatario. El superusuario elige la
 * cuenta; los demás siempre mandan desde el correo que él eligió (ADR-0045).
 *
 * No hace: no crea reglas.
 */
import { useId, useState } from 'react';

import {
  useDeliveryAccounts,
  useDeliveryHistory,
  useRecipients,
  useRetryDelivery,
  useSendTest,
} from '../../hooks/useDeliveries';
import { HudButton } from '../ui/HudButton';
import { HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { HudSelect } from '../ui/HudSelect';
import { DELIVERY_STATUS, whenLabel } from './labels';

function TestSend({ isSuperuser }: { isSuperuser: boolean }) {
  const recipients = (useRecipients().data ?? []).filter((r) => r.is_active && r.email);
  const accounts = (useDeliveryAccounts(isSuperuser).data ?? []).filter(
    (a) => a.channel === 'email' && a.status === 'active',
  );
  const send = useSendTest();
  const id = useId();
  const [recipientId, setRecipientId] = useState(0);
  const [accountId, setAccountId] = useState(0);
  const result = send.data;

  return (
    <div className="space-y-3 rounded-lg border border-sky-400/15 p-4">
      <p className="hud-label mb-0">Mandar prueba</p>
      <p className="text-xs text-slate-400">
        {isSuperuser
          ? 'Manda ya el reporte de la última corrida a una persona. Funciona aunque los envíos automáticos estén apagados.'
          : 'Te manda ya el reporte de la última corrida, para que veas cómo llega.'}
      </p>
      <div
        className={`grid gap-3 sm:items-end ${
          isSuperuser ? 'sm:grid-cols-[1fr_1fr_auto]' : 'sm:grid-cols-[1fr_auto]'
        }`}
      >
        <div>
          <label htmlFor={`${id}-to`} className="hud-label">
            Para
          </label>
          <HudSelect
            id={`${id}-to`}
            size="sm"
            value={recipientId}
            options={[
              { value: 0, label: isSuperuser ? 'Elige un destinatario' : 'Elige tu correo' },
              ...recipients.map((r) => ({ value: r.id, label: r.name })),
            ]}
            onChange={setRecipientId}
          />
        </div>
        {isSuperuser && (
          <div>
            <label htmlFor={`${id}-from`} className="hud-label">
              Desde
            </label>
            <HudSelect
              id={`${id}-from`}
              size="sm"
              value={accountId}
              options={[
                { value: 0, label: 'Elige la cuenta' },
                ...accounts.map((a) => ({ value: a.id, label: a.label })),
              ]}
              onChange={setAccountId}
            />
          </div>
        )}
        <HudButton
          variant="solid"
          size="sm"
          disabled={!recipientId || (isSuperuser && !accountId) || send.isPending}
          onClick={() => {
            send.mutate({ recipientId, accountId: isSuperuser ? accountId : undefined });
          }}
        >
          {send.isPending ? 'Enviando…' : 'Mandar prueba'}
        </HudButton>
      </div>
      {result && (
        <p
          role="status"
          className={`text-xs ${result.status === 'sent' ? 'text-emerald-300' : 'text-rose-300'}`}
        >
          {result.status === 'sent'
            ? `Enviado a ${result.destination}. Puede tardar unos minutos en llegar.`
            : `No se pudo mandar: ${result.last_error ?? 'error desconocido'}`}
        </p>
      )}
      {send.error && (
        <p role="alert" className="text-xs text-rose-300">
          {send.error.message}
        </p>
      )}
    </div>
  );
}

export function HistoryPanel({ isSuperuser }: { isSuperuser: boolean }) {
  const history = useDeliveryHistory();
  const retry = useRetryDelivery();
  const items = history.data?.items ?? [];

  return (
    <HudPanel className="space-y-4 p-5">
      <div>
        <h2 className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase">
          {isSuperuser ? 'Historial de envíos' : 'Lo que te hemos mandado'}
        </h2>
        <p className="mt-1 text-xs text-slate-400">
          Cada envío con su resultado: si llegó al proveedor, cuántos intentos y por qué falló.
        </p>
      </div>

      <TestSend isSuperuser={isSuperuser} />

      {history.isPending && <p className="text-sm text-slate-400">Cargando historial…</p>}
      {history.data && items.length === 0 && (
        <p className="text-sm text-slate-400">Todavía no se ha mandado nada.</p>
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-400">
              <tr>
                <th className="py-2 pr-3 font-normal">Cuándo</th>
                <th className="py-2 pr-3 font-normal">Para</th>
                <th className="py-2 pr-3 font-normal">Qué</th>
                <th className="py-2 pr-3 font-normal">Estado</th>
                <th className="py-2 font-normal" />
              </tr>
            </thead>
            <tbody>
              {items.map((d) => {
                const status = DELIVERY_STATUS[d.status];
                return (
                  <tr key={d.id} className="border-t border-sky-400/10 align-top">
                    <td className="py-2 pr-3 whitespace-nowrap text-slate-300">
                      {whenLabel(d.created_at)}
                    </td>
                    <td className="py-2 pr-3">
                      <span className="block text-slate-100">
                        {d.recipient_name ?? '—'}
                        {isSuperuser && d.owner ? (
                          <span className="text-xs text-slate-500"> · de {d.owner}</span>
                        ) : null}
                      </span>
                      <span className="block text-xs text-slate-400">
                        {d.channel === 'email' ? 'Correo' : 'WhatsApp'} · {d.destination}
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <span className="block text-slate-200">{d.subject}</span>
                      <span className="block text-xs text-slate-500">
                        {d.attachment_name ?? 'sin adjunto'}
                        {d.is_test ? ' · prueba' : ''}
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <HudChip tone={status.tone} dot live={d.status === 'sending'}>
                        {status.label}
                      </HudChip>
                      <span className="mt-1 block text-xs text-slate-500">
                        {d.attempts} {d.attempts === 1 ? 'intento' : 'intentos'}
                      </span>
                      {d.last_error && (
                        <span className="mt-1 block max-w-xs text-xs text-rose-300">
                          {d.last_error}
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-right">
                      {(d.status === 'failed' || d.status === 'skipped') && (
                        <HudButton
                          size="sm"
                          variant="ghost"
                          disabled={retry.isPending}
                          onClick={() => {
                            retry.mutate(d.id);
                          }}
                        >
                          Reintentar
                        </HudButton>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {retry.error && (
        <p role="alert" className="text-xs text-rose-300">
          {retry.error.message}
        </p>
      )}
    </HudPanel>
  );
}
