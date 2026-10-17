"""Extracción del texto de las notas (§9, paso 4; ADR-0015), sin red."""

from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest

from app.adapters.extraction.trafilatura_extractor import (
    PAGES,
    TrafilaturaExtractor,
    build_extractor,
)
from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.extraction import Extraction
from app.application.use_cases.extraction import ExtractTexts
from app.core.config import Settings
from app.domain.articles import RawArticle
from app.domain.dedupe import DedupedArticle
from app.domain.extraction import MIN_ARTICLE_CHARS, ExtractionStatus, processing_text
from app.domain.queries import Provider

PAGE = (Path(__file__).resolve().parents[1] / "fixtures" / "extraction" / "nota.html").read_text(
    encoding="utf-8"
)
TITLE = "Detienen a dos personas por extorsión en Iztapalapa"
LONG = "Detienen en Iztapalapa a dos personas por extorsión a comerciantes. " * 10


# --- Dominio ---


def test_un_cuerpo_suficiente_se_usa_tal_cual() -> None:
    result = processing_text(TITLE, "Fragmento", LONG)

    assert result.status is ExtractionStatus.OK
    assert result.text == LONG.strip()
    assert result.reason is None
    assert len(result.text_hash) == 64


@pytest.mark.parametrize(
    ("extracted", "failure", "reason"),
    [
        (None, "HTTP 403", "HTTP 403"),
        (None, None, "La página no trajo texto."),
        ("Suscríbete para leer.", None, "Texto muy corto"),
        ("Otra nota sobre el clima en Monterrey y sus lluvias. " * 10, None, "otra nota"),
    ],
)
def test_si_no_hay_cuerpo_util_se_usa_titulo_y_fragmento(
    extracted: str | None, failure: str | None, reason: str
) -> None:
    result = processing_text(TITLE, "Los detenidos exigían pagos.", extracted, failure)

    assert result.status is ExtractionStatus.FALLBACK
    assert result.text == f"{TITLE}. Los detenidos exigían pagos."
    assert result.reason is not None and reason in result.reason


def test_un_titulo_sin_palabras_largas_no_bloquea() -> None:
    assert processing_text("Ya", None, "x " * MIN_ARTICLE_CHARS).status is ExtractionStatus.OK


# --- Adaptador con una página grabada ---


def extractor(handler: Callable[[httpx2.Request], httpx2.Response]) -> TrafilaturaExtractor:
    http = ProviderHttpClient(
        PAGES,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=2,
        transport=httpx2.MockTransport(handler),
    )
    return TrafilaturaExtractor(http)


@pytest.mark.anyio
async def test_trafilatura_saca_el_cuerpo_sin_menus_ni_anuncios() -> None:
    reader = extractor(lambda request: httpx2.Response(200, text=PAGE))

    result = await reader.extract("https://medio.mx/nota")

    assert result.failure is None and result.text is not None
    assert "comerciantes de un mercado" in result.text
    assert "Publicidad" not in result.text
    assert "Deportes" not in result.text
    await reader.aclose()


@pytest.mark.anyio
async def test_una_pagina_bloqueada_no_rompe_y_dice_por_que() -> None:
    reader = extractor(lambda request: httpx2.Response(403, text="Prohibido"))

    result = await reader.extract("https://medio.mx/nota")

    assert result.text is None
    assert result.failure is not None and "403" in result.failure
    await reader.aclose()


@pytest.mark.anyio
async def test_una_pagina_sin_articulo_no_trae_cuerpo() -> None:
    reader = extractor(lambda request: httpx2.Response(200, text="<html><body></body></html>"))

    result = await reader.extract("https://medio.mx/nota")

    assert result.text is None and result.failure is not None
    await reader.aclose()


def test_la_fabrica_usa_la_configuracion() -> None:
    reader = build_extractor(
        Settings.model_construct(
            extraction_timeout_seconds=15, extraction_concurrency=4, provider_max_attempts=3
        )
    )

    assert isinstance(reader, TrafilaturaExtractor)


# --- Caso de uso ---


class FakeExtractor:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def extract(self, url: str) -> Extraction:
        self.urls.append(url)
        if "bloqueado" in url:
            return Extraction(None, "HTTP 403")
        return Extraction(LONG)


def deduped(url: str) -> DedupedArticle:
    article = RawArticle.create(
        provider=Provider.SEARCHAPI, provider_rank=1, url=url, title=TITLE, snippet="Fragmento."
    )
    return DedupedArticle(article, url.replace("?utm_source=x", ""), TITLE.upper())


@pytest.mark.anyio
async def test_extrae_todas_con_la_url_original_y_en_orden() -> None:
    fake = FakeExtractor()
    notes = [deduped("https://medio.mx/a?utm_source=x"), deduped("https://bloqueado.mx/b")]

    results = await ExtractTexts(fake, concurrency=2).run(notes)

    assert [r.text.status for r in results] == [ExtractionStatus.OK, ExtractionStatus.FALLBACK]
    assert fake.urls == ["https://medio.mx/a?utm_source=x", "https://bloqueado.mx/b"]
    assert results[1].text.reason == "HTTP 403"
