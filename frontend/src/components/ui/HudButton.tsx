/**
 * Botón de la consola táctica (27/10/2026, styles/hud.css).
 *
 * Al pasar el mouse: se eleva, brilla, el texto se abre un poco y una franja
 * de luz lo cruza. Al presionar: se hunde y sale una onda desde el punto del
 * clic. Variantes:
 * - `outline` (por defecto): la mayoría de las acciones;
 * - `solid`: la acción principal de la pantalla (Buscar, Crear caso);
 * - `ghost`: secundarias (Ocultar, Cancelar);
 * - `danger`: eliminar.
 *
 * No hace: no decide qué pasa al hacer clic.
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type HudButtonVariant = 'outline' | 'solid' | 'ghost' | 'danger';

interface HudButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: HudButtonVariant;
  size?: 'md' | 'sm';
  /** Ícono al final (una flecha, por ejemplo): se adelanta al pasar el mouse. */
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

/** Flecha fina para botones y filas («Abrir en el globo →»). */
export function ArrowIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor">
      <path d="M2 8h11M9 4l4 4-4 4" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
