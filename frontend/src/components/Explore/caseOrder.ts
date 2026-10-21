/**
 * Orden de los casos en «Agregar al caso» (Fase 9.3, decisión D8).
 *
 * El último caso usado va primero: en la historia H9.1 el analista agrega 8
 * notas seguidas al mismo caso, y así cada una le cuesta un clic. Los demás
 * conservan el orden de la API (el que cambió más recientemente primero).
 *
 * No hace: no pide datos ni recuerda nada (eso es el store de Explorar).
 */
import type { Case } from '../../services/cases';

/**
 * Casos con el último usado al frente.
 *
 * @param cases Casos abiertos, como llegan de la API.
 * @param lastCaseId Último caso usado, si se recuerda alguno.
 * @returns Una lista nueva; la original no cambia.
 */
export function withLastFirst(cases: readonly Case[], lastCaseId: string | null): Case[] {
  const last = cases.find((c) => c.id === lastCaseId);
  return last ? [last, ...cases.filter((c) => c !== last)] : [...cases];
}
