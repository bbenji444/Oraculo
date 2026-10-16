"""Lectura del GKG translingual de GDELT con un recorte del archivo real (16/10/2026)."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from app.adapters.ingest.gdelt_gkg import (
    GdeltGkgSource,
    GkgFileError,
    parse_lastupdate,
    parse_locations,
    parse_rows,
    read_zip,
    verify,
)
from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.ingest import GkgFile
from app.domain.queries import Provider
from app.geodata.fips import read_fips_to_inegi

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"
ZIP_NAME = "20261016191500.translation.gkg.csv.zip"
FIPS = read_fips_to_inegi()


def zip_bytes() -> bytes:
    return (FIXTURES / ZIP_NAME).read_bytes()


def announced() -> GkgFile:
    return parse_lastupdate((FIXTURES / "lastupdate-translation.txt").read_text(encoding="utf-8"))


def test_el_anuncio_trae_el_gkg_con_tamano_y_md5_en_https() -> None:
    file = announced()

    assert file.name == ZIP_NAME
    assert file.url.startswith("https://data.gdeltproject.org/gdeltv2/")
    # MD5 porque es la huella que publica GDELT; aquí no protege nada secreto.
    digest = hashlib.md5(zip_bytes(), usedforsecurity=False).hexdigest()
    assert (file.size, file.md5) == (len(zip_bytes()), digest)


def test_anuncio_sin_gkg_es_error() -> None:
    with pytest.raises(GkgFileError, match="no anuncia"):
        parse_lastupdate("1 abc http://x/20261016.export.CSV.zip\n")


def test_archivo_incompleto_o_alterado_se_rechaza() -> None:
    file = announced()
    verify(zip_bytes(), file)

    with pytest.raises(GkgFileError, match="bytes"):
        verify(zip_bytes()[:-10], file)
    with pytest.raises(GkgFileError, match="MD5"):
        verify(b"x" * file.size, file)


def test_zip_danado_es_error() -> None:
    with pytest.raises(GkgFileError, match="dañado"):
        read_zip(b"no es un zip")


def test_solo_entran_notas_en_espanol_con_mexico() -> None:
    rows = read_zip(zip_bytes())

    result = parse_rows(rows, FIPS)

    # El recorte trae 20 en español con México, 10 en español de otros
    # países y 10 en otros idiomas.
    assert result.seen == 40
    assert len(result.items) + result.discarded == 20
    assert all(item.language == "es" for item in result.items)
    assert all(item.source == "gdelt_gkg" for item in result.items)


def test_nota_real_con_titulo_sin_entidades_html_y_pistas_de_ubicacion() -> None:
    items = parse_rows(read_zip(zip_bytes()), FIPS).items
    nota = next(i for i in items if "extorsionador" in i.url)

    assert nota.title == "Cayó extorsionador tras cateo en Iztapalapa"
    assert nota.source_domain == "puentelibre.mx"
    assert nota.published_at == datetime(2026, 10, 16, 19, 15, tzinfo=UTC)
    # GDELT la ubicó (mal) en "Cuauhtémoc, Guerrero": queda solo como pista
    # (estado 12); la ubicación final la decide F4 con INEGI.
    assert nota.gdelt_states == ("12",)
    assert nota.text_norm.startswith("CAYO EXTORSIONADOR TRAS CATEO EN IZTAPALAPA")


def test_las_ubicaciones_se_leen_y_las_rotas_se_ignoran() -> None:
    locations = parse_locations(
        "4#Saltillo, Coahuila De Zaragoza, Mexico#MX#MX07#16290#25.4167#-101#-1#1;"
        "roto;"
        "1#Mexico#MX#MX##23#-102#MX#9"
    )

    assert [(loc.kind, loc.adm1) for loc in locations] == [(4, "MX07"), (1, "MX")]
    assert locations[0].lat == pytest.approx(25.4167)


@pytest.mark.anyio
async def test_baja_verifica_y_lee_con_transporte_simulado() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("lastupdate-translation.txt"):
            return httpx2.Response(
                200, text=(FIXTURES / "lastupdate-translation.txt").read_text(encoding="utf-8")
            )
        return httpx2.Response(200, content=zip_bytes())

    http = ProviderHttpClient(
        Provider.GDELT,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(handler),
    )
    source = GdeltGkgSource(http, FIPS)

    file = await source.latest()
    result, size = await source.fetch(file)

    assert size == len(zip_bytes())
    assert len(result.items) > 0
    await http.aclose()
