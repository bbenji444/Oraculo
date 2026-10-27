"""Quitar duplicados de una búsqueda (§9, paso 3), con la similitud real de rapidfuzz."""

from dataclasses import replace as dataclass_replace
from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.text.similarity import title_similarity
from app.domain.articles import RawArticle
from app.domain.dedupe import (
    KnownArticle,
    Sighting,
    canonical_url,
    dedupe,
    is_google_news,
    match_known,
    url_hash,
)
from app.domain.names import normalize_name
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


# Par real de la base (24/10/2026): la misma nota de infobae guardada con el
# link de Google News (RSS) y con el del medio.
MICKY = "Reportan orden de aprehensión contra empresario por el asesinato de Micky Hernández"
GOOGLE_URL = "https://news.google.com/rss/articles/CBMiXkFVX3lxTE1"


def known(article_id: int, url: str, title: str, published: datetime | None = NOON) -> KnownArticle:
    return KnownArticle(article_id, canonical_url(url), normalize_name(title), published)


def test_reconoce_links_de_google_news() -> None:
    assert is_google_news(GOOGLE_URL)
    assert not is_google_news("https://www.infobae.com/mexico/2026/10/22/micky")


def test_en_el_grupo_gana_el_link_del_medio() -> None:
    google = article(GOOGLE_URL, MICKY, Provider.GOOGLE_NEWS_RSS, 1)
    medio = article("https://www.infobae.com/mexico/micky", MICKY, Provider.SEARCHAPI, 4)

    [kept] = dedupe([google, medio], title_similarity)

    assert kept.url_canonical == "https://infobae.com/mexico/micky"
    assert kept.article is medio
    assert [s.provider for s in kept.sightings] == ["google_news_rss", "searchapi"]


def test_misma_nota_guardada_con_otro_link() -> None:
    [new] = dedupe([article("https://www.infobae.com/mexico/micky", MICKY)], title_similarity)
    candidates = [
        known(1, "https://otro.mx/nota", "Detienen a empresario en Polanco"),
        known(2, GOOGLE_URL, MICKY),
    ]

    match = match_known(new, candidates, title_similarity)

    assert match is not None
    assert match.article_id == 2


@pytest.mark.parametrize(
    "candidate",
    [
        # Mismo título pero tres días después: otra nota (§9, ±1 día).
        known(2, GOOGLE_URL, MICKY, NOON + timedelta(days=3)),
        # Título distinto.
        known(2, GOOGLE_URL, "Vinculan a proceso a El Cromos, ligado al CJNG"),
        # La misma URL ya la resuelve el nivel 1; no es «otro link».
        known(2, "https://infobae.com/mexico/micky", MICKY),
    ],
)
def test_no_es_la_misma_nota_guardada(candidate: KnownArticle) -> None:
    [new] = dedupe([article("https://www.infobae.com/mexico/micky", MICKY)], title_similarity)

    assert match_known(new, [candidate], title_similarity) is None


def test_guardada_sin_fecha_solo_cuenta_el_titulo_identico() -> None:
    [new] = dedupe([article("https://infobae.com/m", MICKY, published=None)], title_similarity)

    assert match_known(new, [known(2, GOOGLE_URL, MICKY, None)], title_similarity) is not None
    assert match_known(new, [known(2, GOOGLE_URL, MICKY + ".", None)], title_similarity) is None


# Par real (auditoría del 27/10/2026): Google News volvió a dar la nota de
# oem.com.mx tres días después, con otra liga.
DON_RODO = "Don Rodo, hermano de El Mencho, gana amparo a la FGR"


def outlet_known(
    title: str, domain: str | None, published: datetime = NOON - timedelta(days=3)
) -> KnownArticle:
    return KnownArticle(
        7,
        canonical_url("https://oem.com.mx/la-prensa/don-rodo"),
        normalize_name(title),
        published,
        domain,
    )


def test_el_mismo_medio_con_el_mismo_titulo_dias_despues_es_la_misma_nota() -> None:
    [new] = dedupe([article(GOOGLE_URL, DON_RODO, Provider.GOOGLE_NEWS_RSS)], title_similarity)
    new.article = replace_domain(new.article, "oem.com.mx")

    match = match_known(new, [outlet_known(DON_RODO, "oem.com.mx")], title_similarity)

    assert match is not None and match.article_id == 7


@pytest.mark.parametrize(
    "candidate",
    [
        # Otro medio con el mismo título: puede ser otra nota (agencias, refritos).
        outlet_known(DON_RODO, "milenio.com"),
        # Fuera de la semana.
        outlet_known(DON_RODO, "oem.com.mx", NOON - timedelta(days=8)),
        # Título corto: las columnas repiten su nombre cada día.
        outlet_known("Portafolios Político", "oem.com.mx"),
    ],
)
def test_mismo_medio_no_basta_sin_titulo_largo_identico_y_cercano(candidate: KnownArticle) -> None:
    title = "Portafolios Político" if "PORTAFOLIOS" in candidate.title_norm else DON_RODO
    [new] = dedupe([article(GOOGLE_URL, title, Provider.GOOGLE_NEWS_RSS)], title_similarity)
    new.article = replace_domain(new.article, "oem.com.mx")

    assert match_known(new, [candidate], title_similarity) is None


def replace_domain(raw: RawArticle, domain: str) -> RawArticle:
    return dataclass_replace(raw, source_domain=domain)
