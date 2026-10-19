"""Endpoints de reporte y exportación con puertos en memoria (§13, §15, ADR-0018)."""

from collections.abc import Iterator
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.reports.render import ReportRenderer
from app.api.v1.concepts import get_actor
from app.api.v1.reports import (
    file_name,
    get_report_builder,
    get_report_documents,
    get_search_exporter,
)
from app.application.ports.search_reads import ConceptRef, SearchDetail
from app.application.use_cases.reports import ExportSearch
from app.domain.search import SearchStatus
from app.main import create_app
from tests.unit.application.test_reports_use_case import (
    ACTOR,
    IZTAPALAPA_NOTE,
    NOW,
    Articles,
    Reader,
    Store,
    build,
    search,
)
from tests.unit.fake_regions import FakeRegionRepository

FINISHED = search()
RUNNING = search(SearchStatus.RUNNING)


def make_client(row: SearchDetail) -> TestClient:
    app: FastAPI = create_app()
    builder = build(row, rows=(IZTAPALAPA_NOTE,))
    exporter = ExportSearch(
        Reader(row), Articles([IZTAPALAPA_NOTE]), FakeRegionRepository(), Store(), lambda: NOW
    )
    documents = ReportRenderer()
    app.dependency_overrides[get_report_builder] = lambda: builder
    app.dependency_overrides[get_search_exporter] = lambda: exporter
    app.dependency_overrides[get_report_documents] = lambda: documents
    app.dependency_overrides[get_actor] = lambda: ACTOR
    # Sin `with`: no corre el lifespan, así que no se conecta a la base.
    return TestClient(app)


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield make_client(FINISHED)


def url(path: str, row: SearchDetail = FINISHED) -> str:
    return f"/api/v1/searches/{row.search_id}/{path}"


def test_el_pdf_se_descarga_con_un_nombre_legible(client: TestClient) -> None:
    response = client.post(url("report"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="reporte-extorsion-ciudad-de-mexico-2026-10-17.pdf"'
    )
    assert response.content.startswith(b"%PDF")


def test_el_html_se_ve_en_el_navegador(client: TestClient) -> None:
    response = client.post(url("report"), params={"format": "html"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Resumen ejecutivo" in response.text
    assert "content-disposition" not in response.headers


@pytest.mark.parametrize(
    ("fmt", "media", "extension"),
    [("csv", "text/csv; charset=utf-8", "csv"), ("geojson", "application/geo+json", "geojson")],
)
def test_los_datos_se_descargan(client: TestClient, fmt: str, media: str, extension: str) -> None:
    response = client.get(url("export"), params={"format": fmt})

    assert response.status_code == 200
    assert response.headers["content-type"] == media
    assert response.headers["content-disposition"].endswith(f'.{extension}"')
    assert "Iztapalapa" in response.content.decode("utf-8-sig")


@pytest.mark.parametrize(("method", "path"), [("post", "report"), ("get", "export")])
def test_una_busqueda_que_corre_responde_409(method: str, path: str) -> None:
    response = getattr(make_client(RUNNING), method)(url(path, RUNNING))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "search_not_finished"


def test_busqueda_inexistente_es_404(client: TestClient) -> None:
    response = client.post(f"/api/v1/searches/{uuid4()}/report")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "search_not_found"


def test_formato_desconocido_es_422(client: TestClient) -> None:
    response = client.post(url("report"), params={"format": "docx"})

    assert response.status_code == 422


def test_el_nombre_del_archivo_quita_acentos_y_enie() -> None:
    row = replace(
        FINISHED,
        concepts=(ConceptRef(5, "Desaparición de personas"),),
        region_name="Peñón Blanco",
    )

    assert file_name(row, "pdf") == "reporte-desaparicion-de-personas-penon-blanco-2026-10-17.pdf"
