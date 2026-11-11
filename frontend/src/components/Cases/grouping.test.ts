import { describe, expect, it } from 'vitest';

import { entity, link } from '../../test/caseFixtures';
import {
  effectiveLegal,
  groupByType,
  linkEnds,
  participatesInEvent,
  relationshipKey,
  splitByStrength,
  touches,
} from './grouping';

describe('grupos por tipo', () => {
  it('ordena los grupos: quién y con qué antes que dónde', () => {
    const groups = groupByType([
      entity(1, 'place', 'Culiacán'),
      entity(2, 'vehicle', 'camioneta Ford'),
      entity(3, 'org', 'FGR'),
      entity(4, 'person', 'Juan'),
      entity(5, 'weapon', 'rifle'),
    ]);

    expect(groups.map((g) => g.label)).toEqual([
      'Personas',
      'Organizaciones',
      'Vehículos',
      'Lugares',
      // Un tipo nuevo del backend no se pierde: va al final con su etiqueta.
      'weapon',
    ]);
  });

  it('dentro del grupo, primero quien participa en el hecho y luego por estatus legal', () => {
    const [people] = groupByType([
      entity(1, 'person', 'Ana', { suggested: 'victim' }),
      entity(2, 'person', 'Beto', { roles: ['event'], suggested: 'witness' }),
      entity(3, 'person', 'Carlos', { roles: ['mentioned', 'event'], legal: 'detained' }),
      // Sin estatus cuenta como «mencionado»: va después de la víctima.
      entity(4, 'person', 'Dora'),
      entity(5, 'person', 'Elsa', { suggested: 'victim', articles: 3 }),
    ]);

    expect(people?.items.map((e) => e.label)).toEqual(['Carlos', 'Beto', 'Elsa', 'Ana', 'Dora']);
    expect(people?.inEvent).toBe(2);
  });

  it('en lo que no es persona desempata por notas y luego por nombre', () => {
    const [orgs] = groupByType([
      entity(1, 'org', 'Marina'),
      entity(2, 'org', 'Ejército', { articles: 2 }),
      entity(3, 'org', 'Cártel'),
    ]);

    expect(orgs?.items.map((e) => e.label)).toEqual(['Ejército', 'Cártel', 'Marina']);
  });

  it('sin entidades no hay grupos', () => {
    expect(groupByType([])).toEqual([]);
  });
});

describe('papel y estatus de una entidad', () => {
  it('participa en el hecho si alguna mención lo dice', () => {
    expect(participatesInEvent(entity(1, 'person', 'A', { roles: ['mentioned', 'event'] }))).toBe(
      true,
    );
    expect(participatesInEvent(entity(1, 'person', 'A'))).toBe(false);
  });

  it('el estatus confirmado gana sobre el sugerido', () => {
    expect(effectiveLegal({ legal_status: 'charged', suggested_legal_status: 'alleged' })).toBe(
      'charged',
    );
    expect(effectiveLegal({ legal_status: null, suggested_legal_status: 'alleged' })).toBe(
      'alleged',
    );
    expect(effectiveLegal({ legal_status: null, suggested_legal_status: null })).toBeNull();
  });
});

describe('fuerza de los vínculos', () => {
  it('parte en fuertes y débiles sin cambiar el orden', () => {
    const { strong, weak } = splitByStrength([
      link(1, 2, 'strong'),
      link(1, 3, 'weak'),
      link(2, 3, 'strong'),
    ]);

    expect(strong.map(relationshipKey)).toEqual(['1-2-appears_with', '2-3-appears_with']);
    expect(weak.map(relationshipKey)).toEqual(['1-3-appears_with']);
  });
});

describe('filtrar vínculos por entidad', () => {
  const links = [link(1, 2, 'strong'), link(2, 3, 'weak'), link(2, 4, 'weak'), link(3, 1, 'weak')];

  it('ofrece primero las entidades más conectadas', () => {
    expect(linkEnds(links)).toEqual([
      { id: 2, label: 'E2', links: 3 },
      { id: 1, label: 'E1', links: 2 },
      { id: 3, label: 'E3', links: 2 },
      { id: 4, label: 'E4', links: 1 },
    ]);
  });

  it('deja solo los vínculos de la entidad elegida, o todos sin elegir', () => {
    expect(links.filter((r) => touches(r, 4)).map(relationshipKey)).toEqual(['2-4-appears_with']);
    expect(links.filter((r) => touches(r, null))).toHaveLength(4);
  });
});
