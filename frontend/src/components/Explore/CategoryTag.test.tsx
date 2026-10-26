// @vitest-environment jsdom
/** Etiqueta de la categoría de una nota (F12.4, ADR-0029). */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { CategoryTag } from './CategoryTag';

afterEach(() => {
  cleanup();
});

const HUACHICOL = {
  id: 7,
  name: 'Huachicol y delitos contra hidrocarburos',
  color: null,
  symbol: null,
};

describe('CategoryTag', () => {
  it('muestra la categoría y la etiqueta libre de la IA al pasar el mouse', () => {
    render(<CategoryTag article={{ category: HUACHICOL, category_raw: 'robo de combustible' }} />);

    const tag = screen.getByText('Huachicol y delitos contra hidrocarburos');
    expect(tag.getAttribute('title')).toBe('Categoría de la IA · «robo de combustible»');
  });

  it('sin etiqueta libre, el aviso no muestra comillas vacías', () => {
    render(<CategoryTag article={{ category: HUACHICOL, category_raw: null }} />);

    expect(screen.getByText(HUACHICOL.name).getAttribute('title')).toBe('Categoría de la IA');
  });

  it('una nota sin clasificar no muestra nada', () => {
    const { container } = render(<CategoryTag article={{ category: null }} />);

    expect(container.textContent).toBe('');
  });
});
