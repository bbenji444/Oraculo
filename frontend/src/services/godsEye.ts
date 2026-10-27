/**
 * Dónde está God's Eye View y si está respondiendo (27/10/2026).
 *
 * God's Eye View es un proyecto aparte (github.com/bilawalsidhu/gods-eye-view),
 * copiado tal cual para que Benji lo evalúe. Corre en su propio servidor de
 * Vite en el puerto 4173 (`make up` lo arranca, ver scripts/dev/gods_eye.sh).
 * La pestaña «God's Eye» lo muestra en un iframe.
 *
 * No hace: no habla con su API ni le pasa llaves; solo revisa que conteste.
 */

/** Puerto de su servidor (el de su README, scripts/dev/servicios.sh). */
export const GODS_EYE_PORT = 4173;

/**
 * Dirección del módulo, en la misma máquina desde la que se abrió el monitor.
 *
 * @example godsEyeUrl({ protocol: 'http:', hostname: 'localhost' }) // 'http://localhost:4173/'
 */
export function godsEyeUrl(location: Pick<Location, 'protocol' | 'hostname'>): string {
  return `${location.protocol}//${location.hostname}:${String(GODS_EYE_PORT)}/`;
}

/**
 * Dice si el servidor de God's Eye View responde.
 *
 * Es de otro origen: con `no-cors` no se puede leer la respuesta, pero la
 * petición solo falla si nadie escucha en el puerto, y eso basta.
 *
 * @returns `true` si contestó; `false` si no hay nadie en ese puerto.
 */
export async function isGodsEyeUp(url: string, signal?: AbortSignal): Promise<boolean> {
  try {
    await fetch(url, { mode: 'no-cors', cache: 'no-store', signal });
    return true;
  } catch {
    return false;
  }
}
