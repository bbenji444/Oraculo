/**
 * Interruptor encendido/apagado (27/10/2026): la perilla viaja y se enciende
 * en cian, como el interruptor de Oráculo core (styles/hud.css,
 * `.hud-switch`; ADR-0108).
 *
 * No hace: no guarda el estado (lo recibe y avisa con `onChange`).
 */
interface HudSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Qué enciende, para el lector de pantalla. */
  label: string;
  disabled?: boolean;
}

export function HudSwitch({ checked, onChange, label, disabled = false }: HudSwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className="hud-switch disabled:cursor-not-allowed disabled:opacity-40"
      onClick={() => {
        onChange(!checked);
      }}
    />
  );
}
