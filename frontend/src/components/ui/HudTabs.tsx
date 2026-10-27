/**
 * Pestañas del encabezado con una barra de luz que se desliza (27/10/2026).
 *
 * La barra se va a la pestaña elegida y, mientras el mouse pasa por otra, la
 * sigue; al salir regresa. Los nombres se descifran al pasar el mouse
 * (`DecodeText`). Las pestañas son enlaces con su `#/ruta`, para que se pueda
 * compartir o recargar sin perderla.
 *
 * No hace: no cambia de pantalla (eso lo hace App con el cambio de `#`).
 */
import { type CSSProperties, useLayoutEffect, useRef, useState } from 'react';

import { DecodeText } from './DecodeText';

export interface HudTab<T extends string> {
  id: T;
  label: string;
}

interface HudTabsProps<T extends string> {
  tabs: readonly HudTab<T>[];
  active: T;
  /** Nombre de la navegación, para el lector de pantalla. */
  label: string;
}

interface Bar {
  x: number;
  w: number;
}

export function HudTabs<T extends string>({ tabs, active, label }: HudTabsProps<T>) {
  const navRef = useRef<HTMLElement>(null);
  const [hovered, setHovered] = useState<T | null>(null);
  const [bar, setBar] = useState<Bar>({ x: 0, w: 0 });
  const target = hovered ?? active;

  // Se mide antes de pintar para que la barra no aparezca en el lugar viejo.
  useLayoutEffect(() => {
    const nav = navRef.current;
    const link = nav?.querySelector<HTMLElement>(`[data-tab="${target}"]`);
    if (!nav || !link) return;
    const measure = () => {
      setBar({ x: link.offsetLeft, w: link.offsetWidth });
    };
    measure();
    // Orbitron llega después del primer dibujo y cambia el ancho de cada
    // pestaña: al cargar las fuentes se vuelve a medir.
    let alive = true;
    // (jsdom, el navegador de las pruebas, no tiene document.fonts).
    if ('fonts' in document) {
      void document.fonts.ready.then(() => {
        if (alive) measure();
      });
    }
    // Sin ResizeObserver (navegadores viejos, pruebas) basta el cambio de ventana.
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(nav);
    window.addEventListener('resize', measure);
    return () => {
      alive = false;
      observer?.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [target, tabs]);

  const style = {
    '--tab-x': `${String(bar.x)}px`,
    '--tab-w': `${String(bar.w)}px`,
  } as CSSProperties;
  return (
    <nav
      ref={navRef}
      aria-label={label}
      className="hud-tabs sin-barra max-w-full min-w-0 overflow-x-auto"
      style={style}
      onMouseLeave={() => {
        setHovered(null);
      }}
    >
      {tabs.map((tab) => (
        <a
          key={tab.id}
          data-tab={tab.id}
          href={`#/${tab.id}`}
          aria-current={tab.id === active ? 'page' : undefined}
          className="hud-tab shrink-0 focus-visible:outline-2 focus-visible:outline-sky-400"
          onMouseEnter={() => {
            setHovered(tab.id);
          }}
          onFocus={() => {
            setHovered(tab.id);
          }}
          onBlur={() => {
            setHovered(null);
          }}
        >
          <DecodeText text={tab.label} />
        </a>
      ))}
      <span aria-hidden="true" className="hud-tabs-bar" />
    </nav>
  );
}
