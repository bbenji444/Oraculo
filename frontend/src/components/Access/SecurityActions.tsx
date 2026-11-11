/**
 * Acciones de seguridad sobre una persona en «Accesos» (ADR-0043):
 *
 * - «Restablecer contraseña»: olvidó la suya; recibe una temporal nueva y sus
 *   sesiones se cierran. Su Authenticator sigue igual.
 * - «Reiniciar autenticador»: cambió o perdió el celular; al entrar escanea
 *   un QR nuevo. También cierra sus sesiones.
 *
 * Las dos piden confirmación en el mismo lugar.
 *
 * No hace: no muestra la contraseña nueva (eso es de `TemporaryPasswordNotice`).
 */
import { useResetPassword, useResetTotp } from '../../hooks/useAccess';
import type { AccessUser } from '../../services/access';
import { ConfirmDelete } from '../ConfirmDelete';

interface SecurityActionsProps {
  user: AccessUser;
  onTemporaryPassword: (password: string) => void;
}

export function SecurityActions({ user, onTemporaryPassword }: SecurityActionsProps) {
  const resetPassword = useResetPassword();
  const resetTotp = useResetTotp();

  return (
    <section className="space-y-3 border-t border-white/10 pt-4" aria-label="Seguridad">
      <h3 className="mando-kicker">Seguridad</h3>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm text-slate-300">¿Olvidó su contraseña?</span>
        <ConfirmDelete
          what={`la contraseña de ${user.display_name}`}
          label="Restablecer contraseña"
          verb="restablecer"
          busy={resetPassword.isPending}
          onConfirm={() => {
            resetPassword.mutate(user.id, { onSuccess: onTemporaryPassword });
          }}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm text-slate-300">
          {user.totp_enrolled ? '¿Cambió de celular?' : 'Aún no conecta Microsoft Authenticator.'}
        </span>
        {user.totp_enrolled && (
          <ConfirmDelete
            what={`el autenticador de ${user.display_name}`}
            label="Reiniciar autenticador"
            verb="reiniciar"
            busy={resetTotp.isPending}
            onConfirm={() => {
              resetTotp.mutate(user.id);
            }}
          />
        )}
      </div>
      {resetTotp.isSuccess && (
        <p className="text-xs text-emerald-300">Listo: al entrar escaneará un código QR nuevo.</p>
      )}
      {(resetPassword.error ?? resetTotp.error) && (
        <p role="alert" className="text-xs text-rose-300">
          {(resetPassword.error ?? resetTotp.error)?.message}
        </p>
      )}
    </section>
  );
}
