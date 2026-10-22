/**
 * Claves de TanStack Query de lo que depende de las entidades de un caso
 * (Fases 9.4 y 9.5).
 *
 * Confirmar, descartar, unir o separar una entidad cambia sus sugerencias de
 * duplicados y sus vínculos por coocurrencia: por eso cualquier acción sobre
 * entidades invalida las tres. Todas empiezan con `cases` para que un cambio
 * del caso las invalide junto con el resto.
 */
import type { QueryClient } from '@tanstack/react-query';

export function entitiesKey(caseId: string): unknown[] {
  return ['cases', 'entities', caseId];
}

export function mergeSuggestionsKey(caseId: string): unknown[] {
  return ['cases', 'merge-suggestions', caseId];
}

export function relationshipsKey(caseId: string): unknown[] {
  return ['cases', 'relationships', caseId];
}

/** Vuelve a pedir entidades, duplicados y vínculos del caso. */
export async function invalidateCaseEntities(client: QueryClient, caseId: string): Promise<void> {
  await Promise.all(
    [entitiesKey, mergeSuggestionsKey, relationshipsKey].map((key) =>
      client.invalidateQueries({ queryKey: key(caseId) }),
    ),
  );
}
