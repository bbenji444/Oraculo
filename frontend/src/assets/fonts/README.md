# Fuentes de la interfaz

Van autoalojadas: la interfaz no descarga nada de internet (`src/styles/index.css`).

| Fuente                    | Dónde se usa                                                                     |
| ------------------------- | -------------------------------------------------------------------------------- |
| **Orbitron** (400, 700)   | Títulos, botones, etiquetas y cifras (`--font-display`), como Oráculo core       |
| **Roboto** (300 a 700)    | El texto (`--font-sans`), como Oráculo core                                      |
| **Material Icons**        | Los iconos (`components/ui/Icon.tsx`), los mismos de Oráculo core (ADR-0108)     |
| **Exo 2** (500, 600, 700) | Ya no se usa: de 30/10 a 17/11/2026 fue la letra de títulos; queda para regresar |
| **Inter** (400 a 700)     | Ya no se usa: de 30/10 a 17/11/2026 fue la letra del texto; queda para regresar  |

Orbitron y Roboto se tomaron de OSINT Oráculo el 26/10/2026. Desde el 17/11/2026 son las letras de toda la interfaz, como en Oráculo core (ADR-0037 y ADR-0108). El 30/10/2026 Benji había pedido «algo que se vea más moderno pero tampoco tan exagerado» y se usaron Exo 2 e Inter; siguen cargadas por si se quiere regresar.

## Material Icons

La letra de iconos de Google que usa Oráculo core. Oráculo la carga de Google Fonts; aquí va autoalojada para no descargar nada de internet. Es la versión 145, descargada el 17/11/2026 de la dirección que da `https://fonts.googleapis.com/icon?family=Material+Icons`:

`https://fonts.gstatic.com/s/materialicons/v145/flUhRq6tzZclQEJ-Vdg-IuiaDsNc.woff2`

Licencia Apache 2.0 (`LICENSE-MaterialIcons.txt`, del repositorio `google/material-design-icons`; sin las líneas en blanco del final). La letra completa pesa 125 KB y se descarga una vez; el navegador la guarda.

| Archivo                     | SHA-256                                                            |
| --------------------------- | ------------------------------------------------------------------ |
| `material-icons-v145.woff2` | `8265f64786397d6b832d1ca0aafdf149ad84e72759fffa9f7272e91a0fb015d1` |
| `LICENSE-MaterialIcons.txt` | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |

## Exo 2 e Inter

Subconjunto latino en WOFF2 de `@fontsource` 5.3.0, descargado el 30/10/2026 de `https://cdn.jsdelivr.net/npm/@fontsource/<familia>@5.3.0/files/<archivo>`. Trae la Ñ, los acentos, «», las rayas y las comillas. Licencia SIL Open Font License 1.1 (`LICENSE-Exo2.txt`, `LICENSE-Inter.txt`).

| Archivo                        | SHA-256                                                            |
| ------------------------------ | ------------------------------------------------------------------ |
| `exo-2-latin-500-normal.woff2` | `78b3f89f94236f0298cbb49ef6839627430f3aac63a00c75f468a60477742e03` |
| `exo-2-latin-600-normal.woff2` | `fd2112e53440975a4885179f3d09058787b97b711e7e141c55fcaecaf48fbcb6` |
| `exo-2-latin-700-normal.woff2` | `96c87b1597aed754e0ad45970883774e851a390788e7fba7b3f49f8d1f6e5a6b` |
| `inter-latin-400-normal.woff2` | `8909904ab6c872eb994093482a88a28eca2cd95912d7b6fecd72103b0dc07edc` |
| `inter-latin-500-normal.woff2` | `f3779f1efccc4bdcdf9c0a02ab95bf6bd092ed09c48c08cedc725889edd1d19f` |
| `inter-latin-600-normal.woff2` | `f9a06e79cd3a2a20951c0f0e28f66dd0e6d3fda73911d640a2125c8fcb78f21a` |
| `inter-latin-700-normal.woff2` | `6f56409fd3d64bb85f7d070bce20749db2d66b6d63cec586cc22d1c761be2491` |
| `LICENSE-Exo2.txt`             | `7644b74e07215f62af4ebbfcf2b0f06a428d70d32c41e751fba93763a683c3f5` |
| `LICENSE-Inter.txt`            | `3b0a5fca3d17942cde889069889dedbbbd075e9b599968c82a95f4d944e9b345` |
