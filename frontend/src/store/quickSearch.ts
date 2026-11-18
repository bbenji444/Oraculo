/**
 * La última búsqueda rápida que lanzó la persona (ADR-0110).
 *
 * Sirve para ofrecer «Guardar como concepto» mientras se ven sus resultados:
 * la búsqueda usa un concepto oculto, y aquí queda cuál es. También guarda el
 * aviso con que respondió al lanzarse (Google web sin créditos, ADR-0115).
 *
 * No hace: no se guarda entre visitas. Al reabrir la búsqueda desde el
 * historial, el concepto sigue oculto y se puede guardar desde la API.
 */
import { create } from 'zustand';

export interface QuickSearchMemory {
  searchId: string;
  conceptId: number;
  conceptName: string;
  /** Lo que escribió la persona. */
  text: string;
  /**
   * Aviso del lanzamiento («Sin créditos de Google web: se buscó en
   * noticias», ADR-0115); `null` si no hubo. Lo muestran el avance y el
   * expediente de esta búsqueda (`searchNotices`).
   */
  notice: string | null;
  /** Si ya se guardó como concepto. */
  kept: boolean;
}

interface QuickSearchState {
  last: QuickSearchMemory | null;
  remember: (memory: Omit<QuickSearchMemory, 'kept'>) => void;
  markKept: () => void;
}

export const useQuickSearchStore = create<QuickSearchState>()((set) => ({
  last: null,
  remember: (memory) => {
    set({ last: { ...memory, kept: false } });
  },
  markKept: () => {
    set((state) => (state.last ? { last: { ...state.last, kept: true } } : state));
  },
}));
