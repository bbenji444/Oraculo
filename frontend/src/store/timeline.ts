/**
 * Estado de la línea del tiempo de Explorar (F12.7): si está abierta, si se ve
 * la lista de noticias del panel izquierdo y qué tramo, categoría y estado
 * eligió el analista.
 *
 * Los filtros se aplican a la misma lista que usan el globo y la lista de
 * noticias (`ExplorePage`), así los tres muestran siempre las mismas notas.
 * La lista de la izquierda empieza oculta: la línea del tiempo la reemplaza
 * (decisión de Benji del 26/10/2026) y se vuelve a mostrar con «☰ Lista».
 * No se guarda en el navegador: otra búsqueda empieza sin filtros.
 *
 * No hace: no calcula los tramos (eso es `components/Explore/timelineData.ts`).
 */
import { create } from 'zustand';

import { NO_FILTERS, type TimelineFilters } from '../components/Explore/timelineData';

export interface TimelineState extends TimelineFilters {
  open: boolean;
  /** Si se ve la lista de noticias del panel izquierdo (oculta por defecto). */
  listOpen: boolean;
  setOpen: (open: boolean) => void;
  setListOpen: (listOpen: boolean) => void;
  /** Elige un tramo; elegir el mismo otra vez lo quita. */
  toggleRange: (range: readonly [number, number]) => void;
  setCategory: (categoryId: number | null) => void;
  setState: (stateCode: string | null) => void;
  clear: () => void;
}

export const useTimelineStore = create<TimelineState>()((set) => ({
  ...NO_FILTERS,
  open: true,
  listOpen: false,
  setOpen: (open) => {
    set({ open });
  },
  setListOpen: (listOpen) => {
    set({ listOpen });
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
