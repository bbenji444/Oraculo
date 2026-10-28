// @vitest-environment jsdom
/** Calendario de la consola táctica: elegir, límites, cambiar de mes y borrar. */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { HudDatePicker } from './HudDatePicker';

afterEach(cleanup);

describe('HudDatePicker', () => {
  it('abre el mes de la fecha, elige un día y cierra', () => {
    const onChange = vi.fn();
    render(<HudDatePicker label="Desde" value="2026-10-20" onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: '20/10/2026' }));
    const calendar = screen.getByRole('dialog', { name: 'Elegir fecha: Desde' });
    expect(within(calendar).getByText('octubre de 2026')).toBeTruthy();
    expect(
      within(calendar)
        .getByRole('button', { name: '20 de octubre de 2026' })
        .getAttribute('aria-pressed'),
    ).toBe('true');

    fireEvent.click(within(calendar).getByRole('button', { name: '22 de octubre de 2026' }));
    expect(onChange).toHaveBeenCalledWith('2026-10-22');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('no deja elegir días fuera del rango y cambia de mes', () => {
    render(
      <HudDatePicker
        label="Hasta"
        value="2026-10-20"
        min="2026-10-10"
        max="2026-10-28"
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '20/10/2026' }));
    const calendar = screen.getByRole('dialog');

    expect(
      within(calendar).getByRole<HTMLButtonElement>('button', { name: '29 de octubre de 2026' })
        .disabled,
    ).toBe(true);
    expect(
      within(calendar).getByRole<HTMLButtonElement>('button', { name: '9 de octubre de 2026' })
        .disabled,
    ).toBe(true);

    fireEvent.click(within(calendar).getByRole('button', { name: 'Mes anterior' }));
    expect(within(calendar).getByText('septiembre de 2026')).toBeTruthy();
  });

  it('sin fecha muestra el formato y «Borrar» la quita', () => {
    const onChange = vi.fn();
    render(<HudDatePicker label="Desde" value={undefined} onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: 'dd/mm/aaaa' }));
    fireEvent.click(screen.getByRole('button', { name: 'Borrar' }));
    expect(onChange).toHaveBeenCalledWith(undefined);
  });
});
