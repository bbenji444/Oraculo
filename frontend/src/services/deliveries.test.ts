/** Servicio de envíos (`/api/v1/deliveries`, ADR-0039). */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { hoursLabel } from '../components/Deliveries/labels';
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

  it('dice las horas de una regla como se leen', () => {
    expect(hoursLabel([], [7, 15, 23])).toBe('Todas las corridas');
    expect(hoursLabel([7, 15], [7, 15, 23])).toBe('07:00 y 15:00');
    expect(hoursLabel([23], [7, 15, 23])).toBe('23:00');
  });
});
