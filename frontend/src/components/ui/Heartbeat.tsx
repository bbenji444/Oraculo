/**
 * Línea de latido (27/10/2026): una línea tenue y un pulso de luz que la
 * recorre, como un monitor de signos vitales. Dice «esto está vivo» en los
 * servicios de Estado del sistema. En rojo y plana cuando algo falla.
 *
 * No hace: no mide nada (es la imagen de un estado que ya se conoce).
 */

// Trazo de latido: plano, un pico y plano otra vez (160 × 28).
const BEAT = 'M0 14h48l6-9 8 18 7-14 5 5h86';
// Sin latido: una línea plana.
const FLAT = 'M0 14h160';
// Verde «funciona» y rojo «falla» de Oráculo core (--hud-green y --hud-rose de
// hud.css; un atributo de SVG no lee variables CSS).
const OK_COLOR = '#00ff9d';
const FAIL_COLOR = '#ff3333';

interface HeartbeatProps {
  ok: boolean;
  /** Retraso del pulso, para que varias tarjetas no laten al mismo tiempo. */
  delaySeconds?: number;
  className?: string;
}

export function Heartbeat({ ok, delaySeconds = 0, className = '' }: HeartbeatProps) {
  const color = ok ? OK_COLOR : FAIL_COLOR;
  const path = ok ? BEAT : FLAT;
  return (
    <svg
      viewBox="0 0 160 28"
      preserveAspectRatio="none"
      className={`h-7 w-full ${className}`}
      aria-hidden="true"
    >
      <path d={path} fill="none" stroke={color} strokeOpacity="0.2" strokeWidth="1.2" />
      {ok && (
        <path
          d={path}
          fill="none"
          stroke={color}
          strokeWidth="1.6"
          strokeLinecap="round"
          pathLength={100}
          className="hud-pulse-line"
          style={{ animationDelay: `${String(delaySeconds)}s` }}
        />
      )}
    </svg>
  );
}
