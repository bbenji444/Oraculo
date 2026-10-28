"""Reporte en HTML y PDF, y datos en CSV y GeoJSON, sin base ni IA (§15, ADR-0018)."""

import csv
import io
import json
from dataclasses import replace
from typing import cast

import pytest
from pypdf import PdfReader
from pypdf.generic import DictionaryObject

from app.adapters.reports.exports import CSV_COLUMNS, to_csv, to_geojson
from app.adapters.reports.render import ReportRenderer, paragraphs
from app.application.ports.reports import ProviderUsage
from app.application.ports.search_reads import JudgementView
from app.application.use_cases.reports import ExportData, ReportData, ReportFormat
from tests.unit.application.test_reports_use_case import (
    ACTOR,
    IZTAPALAPA_NOTE,
    NOW,
    STATE_NOTE,
    UNLOCATED_NOTE,
    Summarizer,
    build,
    search,
)

pytestmark = pytest.mark.anyio

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    '<rect width="10" height="5"/></svg>'
)
# Un título con HTML y uno que Excel tomaría por fórmula: llegan de la web.
HOSTILE = replace(IZTAPALAPA_NOTE, title='<script>alert("x")</script> Cobro de piso en Peñón')
FORMULA = replace(STATE_NOTE, title='=HYPERLINK("http://malo")')


@pytest.fixture
async def report() -> ReportData:
    row = search()
    data = await build(
        row, rows=(HOSTILE, FORMULA, UNLOCATED_NOTE), summarizer=Summarizer()
    ).execute(row.search_id, ReportFormat.PDF, ACTOR)
    return replace(
        data,
        map_svg=SVG,
        summary="Predomina el cobro de piso.\n\nSe concentra en Iztapalapa.",
        providers=(
            ProviderUsage("searchapi", 1, 12, 1, 0, 0),
            ProviderUsage("indice_local", 1, 3, 0, 0, 0),
        ),
    )


def test_los_parrafos_se_separan_por_lineas_en_blanco() -> None:
    assert paragraphs("Uno.\n\n  Dos.\n\n\n") == ["Uno.", "Dos."]


async def test_el_html_lleva_todas_las_secciones_y_escapa_lo_de_la_web(
    report: ReportData,
) -> None:
    page = ReportRenderer().html(report)

    for section in (
        "Panorama",
        "Resumen ejecutivo",
        "Datos clave",
        "Notas por categoría",
        "Distribución geográfica",
        "Notas por municipio",
        "Línea del tiempo",
        "Medios con más notas",
        "Noticias por estado",
        "Metodología y fuentes",
    ):
        assert section in page
    # Rediseño Oráculo (F12.10): expediente, confidencialidad e insignias.
    assert "EXP-20261017-1400" in page
    assert "USO INTERNO · CONFIDENCIAL" in page
    assert "IA · INFERENCIA" in page
    assert 'class="ins ins-confidence"' in page
    # Noticias por Estado ▸ Categoría, numeradas de corrido.
    assert 'class="state-title">Ciudad de México' in page
    assert 'class="state-title">Sin estado identificado' in page
    assert '<span class="number">3</span>' in page
    assert "México › Ciudad de México" in page
    assert "<p>Predomina el cobro de piso.</p>" in page
    assert "<p>Se concentra en Iztapalapa.</p>" in page
    assert "Generado por IA · gpt-6-luna" in page
    # El HTML de un título nunca se ejecuta; el SVG del mapa sí va tal cual.
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert SVG in page
    # Tabla por alcaldía, con lo poco preciso, lo de fuera y lo sin ubicación aparte.
    assert '<td class="name">Iztapalapa</td>' in page
    assert "En la región, sin municipio preciso" in page
    assert "Fuera de la región" in page
    # Proveedores con su nombre para personas y la cita de GDELT (§8).
    assert "Google News (SearchApi)" in page
    assert "Incluye datos de The GDELT Project" in page
    assert "<style>" in page


async def test_sin_resumen_se_lee_el_aviso(report: ReportData) -> None:
    page = ReportRenderer().html(replace(report, summary=None, summary_notice="Falta la llave."))

    assert "Falta la llave." in page
    assert "Generado por IA" not in page


