/**
 * Hooks de casos de investigación con TanStack Query (CLAUDE.md §6.2, Fase 9.3).
 *
 * Todas las claves empiezan con `cases`: cualquier cambio (crear, editar,
 * agregar o quitar una nota) las invalida juntas, así la lista, el detalle y
 * el botón "Agregar al caso" de Explorar nunca se contradicen.
 *
 * Abrir un caso queda en la bitácora del servidor; el servidor registra una
 * vista por persona cada 5 minutos, así que las recargas no la llenan.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  addCaseArticle,
  type CaseInput,
  type CasePatch,
  type CaseStatus,
  createCase,
  getCase,
  listCaseArticles,
  listCases,
  removeCaseArticle,
  updateCase,
} from '../services/cases';

const CASES_KEY = ['cases'] as const;

/** Mis casos; `archived` trae solo los archivados. */
export function useCases(status?: CaseStatus) {
  return useQuery({
    queryKey: [...CASES_KEY, 'list', status ?? 'activos'],
    queryFn: ({ signal }) => listCases({ status }, signal),
  });
}

/** Mis casos abiertos y si cada uno ya tiene la nota (botón "Agregar al caso"). */
export function useCasesForArticle(articleId: number | null) {
  return useQuery({
    queryKey: [...CASES_KEY, 'for-article', articleId],
    queryFn: ({ signal }) => listCases({ status: 'open', containsArticle: articleId ?? 0 }, signal),
    enabled: articleId !== null,
  });
}

/** Un caso abierto en la pantalla. */
export function useCase(id: string | null) {
  return useQuery({
    queryKey: [...CASES_KEY, 'detail', id],
    queryFn: ({ signal }) => getCase(id ?? '', signal),
    enabled: id !== null,
  });
}

/** Las notas de un caso. */
export function useCaseArticles(id: string | null) {
  return useQuery({
    queryKey: [...CASES_KEY, 'articles', id],
    queryFn: ({ signal }) => listCaseArticles(id ?? '', signal),
    enabled: id !== null,
  });
}

function useInvalidateCases() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: CASES_KEY });
}

/** Crea un caso. */
export function useCreateCase() {
  const invalidate = useInvalidateCases();
  return useMutation({
    mutationFn: (input: CaseInput) => createCase(input),
    onSuccess: invalidate,
  });
}

/** Edita, cierra, archiva o reabre un caso. */
export function useUpdateCase() {
  const invalidate = useInvalidateCases();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: CasePatch }) => updateCase(id, patch),
    onSuccess: invalidate,
  });
}

/** Agrega una nota a un caso. */
export function useAddCaseArticle() {
  const invalidate = useInvalidateCases();
  return useMutation({
    mutationFn: ({ caseId, articleId }: { caseId: string; articleId: number }) =>
      addCaseArticle(caseId, articleId),
    onSuccess: invalidate,
  });
}

/** Quita una nota de un caso. */
export function useRemoveCaseArticle() {
  const invalidate = useInvalidateCases();
  return useMutation({
    mutationFn: ({ caseId, articleId }: { caseId: string; articleId: number }) =>
      removeCaseArticle(caseId, articleId),
    onSuccess: invalidate,
  });
}
