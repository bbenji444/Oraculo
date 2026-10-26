/**
 * Estado de la línea del tiempo de Explorar (F12.7): si está abierta y qué
 * tramo, categoría y estado eligió el analista.
 *
 * Los filtros se aplican a la misma lista que usan el globo y la lista de
 * noticias (`ExplorePage`), así los tres muestran siempre las mismas notas.
 * No se guarda en el navegador: otra búsqueda empieza sin filtros.
 *
 * No hace: no calcula los tramos (eso es `components/Explore/timelineData.ts`).
 */
import { create } from 'zustand';

import {
  NO_FILTERS,
  type OrderBasis,
  type TimelineFilters,
} from '../components/Explore/timelineData';

export interface TimelineState extends TimelineFilters {
  open: boolean;
  /** Orden de la tira: por la fecha del hecho (por defecto) o de publicación. */
  orderBasis: OrderBasis;
  setOpen: (open: boolean) => void;
  setOrderBasis: (orderBasis: OrderBasis) => void;
  /** Elige un tramo; elegir el mismo otra vez lo quita. */
  toggleRange: (range: readonly [number, number]) => void;
  setCategory: (categoryId: number | null) => void;
  setState: (stateCode: string | null) => void;
  clear: () => void;
}

export const useTimelineStore = create<TimelineState>()((set) => ({
  ...NO_FILTERS,
  open: true,
  orderBasis: 'event',
  setOpen: (open) => {
    set({ open });
  },
  setOrderBasis: (orderBasis) => {
    set({ orderBasis });
  },
  toggleRange: (range) => {
    set((state) => ({
      range: state.range?.[0] === range[0] && state.range[1] === range[1] ? null : range,
    }));
  },
  setCategory: (categoryId) => {
    set({ categoryId });
  },
  setState: (stateCode) => {
    set({ stateCode });
  },
  clear: () => {
    set(NO_FILTERS);
  },
}));
