import { describe, expect, it } from 'vitest';

import type { AuditEvent } from '../../services/access';
import { AUDIT_GROUPS, describeAudit } from './auditText';

const PEOPLE = [
  { id: 1, username: 'benji', display_name: 'Benjamín' },
  { id: 2, username: 'pepe', display_name: 'Pepe López' },
];

function event(
  action: string,
  details: Record<string, unknown> = {},
  more: Partial<AuditEvent> = {},
): AuditEvent {
  return {
    id: 1,
    created_at: '2026-11-11T18:00:00Z',
    actor: 'benji',
    actor_name: 'Benjamín',
    action,
    entity_type: action.split('.')[0] ?? '',
    entity_id: '2',
    details,
    ip: '10.244.0.7',
    ...more,
  };
}

describe('frases de la bitácora', () => {
  it('dice quién vio la llave de quién, con la llave enmascarada y resaltada', () => {
    const line = describeAudit(
      event('access_key.revealed', { de: 'pepe', llave: 'orc_live_a1b2c3d4…' }),
      PEOPLE,
    );

    expect(line.text).toBe('Benjamín vio la llave de API de Pepe López');
    expect(line.extra).toBe('orc_live_a1b2c3d4…');
    expect(line.group).toBe('access');
    expect(line.alert).toBe(true);
  });

  it('distingue la llave de API de una llave de sistema', () => {
    expect(
      describeAudit(event('access_key.created', { para: 'pepe', etiqueta: 'Llave de API' }), PEOPLE)
        .text,
    ).toBe('Benjamín generó la llave de API de Pepe López');
    expect(
      describeAudit(event('access_key.created', { para: 'pepe', etiqueta: 'Laptop' }), PEOPLE).text,
    ).toBe('Benjamín creó una llave de sistema para Pepe López');
  });

  it('las entradas fallidas se resaltan y dicen el motivo', () => {
    const line = describeAudit(
      event('auth.login_failed', { motivo: 'contraseña' }, { actor: 'anonimo', actor_name: null }),
      PEOPLE,
    );

    expect(line).toMatchObject({ text: 'Entrada fallida', extra: 'contraseña', alert: true });
  });

  it('nombra a quien no es persona y a la persona editada por su id', () => {
    expect(
      describeAudit(
        event('user.password_reset', { username: 'pepe' }, { actor: 'consola', actor_name: null }),
        PEOPLE,
      ).text,
    ).toBe('La consola del servidor restableció la contraseña de Pepe López');
    expect(
      describeAudit(event('user.updated', { changes: { is_active: false } }), PEOPLE).text,
    ).toBe('Benjamín editó a Pepe López');
  });

  it('casos, conceptos y vínculos usan su nombre', () => {
    expect(describeAudit(event('case.created', { after: { name: 'Fosa SLP' } }), PEOPLE).text).toBe(
      'Benjamín creó el caso «Fosa SLP»',
    );
    expect(describeAudit(event('case.viewed'), PEOPLE).text).toBe('Benjamín abrió un caso');
    expect(
      describeAudit(event('concept.deleted', { before: { name: 'Secuestro' } }), PEOPLE).text,
    ).toBe('Benjamín borró el concepto «Secuestro»');
    expect(
      describeAudit(
        event('relationship.confirmed', {
          entity_a: { label: 'FGR' },
          entity_b: { label: 'Sinaloa' },
        }),
        PEOPLE,
      ).text,
    ).toBe('Benjamín confirmó un vínculo entre «FGR» y «Sinaloa»');
  });

  it('una acción que no conoce se muestra tal cual, sin romperse', () => {
    const line = describeAudit(event('algo.nuevo'), PEOPLE);

    expect(line).toMatchObject({ text: 'Benjamín: algo.nuevo', group: 'other', alert: false });
  });

  it('el filtro trae «Todo» primero', () => {
    expect(AUDIT_GROUPS[0]).toEqual({ value: 'all', label: 'Todo' });
  });
});
