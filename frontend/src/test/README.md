# src/test/

Apoyo para las pruebas del frontend. No se incluye en el build.

- `fixtures/explorar/`: respuestas **reales** de la API local, grabadas de la búsqueda "Extorsión · Jalisco" (concepto 3, región 272). Las usa la prueba de humo `src/App.smoke.test.tsx`, así nunca hay red ni se gastan créditos (CLAUDE.md §7). De las listas largas se guardan solo unas cuantas entradas: cuatro notas (dentro, fuera, sin ubicación y no relevante), cuatro conceptos y cinco municipios.
  - **Excepción hecha a mano (18/11/2026, ADR-0117):** `articles.json` trae además tres notas inventadas, con ids 9001 a 9003, para probar las pestañas de plataforma y las bandas de relevancia: una publicación relevante de Facebook (llega por Google News RSS con link de redirección), un video de YouTube «por confirmar» (0.7) y un hilo de X «cercano» (0.45, no relevante). Traen `platform` y `relevance_band`; las cuatro grabadas no, así se prueba también el respaldo para respuestas de antes. Al regrabar, se vuelven a agregar.
- `caseFixtures.ts` (F12): constructores de entidades, menciones y vínculos con la forma exacta de la API, para las pruebas de Casos (`components/Cases/*.test.ts`). Se pide solo lo que cada prueba necesita.

Para volver a grabar `fixtures/explorar/`, con los servicios arriba (`wsl make up`), se piden las mismas rutas a `http://localhost:8080/api/v1/` y se recortan igual. Si cambia el formato de la API, la prueba de humo falla al validar las respuestas: así se nota que hay que regrabar.
