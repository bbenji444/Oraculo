/**
 * Configuración de MapLibre que se hace una sola vez por página:
 *
 * 1. Dónde está su "worker" (el hilo que decodifica teselas). MapLibre v6 lo
 *    busca junto a su propio archivo, pero Vite no lo copia al build por sí
 *    solo; con `?url` Vite lo publica y `setWorkerUrl` le dice dónde quedó.
 *    El worker de MapLibre 6.14 es autocontenido (no importa otros archivos).
 * 2. Cuántos workers: MapLibre 6 usa uno solo fuera de Safari, así que las
 *    teselas de calles se decodificaban de una en una y el mapa «cargaba poco
 *    a poco» al llegar a una nota (Benji, 27/10/2026). Ver `map/workers.ts`.
 * 3. El protocolo `pmtiles://`, para leer cada tesela pidiendo solo sus bytes
 *    del archivo .pmtiles (HTTP Range), sin servidor de teselas (ADR-0004).
 */
import { addProtocol, setWorkerCount, setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import { Protocol } from 'pmtiles';

import { mapWorkerCount } from './workers';

let done = false;

/** Configura MapLibre si no se ha hecho ya (antes de crear cualquier mapa). */
export function setupMapLibre(): void {
  if (done) return;
  setWorkerUrl(workerUrl);
  setWorkerCount(mapWorkerCount(navigator.hardwareConcurrency));
  addProtocol('pmtiles', new Protocol().tile);
  done = true;
}
