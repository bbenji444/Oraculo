# Radar sobre el globo

Capas propias de MapLibre en WebGL 2 que se ven solo mientras corre una búsqueda. Las pone y las quita `components/Mando/ScanOverlay.tsx`; aquí no hay React ni textos de la interfaz.

| Archivo    | Qué hace                                                                                                                                                                                                             |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dome.ts`  | La cúpula de una zona: media esfera de vidrio sobre la región, con el haz del radar y una columna por nota (11/11/2026).                                                                                             |
| `shell.ts` | La esfera de «Todo el mundo»: envuelve la Tierra, aparece, gira su haz, enciende un ping por nota y se disuelve al terminar (ADR-0116).                                                                              |
| `gl.ts`    | La plomería que comparten las dos: compilar shaders, mallas, atributos, uniforms de la proyección, la función `line()` de la rejilla en GLSL con su tamaño (`GRID_*`) y `glslFloat()` para escribir números en GLSL. |

## Cómo se usa

```ts
const dome = addDomeRadar(map, regionBbox, animate); // una zona
const shell = addWorldShell(map, { animate, daylight }); // «Todo el mundo»

shell.setBlips(notasEncontradas); // un ping por nota nueva
shell.dissolve(); // al terminar: destello, se expande y se quita sola
```

Los números de los shaders van como constantes de TypeScript con nombre y se escriben con `glslFloat()` (GLSL no acepta `2` donde espera `2.0`). `shaders.test.ts` captura el código que cada capa manda a compilar y revisa que la cúpula y la esfera giren igual y usen la misma rejilla.

Con «Menos movimiento» del sistema (`animate` en falso) las dos capas quedan quietas y no piden cuadros de más; la esfera además aparece y se quita al instante.

## Ojo al actualizar maplibre-gl

Las dos recortan lo que queda detrás de la Tierra con `globeComputeClippingZ`, del preludio de las capas propias de MapLibre. La esfera depende además de dos convenciones internas de maplibre-gl 6.14.0: la esfera unitaria con `y` al norte y la longitud 0 en `+z`, y el plano de recorte del horizonte `[n, −1/D]`. Están anotadas con «VERIFICAR» en `shell.ts` y cubiertas en `shell.test.ts`. Después de actualizar, hay que ver en pantalla una búsqueda en una zona y otra en «Todo el mundo».
