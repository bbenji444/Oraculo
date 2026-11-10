/**
 * Hooks de subdivisiones con TanStack Query (CLAUDE.md §6.2, ADR-0038).
 *
 * Editar una subdivisión cambia también el nombre y el estado de su tema
 * general, así que se invalidan las subdivisiones y los conceptos.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type CategoryCreate,
  type CategoryPatch,
  createCategory,
  deleteCategory,
  listCategories,
  updateCategory,
} from '../services/categories';

const CATEGORIES_KEY = ['categories'] as const;

/**
 * Las subdivisiones en su orden.
 *
 * @param includeInactive También las apagadas (el editor).
 */
export function useCategories(includeInactive = false) {
  return useQuery({
    queryKey: [...CATEGORIES_KEY, includeInactive],
    queryFn: ({ signal }) => listCategories(includeInactive, signal),
  });
}

/** Al cambiar una subdivisión cambia también su tema general (un concepto). */
function useRefreshCatalog() {
  const client = useQueryClient();
  return async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: CATEGORIES_KEY }),
      client.invalidateQueries({ queryKey: ['concepts'] }),
    ]);
  };
}

/** Edita una subdivisión. */
export function useUpdateCategory() {
  const refresh = useRefreshCatalog();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: CategoryPatch }) => updateCategory(id, patch),
    onSuccess: refresh,
  });
}

/** Agrega una subdivisión con su tema general. */
export function useCreateCategory() {
  const refresh = useRefreshCatalog();
  return useMutation({
    mutationFn: (data: CategoryCreate) => createCategory(data),
    onSuccess: refresh,
  });
}

/** Borra una subdivisión; sus notas pasan a «Otros». */
export function useDeleteCategory() {
  const refresh = useRefreshCatalog();
  return useMutation({ mutationFn: (id: number) => deleteCategory(id), onSuccess: refresh });
}
