/**
 * Menú de secciones con la forma del dock de Oráculo core (ADR-0108).
 *
 * En pantallas anchas es una barra vertical y compacta a la izquierda, con
 * el icono de cada sección y su nombre chiquito debajo (Benji, 17/11/2026:
 * así lo pidió su jefe, como en el Hub de Oráculo). En celular se queda en
 * el encabezado como una fila que se desliza: abajo chocaría con la consola
 * de Explorar. La forma la da `.hud-dock` en `hud.css`.
 *
 * Cada sección es un enlace con su `#/ruta`, para compartirla o recargar sin
 * perderla. El nombre accesible es el completo («Estado del sistema») aunque
 * en la barra se lea el corto («Estado»).
 *
 * Con `exitHref`, al final va «Salir», que regresa a Oráculo (Benji,
 * 20/11/2026: «para que sea más claro que es regresar a la pestaña de
 * atrás»), con el mismo icono que la barra de Oráculo.
 *
 * No hace: no cambia de pantalla (eso lo hace App con el cambio de `#`).
 */
import { Icon, type IconName } from './Icon';

export interface HudDockItem<T extends string> {
  id: T;
  /** Nombre completo: el que oye el lector de pantalla y sale al pasar el mouse. */
  label: string;
  /** Nombre que cabe debajo del icono. */
  short: string;
  icon: IconName;
}

interface HudDockProps<T extends string> {
  items: readonly HudDockItem<T>[];
  active: T;
  /** Nombre de la navegación, para el lector de pantalla. */
  label: string;
  /** A dónde lleva «Salir» (Oráculo); sin valor no se muestra. */
  exitHref?: string | null;
}

export function HudDock<T extends string>({ items, active, label, exitHref }: HudDockProps<T>) {
  return (
    <nav aria-label={label} className="hud-dock sin-barra">
      {items.map((item) => (
        <a
          key={item.id}
          href={`#/${item.id}`}
          aria-label={item.label}
          title={item.label}
          aria-current={item.id === active ? 'page' : undefined}
          className="hud-dock-link focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          <span className="hud-dock-icon">
            <Icon name={item.icon} />
          </span>
          <span className="hud-dock-label">{item.short}</span>
        </a>
      ))}
      {exitHref && (
        <a
          href={exitHref}
          aria-label="Salir a Oráculo"
          title="Salir a Oráculo"
          className="hud-dock-link hud-dock-exit focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          <span className="hud-dock-icon">
            <Icon name="logout" />
          </span>
          <span className="hud-dock-label">Salir</span>
        </a>
      )}
    </nav>
  );
}
