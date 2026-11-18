/**
 * Botón de la consola táctica (27/10/2026, styles/hud.css).
 *
 * Tiene la forma del botón de Oráculo core (ADR-0108): tinte cian sin borde y
 * rótulo de consola; al pasar el mouse y al presionar, el tinte sube.
 * Variantes:
 * - `outline` (por defecto): la mayoría de las acciones;
 * - `solid`: la acción principal de la pantalla (Buscar, Crear caso), con el
 *   tinte más alto;
 * - `ghost`: secundarias (Ocultar, Cancelar), en gris;
 * - `danger`: eliminar, en rojo.
 *
 * No hace: no decide qué pasa al hacer clic.
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Icon } from './Icon';

export type HudButtonVariant = 'outline' | 'solid' | 'ghost' | 'danger';

interface HudButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: HudButtonVariant;
  size?: 'md' | 'sm';
  /** Ícono al final (una flecha, por ejemplo). */
  icon?: ReactNode;
}

const VARIANT_CLASS: Record<HudButtonVariant, string> = {
  outline: '',
  solid: 'hud-btn--solid',
  ghost: 'hud-btn--ghost',
  danger: 'hud-btn--danger',
};

export function HudButton({
  children,
  variant = 'outline',
  size = 'md',
  icon,
  className = '',
  type = 'button',
  ...rest
}: HudButtonProps) {
  const classes = ['hud-btn', VARIANT_CLASS[variant], size === 'sm' ? 'hud-btn--sm' : '', className]
    .filter(Boolean)
    .join(' ');
  return (
    <button type={type} className={classes} {...rest}>
      <span>{children}</span>
      {icon && (
        <span aria-hidden="true" className="hud-btn-icon">
          {icon}
        </span>
      )}
    </button>
  );
}

/** Flecha para botones y filas («Abrir en el globo →»), de Material Icons. */
export function ArrowIcon() {
  return <Icon name="arrow_forward" />;
}
