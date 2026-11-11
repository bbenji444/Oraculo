/**
 * Interruptor «Pedir código al entrar» de «Accesos» (ADR-0047).
 *
 * Benji, 11/11/2026: «dice mi jefe que es tedioso»; que el superusuario lo
 * prenda o apague desde el panel. Apagado, se entra solo con usuario y
 * contraseña. Prendido, se vuelve a pedir el código de Microsoft
 * Authenticator (quien ya lo conectó usa el mismo; quien no, lo conecta al
 * entrar). Aplica desde el siguiente ingreso: las sesiones abiertas siguen.
 *
 * No hace: no cierra sesiones.
 */
import { useAuthSettings, useSaveAuthSettings } from '../../hooks/useAccess';
import { HudPanel } from '../ui/HudPanel';
import { HudSwitch } from '../ui/HudSwitch';

export function LoginSettings() {
  const settings = useAuthSettings();
  const save = useSaveAuthSettings();
  const required = settings.data?.totp_required ?? false;

  return (
    <HudPanel className="mt-6 flex flex-wrap items-center justify-between gap-4 px-5 py-4">
      <div className="min-w-0 flex-1 basis-64">
        <p className="font-medium text-slate-50">
          Pedir código de Microsoft Authenticator al entrar
        </p>
        <p className="mt-0.5 text-xs text-slate-400">
          {required
            ? 'Prendido: se entra con usuario, contraseña y el código de 6 dígitos.'
            : 'Apagado: se entra solo con usuario y contraseña.'}{' '}
          Aplica desde el siguiente ingreso.
        </p>
        {save.error && (
          <p role="alert" className="mt-1 text-xs text-rose-300">
            {save.error.message}
          </p>
        )}
      </div>
      <HudSwitch
        checked={required}
        disabled={!settings.data || save.isPending}
        label="Pedir código al entrar"
        onChange={(next) => {
          save.mutate(next);
        }}
      />
    </HudPanel>
  );
}
