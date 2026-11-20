/**
 * Configuración de Vite (servidor de desarrollo y build) y de Vitest.
 *
 * En desarrollo, las peticiones a /api se reenvían a la API que corre en
 * Ubuntu (WSL); Windows la ve en localhost gracias al reenvío de puertos de
 * WSL2. En producción, nginx hace ese mismo papel (nginx/).
 */
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Puertos de uvicorn y nginx definidos en scripts/dev/servicios.sh.
const API_DEV_TARGET = 'http://localhost:8000';
const NGINX_DEV_TARGET = 'http://localhost:8080';

export default defineConfig({
  // Rutas relativas en el build: la pantalla funciona igual en la raíz
  // (acceso directo) que bajo /m/noticias/ detrás del gateway de Oráculo,
  // que no reescribe las URLs metidas en el JavaScript (ADR-0119).
  base: './',
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: API_DEV_TARGET, changeOrigin: false },
      // Teselas, fuentes y sprite: los sirve nginx con soporte de Range.
      '/tiles': { target: NGINX_DEV_TARGET, changeOrigin: false },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
