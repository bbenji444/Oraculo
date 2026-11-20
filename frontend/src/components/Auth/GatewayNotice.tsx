/**
 * Aviso para quien abrió el monitor desde Oráculo y su llave no sirvió.
 *
 * Detrás del gateway de Oráculo (ADR-0119) la persona no tiene usuario ni
 * contraseña del monitor que escribir: Oráculo manda su llave en cada
 * petición. Si esa llave falta, venció o se renovó en el monitor sin
 * actualizarla en Oráculo, el formulario de entrada solo confundiría; el
 * aviso la manda con quien sí lo puede arreglar.
 *
 * No hace: no pide datos ni reintenta por su cuenta.
 */
import { HudPanel } from '../ui/HudPanel';

export function GatewayNotice() {
  return (
    <div className="relative z-10 flex h-full items-center justify-center px-4">
      <HudPanel scan className="w-full max-w-md space-y-3 px-6 py-7">
        <p className="mando-kicker">Oráculo · Monitor de Noticias</p>
        <h1 className="text-xl font-semibold text-slate-50">Tu acceso lo da Oráculo</h1>
        <p role="alert" className="text-sm text-slate-300">
          Oráculo no mandó una llave válida para el monitor. Pide al administrador de Oráculo que
          revise tu llave del monitor en tu usuario.
        </p>
        <p className="text-xs text-slate-400">
          Si te acaban de dar una llave nueva, recarga la página.
        </p>
      </HudPanel>
    </div>
  );
}
