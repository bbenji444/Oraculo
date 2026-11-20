/**
 * Configuración pública del servidor (`/api/v1/app-config`).
 *
 * Trae la dirección del sistema principal de Oráculo, para el botón del
 * encabezado que regresa a él, y si la pantalla se abrió por el gateway de
 * Oráculo (ADR-0119). Nunca trae llaves.
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2).
 */
import { apiUrl } from '../config/api';
import { badFormat, requestJson } from './http';

export interface AppConfig {
  /** Sistema principal de Oráculo; `null` = sin botón para regresar. */
  oraculo_url: string | null;
  /**
   * La pantalla se abrió por el gateway de Oráculo (`/m/noticias/`): el
   * acceso lo da Oráculo, así que no se pide usuario ni contraseña.
   */
  via_gateway: boolean;
}

/** Lee la configuración pública. */
export async function getAppConfig(signal?: AbortSignal): Promise<AppConfig> {
  const body = await requestJson(apiUrl('app-config'), { signal });
  if (typeof body !== 'object' || body === null || !('oraculo_url' in body)) throw badFormat();
  const url = body.oraculo_url;
  if (url !== null && typeof url !== 'string') throw badFormat();
  // Un servidor anterior no lo manda: entonces no se entró por Oráculo.
  const viaGateway = 'via_gateway' in body ? body.via_gateway : false;
  if (typeof viaGateway !== 'boolean') throw badFormat();
  return { oraculo_url: url, via_gateway: viaGateway };
}

/**
 * Solo direcciones http(s): así un valor raro en el servidor nunca se vuelve
 * un enlace peligroso (por ejemplo `javascript:`).
 *
 * @example safeOraculoUrl('http://172.25.18.234') // 'http://172.25.18.234'
 * @example safeOraculoUrl('javascript:alert(1)') // null
 */
export function safeOraculoUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}
