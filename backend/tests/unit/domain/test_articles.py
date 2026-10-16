"""Formato común de una nota (RawArticle) y errores de proveedor."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from app.domain.articles import InvalidArticleError, RawArticle, domain_of
from app.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.domain.queries import Provider

MEXICO_CITY = timezone(timedelta(hours=-6))


def article(**overrides: Any) -> RawArticle:
    data: dict[str, Any] = {
        "provider": Provider.GDELT,
        "provider_rank": 1,
        "url": "https://www.ElUniversal.com.mx/metropoli/ataque",
        "title": "  Alcaldía   sufre ataque de ransomware ",
    }
    data.update(overrides)
    return RawArticle.create(**data)


def test_limpia_el_titulo_y_toma_el_dominio_de_la_url() -> None:
    item = article()

    assert item.title == "Alcaldía sufre ataque de ransomware"
    assert item.source_domain == "eluniversal.com.mx"
    assert item.published_at is None
    assert item.raw == {}


def test_respeta_el_dominio_que_da_el_proveedor() -> None:
    # Google News RSS: el link es de Google, el medio llega aparte.
    item = article(url="https://news.google.com/rss/articles/CBMi", source_domain="Milenio.com")

    assert item.source_domain == "milenio.com"


def test_la_fecha_se_guarda_en_utc() -> None:
    item = article(published_at=datetime(2026, 10, 12, 8, 5, tzinfo=MEXICO_CITY))

    assert item.published_at == datetime(2026, 10, 12, 14, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"url": "javascript:alert(1)"}, "URL"),
        ({"url": "/relativa"}, "URL"),
        ({"title": "   "}, "título"),
        ({"title": None}, "título"),
        ({"provider_rank": 0}, "Posición"),
        ({"published_at": datetime(2026, 10, 12, 8, 5)}, "zona horaria"),  # noqa: DTZ001 — se prueba justo la fecha sin zona
    ],
)
def test_resultados_inutilizables_se_rechazan(overrides: dict[str, Any], fragment: str) -> None:
    with pytest.raises(InvalidArticleError, match=fragment):
        article(**overrides)


def test_dominio_de_una_url() -> None:
    assert domain_of("https://www.Milenio.com/policia") == "milenio.com"
    assert domain_of("https://aristeguinoticias.com/x") == "aristeguinoticias.com"


def test_errores_de_proveedor_dicen_si_conviene_reintentar() -> None:
    auth = ProviderAuthError("Llave rechazada.", provider="searchapi", http_status=401)

    assert auth.retryable is False
    assert auth.details == {"proveedor": "searchapi"}
    assert ProviderRateLimitError("x", provider="gdelt").retryable is True
    assert ProviderUnavailableError("x", provider="gdelt").retryable is True
    assert ProviderResponseError("x", provider="gdelt").retryable is False
