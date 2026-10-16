"""Lectura de los ngramas de GDELT con un recorte del minuto real 20261016224700."""

import base64
import gzip
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx2
import pytest

from app.adapters.ingest.gdelt_gkg import GkgFileError, file_from_headers
from app.adapters.ingest.gdelt_ngrams import (
    GdeltNgramsSource,
    TocEntry,
    build_items,
    minute_stamp,
    parse_ngrams,
    parse_toc,
)
from app.adapters.providers.http import ProviderHttpClient
from app.domain.news_index import BODY_SEPARATOR, MexicoMentions
from app.domain.queries import Provider

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest" / "ngrams"
STAMP = "20261016224700"
MOMENT = datetime(2026, 10, 16, 22, 47, tzinfo=UTC)
MENTIONS = MexicoMentions(["Ciudad de México", "CDMX", "Coahuila", "Sonora"])
CDMX = ZoneInfo("America/Mexico_City")
Handler = Callable[[httpx2.Request], httpx2.Response]


def raw(kind: str) -> bytes:
    return (FIXTURES / f"{STAMP}.{kind}").read_bytes()


def entries() -> list[TocEntry]:
    return parse_toc(gzip.decompress(raw("toc.json.gz")))


def test_el_indice_del_minuto_trae_idioma_titulo_y_fecha() -> None:
    toc = entries()

    assert len(toc) == 7
    spain = next(e for e in toc if e.doc_id == 1326)
    assert spain.language == "es"
    assert spain.title.startswith("La barriada cartagenera")
    assert spain.published_at == datetime(2026, 10, 16, 22, 47, tzinfo=UTC)


def test_una_linea_rota_del_indice_se_ignora() -> None:
    data = b'{"ID": 1, "lang": "es", "title": "A &amp; B", "url": "https://x.mx/a"}\nno es json\n'

    [entry] = parse_toc(data)

    assert entry.title == "A & B"
    assert entry.published_at is None


def test_solo_se_juntan_las_frases_de_las_notas_pedidas() -> None:
    phrases = parse_ngrams(gzip.decompress(raw("ngrams.txt.gz")), {1345})

    assert list(phrases) == [1345]
    assert len(phrases[1345]) == 30
    assert any("Tlalpan" in phrase for phrase in phrases[1345])


def test_entran_solo_las_notas_en_espanol_que_mencionan_mexico() -> None:
    toc = entries()
    spanish = {e.doc_id for e in toc if e.language == "es"}
    phrases = parse_ngrams(gzip.decompress(raw("ngrams.txt.gz")), spanish)

    result = build_items(toc, phrases, MENTIONS)

    # 3 de medios mexicanos; fuera: la de Cartagena (España), la que no trae
    # título (Venezuela, no es de México) y las 2 en inglés.
    assert result.seen == 7
    assert [item.source_domain for item in result.items] == [
        "vanguardia.com.mx",
        "eldiariodesonora.com.mx",
        "vanguardia.com.mx",
    ]
    assert result.discarded == 0
    casa = result.items[1]
    assert casa.source == "gdelt_ngrams"
    assert casa.title.startswith("Casa Tlalpan")
    assert casa.body_terms is not None
    assert len(casa.body_terms.split(BODY_SEPARATOR)) == 30


def test_una_nota_de_mexico_sin_titulo_cuenta_como_descartada() -> None:
    toc = parse_toc(
        b'{"ID": 7, "lang": "es", "title": "", "url": "https://x.com/a",'
        b' "date": "2026-10-16T22:47:00Z"}'
    )

    result = build_items(toc, {7: ["robo en la CDMX"]}, MENTIONS)

    assert (result.items, result.discarded) == ((), 1)


def test_el_sello_del_minuto_va_en_utc() -> None:
    assert minute_stamp(datetime(2026, 10, 16, 16, 47, 30, tzinfo=CDMX)) == STAMP


def test_tamano_y_md5_salen_de_los_encabezados_de_cloud_storage() -> None:
    # Encabezados reales del HEAD a 20261016224700.toc.json.gz aceptando
    # compresión: Google quita ETag y Content-Length, pero deja estos dos.
    headers = httpx2.Headers(
        [
            ("x-goog-stored-content-length", "412464"),
            ("x-goog-hash", "crc32c=L2N2hA=="),
            ("x-goog-hash", "md5=lYDctoiDbWsgeQjPyIueYw=="),
            ("content-encoding", "gzip"),
        ]
    )

    file = file_from_headers("https://x/a.toc.json.gz", headers)

    # Es el mismo valor que el ETag de la respuesta sin compresión.
    assert (file.size, file.md5) == (412_464, "9580dcb688836d6b207908cfc88b9e63")


def test_sin_tamano_o_md5_se_rechaza() -> None:
    with pytest.raises(GkgFileError, match="tamaño y MD5"):
        file_from_headers("https://x/a", httpx2.Headers({"x-goog-hash": "md5=%%%"}))


def gcs_headers(data: bytes) -> dict[str, str]:
    digest = base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode()
    return {"x-goog-stored-content-length": str(len(data)), "x-goog-hash": f"md5={digest}"}


def source(handler: Handler) -> GdeltNgramsSource:
    http = ProviderHttpClient(
        Provider.GDELT,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(handler),
    )
    return GdeltNgramsSource(http, MENTIONS)


@pytest.mark.anyio
async def test_mide_baja_verifica_y_lee_un_minuto_con_transporte_simulado() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        kind = "toc.json.gz" if request.url.path.endswith("toc.json.gz") else "ngrams.txt.gz"
        data = raw(kind)
        if request.method == "HEAD":
            return httpx2.Response(200, headers=gcs_headers(data))
        return httpx2.Response(200, content=data)

    ngrams = source(handler)

    minute = await ngrams.describe(MOMENT)
    assert minute is not None
    assert minute.key == ngrams.key_for(MOMENT)
    result, size = await ngrams.fetch(minute)

    assert size == minute.size == len(raw("toc.json.gz")) + len(raw("ngrams.txt.gz"))
    assert len(result.items) == 3
    await ngrams.aclose()


@pytest.mark.anyio
async def test_un_minuto_sin_archivos_no_es_error() -> None:
    ngrams = source(lambda request: httpx2.Response(404))

    assert await ngrams.describe(MOMENT) is None
    await ngrams.aclose()


@pytest.mark.anyio
async def test_un_minuto_a_medias_tampoco_se_procesa() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("toc.json.gz"):
            return httpx2.Response(200, headers=gcs_headers(raw("toc.json.gz")))
        return httpx2.Response(404)

    ngrams = source(handler)

    assert await ngrams.describe(MOMENT) is None
    await ngrams.aclose()


@pytest.mark.anyio
async def test_un_archivo_danado_es_error_claro() -> None:
    broken = b"no es gzip"

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "HEAD":
            return httpx2.Response(200, headers=gcs_headers(broken))
        return httpx2.Response(200, content=broken)

    ngrams = source(handler)
    minute = await ngrams.describe(MOMENT)
    assert minute is not None

    with pytest.raises(GkgFileError, match="dañado"):
        await ngrams.fetch(minute)
    await ngrams.aclose()
