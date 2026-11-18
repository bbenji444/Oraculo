/** Qué dice el chip «Estado del sistema» según la respuesta de /health. */
import { describe, expect, it } from 'vitest';

import type { SystemHealth } from '../../services/health';
import { statusChipOf } from './chipState';

const health = (status: SystemHealth['status']): SystemHealth => ({ status, components: [] });

describe('statusChipOf', () => {
  it('en verde y «en línea» cuando todo funciona', () => {
    expect(statusChipOf({ data: health('ok'), error: null })).toEqual({
      state: 'ok',
      label: 'Estado del sistema: en línea',
    });
  });

  it('en ámbar cuando algún servicio falla', () => {
    expect(statusChipOf({ data: health('degraded'), error: null }).state).toBe('degraded');
  });

  it('en rojo cuando la API no responde', () => {
    expect(statusChipOf({ data: undefined, error: new Error('sin red') })).toEqual({
      state: 'down',
      label: 'Estado del sistema: sin conexión',
    });
  });

  it('en rojo si la API se cae después de haber respondido bien', () => {
    expect(statusChipOf({ data: health('ok'), error: new Error('sin red') }).state).toBe('down');
  });

  it('mientras consulta por primera vez, apagado', () => {
    expect(statusChipOf({ data: undefined, error: null }).state).toBe('checking');
  });
});
