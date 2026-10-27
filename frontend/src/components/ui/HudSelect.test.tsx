// @vitest-environment jsdom
/** Menú desplegable de la consola táctica: mouse, teclado y etiqueta. */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { HudSelect } from './HudSelect';

const OPTIONS = [
  { value: '', label: 'Todo México' },
  { value: '14', label: 'Jalisco' },
  { value: '16', label: 'Michoacán' },
  { value: '15', label: 'México' },
];

function Harness({ onChange }: { onChange?: (value: string) => void }) {
  const [value, setValue] = useState('');
  return (
    <>
      <label htmlFor="estado">Estado</label>
      <HudSelect
        id="estado"
        value={value}
        options={OPTIONS}
        onChange={(next) => {
          setValue(next);
          onChange?.(next);
        }}
      />
      <button type="button">afuera</button>
    </>
  );
}

afterEach(cleanup);

describe('HudSelect', () => {
  it('se enlaza con su etiqueta y muestra la opción elegida', () => {
    render(<Harness />);

    const field = screen.getByLabelText('Estado');
    expect(field.getAttribute('role')).toBe('combobox');
    expect(field.textContent).toBe('Todo México');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('con el mouse: abre, elige y se cierra', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    fireEvent.click(screen.getByRole('combobox', { name: 'Estado' }));
    expect(screen.getByRole('listbox')).toBeTruthy();
    expect(screen.getByRole('option', { name: 'Todo México' }).getAttribute('aria-selected')).toBe(
      'true',
    );
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Michoacán' }));

    expect(onChange).toHaveBeenCalledWith('16');
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(screen.getByRole('combobox', { name: 'Estado' }).textContent).toBe('Michoacán');
  });

  it('con el teclado: flechas, Enter y Escape', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const field = screen.getByRole('combobox', { name: 'Estado' });

    fireEvent.keyDown(field, { key: 'ArrowDown' });
    expect(field.getAttribute('aria-expanded')).toBe('true');
    fireEvent.keyDown(field, { key: 'ArrowDown' });
    fireEvent.keyDown(field, { key: 'ArrowDown' });
    const active = field.getAttribute('aria-activedescendant');
    expect(active && document.getElementById(active)?.textContent).toBe('Michoacán');
    fireEvent.keyDown(field, { key: 'Enter' });
    expect(onChange).toHaveBeenLastCalledWith('16');

    fireEvent.keyDown(field, { key: 'ArrowDown' });
    fireEvent.keyDown(field, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('si la lista se desplaza bajo el mouse quieto, manda el teclado', () => {
    // Pasó en el navegador (27/10/2026): con el mouse sobre la lista, escribir
    // «j» desplazaba la lista, otra opción quedaba bajo el cursor y Enter
    // elegía esa («Guerrero») en lugar de «Jalisco».
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const field = screen.getByRole('combobox', { name: 'Estado' });

    fireEvent.click(field);
    fireEvent.keyDown(field, { key: 'j' });
    // El navegador avisa que el mouse «entró» a otra opción sin que se moviera.
    fireEvent.mouseEnter(screen.getByRole('option', { name: 'México' }));
    fireEvent.mouseOver(screen.getByRole('option', { name: 'México' }));
    fireEvent.keyDown(field, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith('14');
  });

  it('mover el mouse sobre una opción sí la vuelve la activa', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const field = screen.getByRole('combobox', { name: 'Estado' });

    fireEvent.click(field);
    fireEvent.pointerMove(screen.getByRole('option', { name: 'México' }));
    fireEvent.keyDown(field, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith('15');
  });

  it('escribir salta a la opción que empieza así, sin importar acentos', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    fireEvent.keyDown(screen.getByRole('combobox', { name: 'Estado' }), { key: 'j' });

    expect(onChange).toHaveBeenCalledWith('14');
  });

  it('un clic fuera lo cierra sin cambiar nada', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    fireEvent.click(screen.getByRole('combobox', { name: 'Estado' }));
    fireEvent.pointerDown(screen.getByRole('button', { name: 'afuera' }));

    expect(screen.queryByRole('listbox')).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });
});
