/**
 * Switches de fuentes del panel de búsqueda (F12.2, ADR-0027): el analista
 * enciende o apaga Google News, el índice local, SearchApi y, desde F12.3,
 * BrowserWork. Cada switch dice si la fuente es gratis o gasta créditos (y si
 * tarda más, como BrowserWork, que abre un navegador real); las
 * que no están configuradas en el servidor se ven apagadas y deshabilitadas.
 * Si el servidor sabe cuántos créditos le quedan a una de pago
 * (`credits_remaining`, ADR-0115), lo dice al lado: «Gasta créditos · quedan
 * 46», o «Sin créditos» si ya no hay.
 *
 * No hace: no pide datos (los recibe) ni calcula costos (la estimación se
 * recalcula sola porque la elección forma parte de la búsqueda).
 */
import type { SourceOption } from '../../services/sources';

/** Lo que dice una fuente de pago: con o sin saldo conocido. */
function paidNote(option: SourceOption): string {
  const left = option.credits_remaining;
  if (left === undefined || left === null) return 'Gasta créditos';
  // Sin saldo el servidor ya la apaga (default_on); aquí solo se dice por qué.
  if (left === 0) return 'Sin créditos';
  return `Gasta créditos · ${left === 1 ? 'queda 1' : `quedan ${left.toLocaleString('es-MX')}`}`;
}

/**
 * Texto chico bajo el nombre de la fuente.
 *
 * @param option La fuente como la manda `/sources`.
 * @returns «Gratis», «Gasta créditos» (con «· quedan N» si se sabe),
 *   «Sin créditos», «Gratis · tarda más» o «No configurada».
 */
function sourceNote(option: SourceOption): string {
  if (!option.configured) return 'No configurada';
  const cost = option.paid ? paidNote(option) : 'Gratis';
  // BrowserWork abre un Chrome real: tarda minutos y puede pedir captcha (ADR-0028).
  return option.slow ? `${cost} · tarda más` : cost;
}

interface SourceSwitchesProps {
  options: readonly SourceOption[];
  /** Las encendidas (ya resueltas con `chosenSources`). */
  chosen: readonly string[];
  /** Recibe la lista completa de encendidas después del cambio. */
  onChange: (chosen: string[]) => void;
}

export function SourceSwitches({ options, chosen, onChange }: SourceSwitchesProps) {
  const toggle = (id: string) => {
    onChange(chosen.includes(id) ? chosen.filter((c) => c !== id) : [...chosen, id]);
  };
  return (
    <fieldset className="space-y-1.5">
      <legend className="hud-label">Fuentes</legend>
      {options.map((option) => {
        const on = option.configured && chosen.includes(option.id);
        return (
          <button
            key={option.id}
            type="button"
            role="switch"
            aria-checked={on}
            disabled={!option.configured}
            title={option.configured ? undefined : 'No está configurada en el servidor'}
            onClick={() => {
              toggle(option.id);
            }}
            className="hud-row w-full justify-between gap-2 py-2 pr-2.5 pl-3 text-left text-xs focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className="min-w-0">
              <span className="block truncate text-slate-100">{option.label}</span>
              <span
                className={`text-[11px] ${option.paid ? 'text-amber-200/80' : 'text-slate-400'}`}
              >
                {sourceNote(option)}
              </span>
            </span>
            {/* Solo la imagen del interruptor: el botón entero ya es el switch. */}
            <span aria-hidden="true" data-on={on} className="hud-switch" />
          </button>
        );
      })}
    </fieldset>
  );
}
