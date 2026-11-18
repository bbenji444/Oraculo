/**
 * Estado de la línea del tiempo de Explorar (F12.7): si está abierta, si se ve
 * la lista de noticias del panel izquierdo y qué tramo, categoría, estado y
 * plataforma (ADR-0117) eligió el analista.
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
import type { Platform } from '../services/searches';

export interface TimelineState extends TimelineFilters {
  open: boolean;
  /** Si se ve la lista de noticias del panel izquierdo (oculta por defecto). */
  listOpen: boolean;
  setOpen: (open: boolean) => void;
  setListOpen: (listOpen: boolean) => void;
  /** Elige un tramo; elegir el mismo otra vez lo quita. */
  toggleRange: (range: readonly [number, number]) => void;
  /** Una sola categoría (el menú del diseño de columna), o `null` = todas. */
  setCategory: (categoryId: number | null) => void;
  /** Prende o apaga una categoría (los botones de color del expediente). */
  toggleCategory: (categoryId: number) => void;
  setState: (stateCode: string | null) => void;
  /**
   * Una sola plataforma (las pestañas «Todo · Noticias · Facebook…» del
   * expediente, ADR-0117), o `null` = todas.
   */
  setPlatform: (platform: Platform | null) => void;
  /** Prende o apaga una plataforma (la sección «Plataforma» de «Filtro»: varias a la vez). */
  togglePlatform: (platform: Platform) => void;
  /** Quita todos los filtros, también los de plataforma. */
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
    set({ categoryIds: categoryId === null ? [] : [categoryId] });
  },
  toggleCategory: (categoryId) => {
    set((state) => ({
      categoryIds: state.categoryIds.includes(categoryId)
        ? state.categoryIds.filter((id) => id !== categoryId)
        : [...state.categoryIds, categoryId],
    }));
  },
  setState: (stateCode) => {
    set({ stateCode });
  },
  setPlatform: (platform) => {
    set({ platforms: platform === null ? [] : [platform] });
  },
  togglePlatform: (platform) => {
    set((state) => ({
      platforms: state.platforms.includes(platform)
        ? state.platforms.filter((p) => p !== platform)
        : [...state.platforms, platform],
    }));
  },
  clear: () => {
    set(NO_FILTERS);
  },
}));
