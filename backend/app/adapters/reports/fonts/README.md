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
