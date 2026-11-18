/**
 * Icono de Material Icons, la letra de iconos de Oráculo core (ADR-0108).
 *
 * La letra convierte el nombre (`close`, `chevron_right`…) en el dibujo. El
 * nombre va en `data-icon` y lo escribe el CSS (`.hud-icon::before`), no el
 * texto de la página: así no aparece al copiar, al buscar con Ctrl+F ni en el
 * texto de los botones. Va oculto para el lector de pantalla: el botón o
 * enlace que lo lleva ya se nombra con su texto o con `aria-label`.
 *
 * Mide 1.25 veces el texto de al lado (`.hud-icon` en hud.css); para otro
 * tamaño se pasa una clase `text-*`.
 *
 * No hace: no carga la letra (eso es `@font-face` en `styles/index.css`).
 */

/**
 * Los iconos que usa el monitor. Van en una lista cerrada para que un error
 * de dedo no deje una palabra suelta en pantalla («chevron_rigth»). Para
 * agregar uno, se busca su nombre en https://fonts.google.com/icons (estilo
 * «Material Icons»).
 */
export type IconName =
  | 'account_circle'
  | 'arrow_forward'
  | 'calendar_today'
  | 'check'
  | 'chevron_left'
  | 'chevron_right'
  | 'close'
  | 'dark_mode'
  | 'expand_less'
  | 'expand_more'
  | 'filter_alt'
  | 'key'
  | 'light_mode'
  | 'list'
  | 'open_in_new'
  | 'power_settings_new'
  | 'radar'
  | 'search'
  | 'tune'
  | 'warning';

interface IconProps {
  name: IconName;
  /** Clases extra: tamaño (`text-lg`), color, giro… */
  className?: string;
}

export function Icon({ name, className }: IconProps) {
  return (
    <span
      aria-hidden="true"
      data-icon={name}
      className={className ? `hud-icon ${className}` : 'hud-icon'}
    />
  );
}
