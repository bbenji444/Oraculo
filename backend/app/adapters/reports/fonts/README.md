# Fuentes de los reportes

Noto Sans regular y negrita, en versión fija (no variable). Van incluidas en el repositorio para que el PDF muestre la Ñ y los acentos igual en cualquier servidor, sin depender de las fuentes instaladas (ADR-0018). La plantilla las carga con `@font-face`.

## Manifiesto

Descargadas el 17/10/2026.

| Archivo | Origen | SHA-256 |
|---|---|---|
| `NotoSans-Regular.ttf` | <https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/NotoSans/hinted/ttf/NotoSans-Regular.ttf> | `478c558ea716033cd60c03438f628dfa75694dcf6b5f6d505a2f05fd2b4f3823` |
| `NotoSans-Bold.ttf` | <https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/NotoSans/hinted/ttf/NotoSans-Bold.ttf> | `1df075a380fc7cb898acf64c1f7b3b4dd780de3caa860178bf929de35817a913` |
| `OFL.txt` | <https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/OFL.txt> | `cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a` |

## Licencia

SIL Open Font License 1.1 (`OFL.txt`): permite usarlas, incrustarlas en documentos y redistribuirlas junto con el software, siempre que el archivo de licencia las acompañe. Copyright 2022 The Noto Project Authors.

## Para actualizarlas

1. Descarga los mismos archivos de las URLs de arriba.
2. Anota la fecha y el SHA-256 nuevos (`sha256sum NotoSans-*.ttf OFL.txt`).
3. Corre las pruebas de reportes: comprueban que la Ñ y los acentos se lean en el PDF.

## Orbitron (títulos del reporte Oráculo, F12.10)

Para homologar el reporte con Oráculo, los títulos, las cifras y el número de expediente van en **Orbitron**, la misma fuente técnica de OSINT Oráculo. Es un subconjunto en WOFF2 que se tomó de `/opt/osint/app/static/osint/fonts/` en el servidor de Oráculo (solo lectura) el 26/10/2026. WeasyPrint lo lee gracias a `brotli`. Si a un texto le falta una letra en Orbitron, el PDF usa Noto Sans para esa letra.

| Archivo | Origen | SHA-256 |
|---|---|---|
| `orbitron-400.woff2` | OSINT Oráculo (`fonts/orbitron-400.woff2`) | `9320ca80be2f4275e7aaa009bc058b9ea46264d4f92b06f0b822c3405cf45841` |
| `orbitron-700.woff2` | OSINT Oráculo (`fonts/orbitron-700.woff2`) | `ee6acc5ad5349018f9ca71fab8118144160e110838931874150a1ac3f97db38d` |

Licencia: SIL Open Font License 1.1 (Copyright 2018 The Orbitron Project Authors), la misma de `OFL.txt`.

## Exo 2 e Inter (tipografía del reporte desde el 30/10/2026, noche)

Benji pidió «algo que se vea más moderno pero tampoco tan exagerado, algo acorde al sistema». El reporte usa la misma pareja que la interfaz del monitor:

- **Exo 2** (600 y 700): títulos, preguntas, titulares y cifras;
- **Inter** (400, cursiva, 600 y 700): el texto, justificado; también las horas, el expediente y la numeración, con cifras tabulares.

Subconjunto latino en WOFF2 de `@fontsource` 5.3.0, descargado el 30/10/2026 de `https://cdn.jsdelivr.net/npm/@fontsource/<familia>@5.3.0/files/<archivo>`. Trae la Ñ, los acentos, «», las rayas y las comillas. Licencia SIL Open Font License 1.1 (`LICENSE-Exo2.txt`, `LICENSE-Inter.txt`).

| Archivo | SHA-256 |
|---|---|
| `exo-2-latin-600-normal.woff2` | `fd2112e53440975a4885179f3d09058787b97b711e7e141c55fcaecaf48fbcb6` |
| `exo-2-latin-700-normal.woff2` | `96c87b1597aed754e0ad45970883774e851a390788e7fba7b3f49f8d1f6e5a6b` |
| `inter-latin-400-normal.woff2` | `8909904ab6c872eb994093482a88a28eca2cd95912d7b6fecd72103b0dc07edc` |
| `inter-latin-400-italic.woff2` | `7ea9d2f1274cebee837f0c6eebb426c18fbb2333a6b6da4d02ec5cf47db7fb8e` |
| `inter-latin-600-normal.woff2` | `f9a06e79cd3a2a20951c0f0e28f66dd0e6d3fda73911d640a2125c8fcb78f21a` |
| `inter-latin-700-normal.woff2` | `6f56409fd3d64bb85f7d070bce20749db2d66b6d63cec586cc22d1c761be2491` |
| `LICENSE-Exo2.txt` | `7644b74e07215f62af4ebbfcf2b0f06a428d70d32c41e751fba93763a683c3f5` |
| `LICENSE-Inter.txt` | `3b0a5fca3d17942cde889069889dedbbbd075e9b599968c82a95f4d944e9b345` |

Antes de Exo 2 e Inter, el reporte usó unas horas Noto Serif y luego IBM Plex. Se borraron el 30/10/2026, con la aprobación de Benji, porque ya nada las usaba.
