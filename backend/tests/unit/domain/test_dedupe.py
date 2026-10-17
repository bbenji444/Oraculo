"""Quitar duplicados de una búsqueda (§9, paso 3), con la similitud real de rapidfuzz."""

from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.text.similarity import title_similarity
from app.domain.articles import RawArticle
from app.domain.dedupe import Sighting, canonical_url, dedupe, url_hash
from app.domain.queries import Provider

NOON = datetime(2026, 10, 15, 18, 0, tzinfo=UTC)


def article(
    url: str,
    title: str,
    provider: Provider = Provider.SEARCHAPI,
    rank: int = 1,
    published: datetime | None = NOON,
) -> RawArticle:
    return RawArticle.create(
        provider=provider, provider_rank=rank, url=url, title=title, published_at=published
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "http://www.Milenio.com/nota/?utm_source=x&id=2#top",
            "https://milenio.com/nota?id=2",
        ),
        ("https://milenio.com/nota?b=2&a=1&fbclid=XYZ", "https://milenio.com/nota?a=1&b=2"),
        (
            "https://www.eluniversal.com.mx/nacion/nota/?outputType=amp",
            "https://eluniversal.com.mx/nacion/nota",
        ),
        ("https://medio.mx/politica/nota/amp", "https://medio.mx/politica/nota"),
        ("https://medio.mx", "https://medio.mx/"),
        ("https://medio.mx:8443/a", "https://medio.mx:8443/a"),
    ],
)
def test_url_canonica(url: str, expected: str) -> None:
    assert canonical_url(url) == expected


def test_la_huella_es_estable() -> None:
    assert url_hash("https://milenio.com/a") == url_hash("https://milenio.com/a")
    assert len(url_hash("https://milenio.com/a")) == 64


def test_la_misma_url_decorada_es_la_misma_nota() -> None:
    notes = [
        article("https://www.milenio.com/nota?utm_source=fb", "Hackeo en Iztapalapa"),
        article("https://milenio.com/nota", "Hackeo en Iztapalapa", Provider.LOCAL_INDEX, rank=7),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert kept.url_canonical == "https://milenio.com/nota"
    assert kept.sightings == [Sighting("searchapi", 1), Sighting("indice_local", 7)]


def test_titulo_casi_igual_el_mismo_dia_es_la_misma_nota() -> None:
    notes = [
        article("https://milenio.com/a", "Hackeo en la alcaldía Iztapalapa"),
        article(
            "https://infobae.com/b",
            "Hackeo a la alcaldía Iztapalapa",
            Provider.LOCAL_INDEX,
            published=NOON + timedelta(hours=20),
        ),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert len(kept.sightings) == 2
    assert kept.article.url == "https://milenio.com/a"


def test_titulo_parecido_pero_dias_distintos_son_notas_distintas() -> None:
    notes = [
        article("https://milenio.com/a", "Hackeo en la alcaldía Iztapalapa"),
        article(
            "https://infobae.com/b",
            "Hackeo en la alcaldía Iztapalapa",
            published=NOON + timedelta(days=3),
        ),
    ]

    assert len(dedupe(notes, title_similarity)) == 2


def test_titulos_distintos_son_notas_distintas() -> None:
    notes = [
        article("https://milenio.com/a", "Hackeo en la alcaldía Iztapalapa"),
        article("https://milenio.com/b", "Secuestran a empresario en Monterrey"),
    ]

    assert len(dedupe(notes, title_similarity)) == 2


def test_sin_fecha_solo_cuenta_el_titulo_identico() -> None:
    notes = [
        article("https://a.mx/1", "Hackeo en Iztapalapa", published=None),
        article("https://b.mx/2", "Hackeo en Iztapalapa", rank=2, published=None),
        article("https://c.mx/3", "Hackeo a Iztapalapa", rank=3, published=None),
    ]

    kept = dedupe(notes, title_similarity)

    assert [len(k.sightings) for k in kept] == [2, 1]


def test_un_proveedor_no_se_repite_en_la_misma_nota() -> None:
    same = article("https://milenio.com/a", "Hackeo")

    [kept] = dedupe([same, same], title_similarity)

    assert kept.sightings == [Sighting("searchapi", 1)]
