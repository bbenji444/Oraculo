/**
 * Aviso «Acceso denegado» para quien llega al monitor sin una llave válida.
 *
 * Sin entrada con contraseña (ADR-0121) solo se entra por Oráculo, que manda
 * la llave de la persona en cada petición. Este aviso sale si se abre el
 * monitor directo (sin Oráculo), si la sesión de Oráculo terminó o si la
 * llave falta, venció o se renovó sin actualizarla en Oráculo. Benji,
 * 20/11/2026: «Acceso denegado, favor de iniciar sesión»; después, «que solo
 * diga acceso denegado, sesión inválida».
 *
 * No hace: no pide datos ni reintenta por su cuenta.
 */
import { useAppConfig } from '../../hooks/useAppConfig';
import { safeOraculoUrl } from '../../services/appConfig';
import { HudPanel } from '../ui/HudPanel';

export function GatewayNotice() {
  const oraculo = safeOraculoUrl(useAppConfig().data?.oraculo_url ?? null);
  return (
    <div className="relative z-10 flex h-full items-center justify-center px-4">
      <HudPanel scan className="w-full max-w-md space-y-3 px-6 py-7">
        <p className="mando-kicker">Oráculo · Monitor de Noticias</p>
        <h1 className="text-xl font-semibold text-slate-50">Acceso denegado</h1>
        <p role="alert" className="text-sm text-slate-300">
          Sesión inválida. Favor de iniciar sesión en Oráculo.
        </p>
        {oraculo && (
          <a className="hud-btn inline-block" href={oraculo}>
            Ir a Oráculo
          </a>
        )}
      </HudPanel>
    </div>
  );
}
