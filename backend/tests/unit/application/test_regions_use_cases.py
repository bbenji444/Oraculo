"""Casos de uso de regiones con un repositorio en memoria."""

import pytest

from app.application.pagination import NameCursor, decode_cursor, encode_cursor
from app.application.use_cases.regions import (
    FindRegionAtPoint,
    GetRegion,
    ListChildren,
    ListRegions,
    SearchRegions,
)
from app.domain.errors import InvalidRequestError, RegionNotFoundError
from app.domain.region import GeoPoint, RegionLevel
from tests.unit.fake_regions import CUAUHTEMOC, FakeRegionRepository

# --- Cursor -------------------------------------------------------------------


def test_cursor_ida_y_vuelta_conserva_la_enie() -> None:
    cursor = NameCursor("PEÑON BLANCO", 10021)

    token = encode_cursor(cursor)

    assert "=" not in token
    assert decode_cursor(token) == cursor


@pytest.mark.parametrize("token", ["no-es-base64!!", "W10", "WyJhIiwgImIiXQ"])
def test_cursor_danado_es_error_claro(token: str) -> None:
    with pytest.raises(InvalidRequestError, match="cursor"):
        decode_cursor(token)


# --- Listas paginadas -----------------------------------------------------------


@pytest.mark.anyio
async def test_lista_por_nivel_en_paginas_sin_repetir_ni_saltar() -> None:
    use_case = ListRegions(FakeRegionRepository())

    first = await use_case.execute(RegionLevel.MUNICIPALITY, limit=2)
    second = await use_case.execute(RegionLevel.MUNICIPALITY, first.next_cursor, limit=2)

    assert [r.name for r in first.items] == ["Cuauhtémoc", "Iztacalco"]
    assert [r.name for r in second.items] == ["Iztapalapa"]
    assert second.next_cursor is None


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [0, 201])
async def test_limite_fuera_de_rango(limit: int) -> None:
    with pytest.raises(InvalidRequestError, match="entre 1 y 200"):
        await ListRegions(FakeRegionRepository()).execute(RegionLevel.STATE, limit=limit)


@pytest.mark.anyio
async def test_hijas_de_una_region() -> None:
    page = await ListChildren(FakeRegionRepository()).execute(2)

    assert [r.code for r in page.items] == ["09015", "09006", "09007"]


@pytest.mark.anyio
async def test_hijas_de_una_region_inexistente() -> None:
    with pytest.raises(RegionNotFoundError):
        await ListChildren(FakeRegionRepository()).execute(999)


# --- Detalle ----------------------------------------------------------------------


@pytest.mark.anyio
async def test_detalle_con_ancestros() -> None:
    detail = await GetRegion(FakeRegionRepository()).execute(3)

    assert detail.breadcrumb == "México › Ciudad de México › Iztapalapa"


@pytest.mark.anyio
async def test_detalle_de_region_inexistente() -> None:
    with pytest.raises(RegionNotFoundError, match="No existe esa región") as info:
        await GetRegion(FakeRegionRepository()).execute(999)
    assert info.value.details == {"id": 999}


# --- Búsqueda ---------------------------------------------------------------------


@pytest.mark.anyio
async def test_busqueda_normaliza_como_el_cargador() -> None:
    repository = FakeRegionRepository()

    results = await SearchRegions(repository).execute("  iztá ")

    assert repository.last_search == ("IZTA", 10)
    assert {r.name for r in results} == {"Iztapalapa", "Iztacalco"}


@pytest.mark.anyio
@pytest.mark.parametrize("query", ["", "a", " é  "])
async def test_busqueda_exige_dos_letras(query: str) -> None:
    with pytest.raises(InvalidRequestError, match="al menos 2 letras"):
        await SearchRegions(FakeRegionRepository()).execute(query)


@pytest.mark.anyio
async def test_busqueda_limite_maximo_20() -> None:
    with pytest.raises(InvalidRequestError, match="entre 1 y 20"):
        await SearchRegions(FakeRegionRepository()).execute("izta", limit=21)


# --- Punto --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_region_en_un_punto() -> None:
    repository = FakeRegionRepository()
    repository.point_result = CUAUHTEMOC

    region = await FindRegionAtPoint(repository).execute(
        -99.1332, 19.4326, RegionLevel.MUNICIPALITY
    )

    assert region is CUAUHTEMOC
    assert repository.last_point == (GeoPoint(-99.1332, 19.4326), RegionLevel.MUNICIPALITY)


@pytest.mark.anyio
async def test_punto_sin_region_por_ejemplo_en_el_mar() -> None:
    with pytest.raises(RegionNotFoundError, match="No hay ninguna región"):
        await FindRegionAtPoint(FakeRegionRepository()).execute(-130.0, 10.0)


@pytest.mark.anyio
@pytest.mark.parametrize(("lon", "lat"), [(181.0, 0.0), (0.0, -91.0)])
async def test_coordenadas_fuera_de_rango(lon: float, lat: float) -> None:
    with pytest.raises(InvalidRequestError, match="fuera de rango"):
        await FindRegionAtPoint(FakeRegionRepository()).execute(lon, lat)
