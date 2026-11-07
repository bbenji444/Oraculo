/** Servicio de envíos (`/api/v1/deliveries`, ADR-0039). */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { daysLabel, ruleTargets, upcomingSends } from '../components/Deliveries/schedule';
import {
  deliveryFieldErrors,
  type Recipient,
  type Rule,
  saveRecipient,
  sendTest,
} from './deliveries';
import { ApiError } from './http';

function respond(body: unknown, status = 200) {
  const spy = vi.fn<typeof fetch>(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('servicio de envíos', () => {
  it('crea con POST y edita con PUT', async () => {
    const recipient = { id: 1, name: 'Benjamin', email: 'b@x.mx', phone: null, is_active: true };
    const spy = respond(recipient);

    await saveRecipient({ name: 'Benjamin', email: 'b@x.mx', phone: null, is_active: true });
    await saveRecipient({ name: 'Benjamin', email: 'b@x.mx', phone: null, is_active: false }, 1);

    expect(spy.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/deliveries/recipients', 'POST'],
      ['/api/v1/deliveries/recipients/1', 'PUT'],
    ]);
  });

  it('manda la prueba con destinatario y cuenta', async () => {
    const spy = respond({ id: 'd1', status: 'sent' });

    const result = await sendTest(1, 2);

    expect(result.status).toBe('sent');
    const [, init] = spy.mock.calls[0] ?? [];
    expect(JSON.parse(init?.body as string)).toEqual({ recipient_id: 1, account_id: 2 });
  });

  it('traduce los problemas de validación por campo', () => {
    const error = new ApiError('El destinatario no es válido.', 'invalid_delivery', {
      problemas: [
        { campo: 'email', mensaje: 'Ese correo no parece válido.' },
        { campo: 'name', mensaje: 'Escribe el nombre.' },
      ],
    });

    expect(deliveryFieldErrors(error)).toEqual({
      email: ['Ese correo no parece válido.'],
      name: ['Escribe el nombre.'],
    });
    expect(deliveryFieldErrors(new Error('otro'))).toEqual({});
  });

  it('dice los días como se leen', () => {
    expect(daysLabel([])).toBe('todos los días');
    expect(daysLabel([1, 2, 3, 4, 5])).toBe('de lunes a viernes');
    expect(daysLabel([6])).toBe('los sábados');
    expect(daysLabel([1, 3])).toBe('lunes y miércoles');
  });
});

const PEOPLE: Recipient[] = [
  { id: 1, name: 'Benjamin', email: 'b@x.mx', phone: null, is_active: true },
  { id: 2, name: 'Geovanni', email: 'g@x.mx', phone: null, is_active: true },
  { id: 3, name: 'Tadeo', email: 't@x.mx', phone: null, is_active: false },
];

function rule(overrides: Partial<Rule>): Rule {
  return {
    id: 1,
    source: 'monitor.corrida_fgr',
    name: 'Regla general',
    audience: 'all',
    recipient_ids: [],
    exclude_ids: [],
    channel: 'email',
    account_id: 1,
    times: ['07:00', '15:00', '23:00'],
    days: [],
    is_active: true,
    ...overrides,
  };
}

describe('programación de envíos', () => {
  it('a todos menos las excepciones, o solo a los elegidos', () => {
    expect(ruleTargets(rule({ exclude_ids: [2] }), PEOPLE).map((r) => r.name)).toEqual([
      'Benjamin',
    ]);
    expect(
      ruleTargets(rule({ audience: 'selected', recipient_ids: [2, 3] }), PEOPLE).map((r) => r.name),
    ).toEqual(['Geovanni']);
  });

  it('calcula los próximos envíos en hora de la Ciudad de México', () => {
    // Viernes 6/11/2026 a las 21:00 de la CDMX (03:00 UTC del sábado).
    const now = new Date('2026-11-07T03:00:00Z');
    const sends = upcomingSends(
      [
        rule({}),
        rule({
          id: 2,
          name: 'Fin de semana',
          audience: 'selected',
          recipient_ids: [1],
          times: ['09:30'],
          days: [6],
        }),
      ],
      PEOPLE,
      now,
      3,
    );

    expect(sends.map((s) => [s.at.toISOString(), s.rule.name, s.recipients])).toEqual([
      ['2026-11-07T05:00:00.000Z', 'Regla general', 2],
      ['2026-11-07T13:00:00.000Z', 'Regla general', 2],
      ['2026-11-07T15:30:00.000Z', 'Fin de semana', 1],
    ]);
  });

  it('una regla apagada no aparece', () => {
    expect(upcomingSends([rule({ is_active: false })], PEOPLE, new Date(), 5)).toEqual([]);
  });
});
