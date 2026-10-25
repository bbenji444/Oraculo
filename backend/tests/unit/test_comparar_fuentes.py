"""Comparación SearchApi contra Google News RSS (F12.2): la clasificación, sin red."""

from datetime import UTC, datetime

from app.cli.comparar_fuentes import compare
from app.domain.articles import RawArticle
from app.domain.queries import Provider

NOON = datetime(2026, 10, 24, 18, 0, tzinfo=UTC)


def raw(provider: Provider, url: str, title: str, snippet: str | None = None) -> RawArticle:
    return RawArticle.create(
        provider=provider, provider_rank=1, url=url, title=title, published_at=NOON, snippet=snippet
    )


def test_clasifica_quien_trajo_cada_nota() -> None:
    result = compare(
        [
            raw(Provider.SEARCHAPI, "https://milenio.com/cateo", "Cateo de la FGR en Monterrey"),
            raw(
                Provider.GOOGLE_NEWS_RSS,
                "https://news.google.com/rss/articles/CBMi1",
                "Cateo de la FGR en Monterrey",
            ),
            raw(
                Provider.SEARCHAPI,
                "https://infobae.com/fgr",
                "La FGR asegura armas en Sinaloa",
                snippet="Elementos de la FGR…",
            ),
            raw(
                Provider.GOOGLE_NEWS_RSS,
                "https://news.google.com/rss/articles/CBMi2",
                "Detienen a exfiscal en Chihuahua",
            ),
        ]
    )

    assert result.by_source == {"searchapi": 2, "google_news_rss": 2}
    assert [d.article.title for d in result.both] == ["Cateo de la FGR en Monterrey"]
    assert [d.article.title for d in result.only_searchapi] == ["La FGR asegura armas en Sinaloa"]
    assert [d.article.title for d in result.only_rss] == ["Detienen a exfiscal en Chihuahua"]


def test_sin_notas() -> None:
    result = compare([])

    assert result.by_source == {"searchapi": 0, "google_news_rss": 0}
    assert (result.only_searchapi, result.only_rss, result.both) == ([], [], [])
