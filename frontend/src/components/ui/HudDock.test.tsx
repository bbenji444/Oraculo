// @vitest-environment jsdom
/** El menú de secciones: nombre completo para el lector, corto a la vista. */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { HudDock, type HudDockItem } from './HudDock';

afterEach(cleanup);

const ITEMS: HudDockItem<'explorar' | 'estado'>[] = [
  { id: 'explorar', label: 'Explorar', short: 'Explorar', icon: 'public' },
  { id: 'estado', label: 'Estado del sistema', short: 'Estado', icon: 'monitor_heart' },
];

describe('HudDock', () => {
  it('cada sección es un enlace a su ruta con el nombre completo', () => {
    render(<HudDock items={ITEMS} active="explorar" label="Secciones" />);
    const nav = screen.getByRole('navigation', { name: 'Secciones' });
    const estado = within(nav).getByRole('link', { name: 'Estado del sistema' });
    expect(estado.getAttribute('href')).toBe('#/estado');
    // A la vista se lee el nombre corto, debajo del icono.
    expect(estado.textContent).toBe('Estado');
    expect(estado.querySelector('[data-icon]')?.getAttribute('data-icon')).toBe('monitor_heart');
  });

  it('«Salir» va al final y regresa a Oráculo (20/11/2026)', () => {
    render(
      <HudDock items={ITEMS} active="explorar" label="Secciones" exitHref="http://172.25.18.234" />,
    );
    const links = within(screen.getByRole('navigation')).getAllByRole('link');
    const exit = links[links.length - 1];
    expect(exit?.getAttribute('aria-label')).toBe('Salir a Oráculo');
    expect(exit?.getAttribute('href')).toBe('http://172.25.18.234');
    expect(exit?.textContent).toBe('Salir');
    expect(exit?.querySelector('[data-icon]')?.getAttribute('data-icon')).toBe('logout');
  });

  it('sin dirección de Oráculo no hay «Salir»', () => {
    render(<HudDock items={ITEMS} active="explorar" label="Secciones" exitHref={null} />);
    expect(screen.queryByRole('link', { name: 'Salir a Oráculo' })).toBeNull();
  });

  it('marca solo la sección activa', () => {
    render(<HudDock items={ITEMS} active="estado" label="Secciones" />);
    const current = screen.getByRole('link', { current: 'page' });
    expect(current.getAttribute('href')).toBe('#/estado');
    expect(screen.getByRole('link', { name: 'Explorar' }).getAttribute('aria-current')).toBeNull();
  });
});