async def test_el_pdf_trae_la_n_y_los_acentos_con_la_fuente_incluida(report: ReportData) -> None:
    pdf = ReportRenderer().pdf(report)

    assert pdf.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Peñón" in text
    assert "México › Ciudad de México" in text
    assert "Resumen ejecutivo" in text
    # La portada no lleva número; las demás, expediente y confidencialidad.
    assert "Página 2 de" in text
    assert "USO INTERNO · CONFIDENCIAL" in text
    assert "EXP-20261017-1400" in text
    # Marcadores plegables Estado ▸ Categoría ▸ Nota en el lector de PDF.
    titles = [item.title for item in reader.outline if not isinstance(item, list)]
    assert "Noticias por estado" in titles
    fonts = set()
    for page in reader.pages:
        # pypdf tipa cada valor como PdfObject; aquí son diccionarios del PDF.
        resources = cast(DictionaryObject, page["/Resources"])
        for font in cast(DictionaryObject, resources["/Font"]).values():
            fonts.add(str(cast(DictionaryObject, font.get_object())["/BaseFont"]))
    # WeasyPrint nombra la fuente con la familia del @font-face (report.css).
    assert any("Noto-Sans-Reporte" in name for name in fonts)
    assert any("Orbitron-Reporte" in name for name in fonts)
    assert not any("DejaVu" in name for name in fonts)


def export(report: ReportData) -> ExportData:
    return ExportData(report.search, report.breadcrumb, report.articles, NOW)


async def test_csv_para_excel_con_bom_y_sin_formulas(report: ReportData) -> None:
    raw = to_csv(export(report))

    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert len(rows) == 1 + 3
    first = dict(zip(CSV_COLUMNS, rows[1], strict=True))
    assert first["titulo"].endswith("Cobro de piso en Peñón")
    assert (first["lugar"], first["precision"], first["dentro_de_la_region"]) == (
        "Alcaldía Iztapalapa",
        "Municipio",
        "sí",
    )
    assert first["publicada"] == "15/10/2026 18:00"
    # Una fórmula en el título se guarda como texto.
    assert rows[2][0] == '\'=HYPERLINK("http://malo")'
    assert rows[3][CSV_COLUMNS.index("precision")] == "Sin ubicación"


async def test_conceptos_relevantes_en_el_csv(report: ReportData) -> None:
    judged = replace(
        report.articles[0],
        judgements=(
            JudgementView(3, "Extorsión", True, 0.9, None),
            JudgementView(5, "Secuestro", False, 0.1, None),
        ),
    )

    raw = to_csv(ExportData(report.search, report.breadcrumb, (judged,), NOW))

    row = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))[1]
    assert row[CSV_COLUMNS.index("conceptos")] == "Extorsión"


async def test_geojson_con_un_punto_por_nota_ubicada(report: ReportData) -> None:
    collection = json.loads(to_geojson(export(report)))

    assert collection["type"] == "FeatureCollection"
    assert collection["busqueda"]["region"] == "México › Ciudad de México"
    # La nota sin ubicación no tiene punto.
    assert len(collection["features"]) == 2
    feature = collection["features"][0]
    assert feature["geometry"] == {"type": "Point", "coordinates": [-99.1, 19.4]}
    assert feature["properties"]["lugar"] == "Alcaldía Iztapalapa"
    assert "latitud" not in feature["properties"]


async def test_el_reporte_responde_las_preguntas_del_analista(report: ReportData) -> None:
    # Rediseño del 28/10/2026: cada bloque abre con una pregunta numerada.
    page = ReportRenderer().html(report)

    for question in (
        "¿Qué pasó en este periodo?",
        "¿Qué es lo más importante?",
        "¿De qué delitos se trata?",
        "¿Qué tipo de actuación hubo?",
        "¿Dónde pasó?",
        "¿Qué pasa en cada estado?",
        "¿Cuándo pasó?",
        "¿Qué tan confiable es la información?",
    ):
        assert question in page
    # Tipografía formal: Orbitron solo en la marca de la portada.
    assert '--tech: "Noto Sans Reporte", sans-serif;' in page
