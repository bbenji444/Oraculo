# src/test/

Apoyo para las pruebas del frontend. No se incluye en el build.

- `fixtures/explorar/`: respuestas **reales** de la API local, grabadas de la búsqueda "Extorsión · Jalisco" (concepto 3, región 272). Las usa la prueba de humo `src/App.smoke.test.tsx`, así nunca hay red ni se gastan créditos (CLAUDE.md §7). De las listas largas se guardan solo unas cuantas entradas: cuatro notas (dentro, fuera, sin ubicación y no relevante), cuatro conceptos y cinco municipios.

Para volver a grabarlas, con los servicios arriba (`wsl make up`), se piden las mismas rutas a `http://localhost:8080/api/v1/` y se recortan igual. Si cambia el formato de la API, la prueba de humo falla al validar las respuestas: así se nota que hay que regrabar.
