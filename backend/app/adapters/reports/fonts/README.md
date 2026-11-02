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

## Barlow (tipografía del reporte desde el 02/11/2026)

Benji pidió «una más pro acorde al sistema» y eligió entre tres muestras del mismo reporte: Rajdhani, Barlow y Space Grotesk. Eligió **Barlow**, la familia de los tableros de tránsito y defensa:

- **Barlow Semi Condensed** (600 y 700): títulos, preguntas, titulares y cifras;
- **Barlow** (400, cursiva, 600 y 700): el texto, justificado; también las horas y la numeración, con cifras tabulares.

Subconjunto latino en WOFF2 de `@fontsource` 5.3.0, descargado el 02/11/2026 de `https://cdn.jsdelivr.net/npm/@fontsource/<familia>@5.3.0/files/<archivo>`. Licencia SIL Open Font License 1.1 (`LICENSE-Barlow.txt`).

| Archivo | SHA-256 |
|---|---|
| `barlow-latin-400-normal.woff2` | `b0a8ad37ac45f5fb22ced461576db72e44e295107aad7a9c8a7a4bad728fd03b` |
| `barlow-latin-400-italic.woff2` | `7a306c56f630df002deeafbd521738e20795d765feea65030def2e80f9a3d62f` |
| `barlow-latin-600-normal.woff2` | `4b52ddd4836b592df0e4832b8286956883cdc651b015126bdd18f184b7f90cc3` |
| `barlow-latin-700-normal.woff2` | `2d797dd8b35dcb3413e1af9d7052b3f4f8c341a147cdcb01f4f06af80db53289` |
| `barlow-semi-condensed-latin-600-normal.woff2` | `f158417e9207b5362f9b71a2fe779ce5bb836ad972f38445c3163af39d2c998d` |
| `barlow-semi-condensed-latin-700-normal.woff2` | `fb958c8c20a05552ac8a85d925d96028d52565792650e941a5fe96b6997aa5cb` |
| `LICENSE-Barlow.txt` | `4877e0c1b66f0b16cc3ebc4801c4def24c06252f618b9229428b20c7387aa0c0` |

Ni Barlow ni Noto Sans traen las flechas (↑ ↓ →). La plantilla dibuja con bordes los triángulos de «¿Qué cambió?» y usa «›» en lugar de «→». Así el PDF no toma letras de las fuentes del sistema.

Antes de Barlow, el reporte usó Noto Serif, IBM Plex y luego Exo 2 con Inter. Se borraron de esta carpeta, con la aprobación de Benji, porque ya nada las usaba. La interfaz conserva Exo 2 e Inter en `frontend/src/assets/fonts`.
