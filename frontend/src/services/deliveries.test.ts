/** Servicio de envíos (`/api/v1/deliveries`, ADR-0039). */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { daysLabel, scheduleProblem, weeklyCost } from '../components/Deliveries/schedule';
import { deliveryFieldErrors, saveRecipient, sendTest } from './deliveries';
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

const LIMITS = { max_runs_per_day: 8, min_gap_minutes: 60 };

describe('horario único de las corridas (ADR-0040)', () => {
  it('avisa los topes antes de guardar', () => {
    expect(scheduleProblem(['07:00', '15:00', '19:00', '23:00'], LIMITS)).toBeNull();
    expect(scheduleProblem([], LIMITS)).toBe('Agrega al menos una hora.');
    expect(scheduleProblem(['07:00', '07:30'], LIMITS)).toBe(
      'Entre 07:00 y 07:30 debe haber al menos 60 minutos.',
    );
    // La última y la primera del día siguiente también cuentan.
    expect(scheduleProblem(['00:10', '23:30'], LIMITS)).toBe(
      'Entre 23:30 y 00:10 debe haber al menos 60 minutos.',
    );
    const nine = ['00:00', '02:40', '05:20', '08:00', '10:40', '13:20', '16:00', '18:40', '21:20'];
    expect(scheduleProblem(nine, LIMITS)).toMatch(/^Máximo 8 horas/);
  });

  it('calcula lo que cuesta a la semana', () => {
    expect(weeklyCost(['07:00', '15:00', '23:00'], [], 0.04)).toBeCloseTo(0.84);
    expect(weeklyCost(['07:00'], [1, 2, 3, 4, 5], 0.04)).toBeCloseTo(0.2);
    expect(weeklyCost(['07:00'], [], null)).toBeNull();
  });
});
