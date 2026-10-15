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

// Puerto de uvicorn definido en scripts/dev/servicios.sh.
const API_DEV_TARGET = 'http://localhost:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: API_DEV_TARGET, changeOrigin: false },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
