"""Columna «plataforma» del CSV y ``platform`` de la API (ADR-0115)."""

import csv
import io
from dataclasses import replace

from app.adapters.reports.exports import CSV_COLUMNS, to_csv
from app.adapters.reports.labels import PROVIDER_LABEL
from app.api.v1.schemas.articles import ArticleOut
from app.application.use_cases.reports import ExportData
from tests.unit.application.test_reports_use_case import NOW, item, search

NEWS_NOTE = item(1)
FACEBOOK_POST = replace(
    item(2),
    source_name="Facebook · Ignacio Gómez Villaseñor",
    source_domain="facebook.com",
    url="https://www.facebook.com/ignacio.gomez/posts/123",
    providers=("searchapi_web",),
)
OTHER_SITE = replace(
    item(3),
    source_name="Quinta Fuerza",
    source_domain="quintafuerza.mx",
    url="https://quintafuerza.mx/nota",
    providers=("searchapi_web",),
)


def rows() -> list[dict[str, str]]:
    data = ExportData(search(), "México", (NEWS_NOTE, FACEBOOK_POST, OTHER_SITE), NOW)
    raw = to_csv(data)
    header, *body = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    return [dict(zip(header, row, strict=True)) for row in body]


def test_el_csv_dice_en_que_plataforma_se_publico_cada_nota() -> None:
    assert CSV_COLUMNS.index("plataforma") == CSV_COLUMNS.index("medio") + 1
    assert [r["plataforma"] for r in rows()] == ["Noticias", "Facebook", "Otros sitios"]


def test_el_csv_nombra_google_web_como_proveedor() -> None:
    assert rows()[1]["proveedores"] == "Google web (SearchApi)"
    assert PROVIDER_LABEL["searchapi_web"] == "Google web (SearchApi)"


def test_la_api_entrega_la_plataforma_calculada_al_leer() -> None:
    assert [ArticleOut.from_item(n).platform for n in (NEWS_NOTE, FACEBOOK_POST, OTHER_SITE)] == [
        "news",
        "facebook",
        "web",
    ]
