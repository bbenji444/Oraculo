/**
 * Hooks de conceptos con TanStack Query (CLAUDE.md §6.2).
 *
 * Cada cambio (crear, editar, borrar) invalida la lista para que la tabla
 * se actualice sola. "Probar concepto" es una mutación: se ejecuta solo
 * cuando la persona presiona el botón, nunca al teclear.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type ConceptInput,
  type ConceptPatch,
  createConcept,
  deleteConcept,
  listConcepts,
  previewQueries,
  updateConcept,
} from '../services/concepts';

const CONCEPTS_KEY = ['concepts'] as const;

/** Todos los conceptos vigentes (activos e inactivos). */
export function useConcepts() {
  return useQuery({
    queryKey: CONCEPTS_KEY,
    queryFn: ({ signal }) => listConcepts(signal),
  });
}

function useInvalidateConcepts() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: CONCEPTS_KEY });
}

/** Crea un concepto. */
export function useCreateConcept() {
  const invalidate = useInvalidateConcepts();
  return useMutation({
    mutationFn: (input: ConceptInput) => createConcept(input),
    onSuccess: invalidate,
  });
}

/** Edita un concepto (también activar o desactivar). */
export function useUpdateConcept() {
  const invalidate = useInvalidateConcepts();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: ConceptPatch }) => updateConcept(id, patch),
    onSuccess: invalidate,
  });
}

/** Borra un concepto. */
export function useDeleteConcept() {
  const invalidate = useInvalidateConcepts();
  return useMutation({
    mutationFn: (id: number) => deleteConcept(id),
    onSuccess: invalidate,
  });
}

/** "Probar concepto": arma las consultas sin gastar créditos. */
export function useQueryPreview() {
  return useMutation({ mutationFn: previewQueries });
}
