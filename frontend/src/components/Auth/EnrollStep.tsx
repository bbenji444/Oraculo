/**
 * Primer ingreso: dar de alta Microsoft Authenticator (ADR-0043).
 *
 * Igual que en Oráculo: se abre la app, se toca «+» → «Otra cuenta» y se
 * escanea el QR. Si la cámara no puede, se muestra el secreto para teclearlo.
 * El primer código confirma que el celular quedó bien.
 *
 * El QR llega del servidor como SVG y se muestra como imagen `data:`: una
 * imagen no puede ejecutar código.
 *
 * No hace: no guarda el secreto (el servidor lo cifra).
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { type Enrollment, looksLikeCode, qrImageSrc, startEnrollment } from '../../services/auth';
import { HudButton } from '../ui/HudButton';
import { CodeField } from './CodeField';

interface EnrollStepProps {
  ticket: string;
  pending: boolean;
  error: Error | null;
  onConfirm: (code: string) => void;
}

export function EnrollStep({ ticket, pending, error, onConfirm }: EnrollStepProps) {
  const [code, setCode] = useState('');
  // Una consulta (y no una acción) para pedir el QR una sola vez aunque React
  // monte el paso dos veces: cada pedido genera un secreto nuevo.
  const enroll = useQuery({
    queryKey: ['auth', 'enroll', ticket],
    queryFn: () => startEnrollment(ticket),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });
  const data: Enrollment | undefined = enroll.data;

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (looksLikeCode(code)) onConfirm(code.replace(/\s/g, ''));
      }}
    >
      <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-300">
        <li>Abre Microsoft Authenticator en tu celular.</li>
        <li>
          Toca <strong>+</strong> → <strong>Otra cuenta</strong> y escanea este código.
        </li>
        <li>Escribe abajo los 6 dígitos que aparecen para «Oráculo Monitor».</li>
      </ol>
      {enroll.isPending && <p className="text-sm text-slate-400">Generando tu código QR…</p>}
      {enroll.error && (
        <p role="alert" className="text-sm text-rose-300">
          {enroll.error.message}
        </p>
      )}
      {data && (
        <div className="flex flex-col items-center gap-2">
          <img
            src={qrImageSrc(data.qr_svg)}
            alt="Código QR para Microsoft Authenticator"
            className="size-48 rounded-lg bg-white p-2"
          />
          <details className="w-full text-xs text-slate-400">
            <summary className="cursor-pointer">¿No puedes escanear? Escribe esta clave</summary>
            <code className="mt-2 block break-all rounded bg-black/40 p-2 font-mono text-sky-200 select-all">
              {data.secret}
            </code>
          </details>
        </div>
      )}
      <CodeField value={code} onChange={setCode} />
      {error && (
        <p role="alert" className="text-sm text-rose-300">
          {error.message}
        </p>
      )}
      <HudButton
        type="submit"
        variant="solid"
        className="w-full justify-center"
        disabled={!data || !looksLikeCode(code) || pending}
      >
        {pending ? 'Revisando…' : 'Confirmar y entrar'}
      </HudButton>
    </form>
  );
}
