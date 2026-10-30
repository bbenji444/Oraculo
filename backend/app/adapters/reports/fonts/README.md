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

## IBM Plex (tipografía del reporte desde el 30/10/2026)

Benji pidió «una tipografía más pro, que no parezca hecha en un documento de Word»: Noto Serif se parecía a Cambria o Georgia. El reporte usa **IBM Plex**, la familia corporativa de IBM, hecha para documentos técnicos:

- **IBM Plex Sans:** el texto, justificado;
- **IBM Plex Sans Condensed:** títulos, preguntas, titulares y cifras;
- **IBM Plex Mono:** horas, número de expediente y numeración.

Es el subconjunto latino en WOFF2 de `@fontsource` 5.3.0. Trae la Ñ, los acentos, «», las rayas y las comillas; si falta una letra, el PDF usa Noto Sans. Licencia SIL Open Font License 1.1 (`LICENSE-IBMPlex.txt`).

Descargadas el 30/10/2026 de `https://cdn.jsdelivr.net/npm/@fontsource/<familia>@5.3.0/files/<archivo>`.

| Archivo | SHA-256 |
|---|---|
| `ibm-plex-sans-latin-400-normal.woff2` | `3b646991d30055a93a4ecc499713d4347953a74a947ecab435ab72070cbdab0e` |
| `ibm-plex-sans-latin-400-italic.woff2` | `6de912e531b6c98084f1b2d5e5a91bad77be4e68bc4e396e43c46fc435e5f3d9` |
| `ibm-plex-sans-latin-600-normal.woff2` | `8960851d691c054ed38e259bdcf1a6190d157b4203ed5bb32c632a863fb8ec2f` |
| `ibm-plex-sans-latin-700-normal.woff2` | `42e7b0c143c19df9d99fd896e76b48f846edf0902d200bc29796b34d12c33aa7` |
| `ibm-plex-sans-condensed-latin-600-normal.woff2` | `3d72a0923c5830358b0a8e25b258aecadbecbf542b6ee9a25f387803e37d56b9` |
| `ibm-plex-sans-condensed-latin-700-normal.woff2` | `4768878c107d92c528a65bba206a87cdcf2c694514e75907fb91772cf8a388a5` |
| `ibm-plex-mono-latin-400-normal.woff2` | `08949f728dc52d528e69b1667d15c89a5686a4ee9a296ff90983985f99c380f7` |
| `ibm-plex-mono-latin-600-normal.woff2` | `0d1f0b8d0722224e32e9f28261bdc86c79115be73444ae5eceb73976a1bcdf83` |
| `LICENSE-IBMPlex.txt` | `d0283623ef57e722fd0eb688a8041589670c608ab780cd3612d06ba6f153d3fd` |

Antes de IBM Plex, el reporte usó unas horas Noto Serif y Noto Sans seminegrita. Se borraron el 30/10/2026, con la aprobación de Benji, porque ya nada las usaba.
