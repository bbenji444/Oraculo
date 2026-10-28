/**
 * Estado de la pantalla del diseño «Centro de mando» (diseño 3, 27/10/2026):
 * qué parte de la consulta se está ajustando, si el expediente de resultados
 * está a la vista y si la consola está minimizada.
 *
 * Va aparte de `explorer.ts` porque solo existe en este diseño; la búsqueda
 * misma (región, conceptos, fechas, fuentes) sigue en `explorer.ts`, así que
 * los dos diseños buscan exactamente igual.
 *
 * Solo se recuerda en el navegador si el resumen del expediente quedó plegado:
 * quien lo pliega quiere ver más noticias también la próxima vez.
 */
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { safeStorage } from './explorer';

/** Parte de la frase de la consulta que se puede tocar para cambiarla. */
export type MissionSlot = 'concepts' | 'region' | 'range' | 'sources';

export interface MandoState {
  /** Parte que se está ajustando (su tarjeta sube sobre la consola), o `null`. */
  slot: MissionSlot | null;
  /** Expediente de resultados a la derecha. */
  dossierOpen: boolean;
  /** Consola reducida a una pastilla para ver el globo completo. */
  dockMinimized: boolean;
  /** Editando la consulta con resultados a la vista (para lanzar otra). */
  editing: boolean;
  /** Alto que ocupa la consola abajo, en píxeles: el globo flota encima. */
  dockHeight: number;
  /**
   * Resumen del expediente desplegado (cifras, categorías, descargas). Plegado,
   * la lista de noticias tiene casi todo el alto (Benji, 27/10/2026).
   */
  summaryOpen: boolean;
  setSlot: (slot: MissionSlot | null) => void;
  toggleSlot: (slot: MissionSlot) => void;
  setDossierOpen: (open: boolean) => void;
  setDockMinimized: (minimized: boolean) => void;
  setEditing: (editing: boolean) => void;
  setDockHeight: (height: number) => void;
  setSummaryOpen: (open: boolean) => void;
}

export const useMandoStore = create<MandoState>()(
  persist(
    (set) => ({
      slot: null,
      dossierOpen: true,
      dockMinimized: false,
      editing: false,
      dockHeight: 0,
      summaryOpen: true,
      setSlot: (slot) => {
        set({ slot });
      },
      toggleSlot: (slot) => {
        set((state) => ({ slot: state.slot === slot ? null : slot }));
      },
      setDossierOpen: (dossierOpen) => {
        set({ dossierOpen });
      },
      setDockMinimized: (dockMinimized) => {
        set({ dockMinimized, slot: null });
      },
      setEditing: (editing) => {
        set({ editing, slot: null });
      },
      setDockHeight: (dockHeight) => {
        set({ dockHeight });
      },
      setSummaryOpen: (summaryOpen) => {
        set({ summaryOpen });
      },
    }),
    {
      name: 'monitor-noticias:centro-de-mando',
      storage: createJSONStorage(() => safeStorage),
      partialize: (state) => ({ summaryOpen: state.summaryOpen }),
    },
  ),
);
