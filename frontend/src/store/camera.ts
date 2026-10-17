/**
 * Cámara del globo compartida con el fondo de universo (ADR-0017).
 *
 * El mapa la actualiza en cada cuadro de movimiento; el fondo se suscribe con
 * `useCameraStore.subscribe` (fuera de React), así moverse no vuelve a dibujar
 * ningún componente.
 *
 * No hace: no mueve el mapa (solo refleja dónde está).
 */
import { create } from 'zustand';

import type { CameraView } from '../map/space';

interface CameraState {
  view: CameraView;
  setView: (view: CameraView) => void;
}

// Igual que la vista inicial del globo (México, eje inclinado).
const INITIAL_VIEW: CameraView = { lng: -102, lat: 23.5, zoom: 1.8, bearing: -15, pitch: 0 };

export const useCameraStore = create<CameraState>()((set) => ({
  view: INITIAL_VIEW,
  setView: (view) => {
    set({ view });
  },
}));
