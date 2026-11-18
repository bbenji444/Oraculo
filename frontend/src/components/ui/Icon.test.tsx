// @vitest-environment jsdom
/** El icono se dibuja con la letra y no se mete en el texto ni en el nombre del botón. */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Icon } from './Icon';

afterEach(cleanup);

describe('Icon', () => {
  it('lleva el nombre en data-icon, sin texto y oculto al lector de pantalla', () => {
    const { container } = render(<Icon name="close" />);
    const icon = container.querySelector('span');
    expect(icon?.dataset.icon).toBe('close');
    expect(icon?.textContent).toBe('');
    expect(icon?.getAttribute('aria-hidden')).toBe('true');
    expect(icon?.className).toBe('hud-icon');
  });

  it('suma las clases extra', () => {
    const { container } = render(<Icon name="check" className="text-lg" />);
    expect(container.querySelector('span')?.className).toBe('hud-icon text-lg');
  });

  it('el botón se sigue llamando y leyendo solo por su texto', () => {
    render(
      <button type="button">
        <Icon name="list" /> Lista
      </button>,
    );
    const button = screen.getByRole('button', { name: 'Lista' });
    expect(button.textContent.trim()).toBe('Lista');
  });
});
