"""Duplicados con Google web (ADR-0115): redes solo por link y títulos cortados."""

from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.text.similarity import title_similarity
from app.domain.articles import RawArticle
from app.domain.dedupe import (
    DedupedArticle,
    KnownArticle,
    Sighting,
    canonical_url,
    dedupe,
    match_known,
    refreshes_link,
)
from app.domain.names import normalize_name
from app.domain.queries import Provider

NOON = datetime(2026, 11, 17, 18, 0, tzinfo=UTC)
GOOGLE_NEWS = "https://news.google.com/rss/articles/CBMiHackean746"
QUINTA = "https://quintafuerza.mx/mexico/hackean-746-mil-cuentas-de-celular"
FULL = "Hackean 746 mil cuentas de celular, incluidas las de Pillofon"
CUT = "Hackean 746 mil cuentas de celular, incluidas las de"


def note(
    url: str,
    title: str,
    provider: Provider = Provider.SEARCHAPI_WEB,
    *,
    published: datetime | None = NOON,
    source: str | None = None,
    truncated: bool = False,
    rank: int = 1,
) -> RawArticle:
    return RawArticle.create(
        provider=provider,
        provider_rank=rank,
        url=url,
        title=title,
        published_at=published,
        source_name=source,
        title_truncated=truncated,
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://m.facebook.com/ivillasenor/posts/1", "https://facebook.com/ivillasenor/posts/1"),
        ("https://twitter.com/ivillasenor/status/1", "https://x.com/ivillasenor/status/1"),
        ("https://mobile.twitter.com/ivillasenor/status/1", "https://x.com/ivillasenor/status/1"),
        ("https://youtu.be/jMs7fCiEHRo?si=abc", "https://youtube.com/watch?v=jMs7fCiEHRo"),
        (
            "https://m.youtube.com/watch?v=jMs7fCiEHRo&feature=share",
            "https://youtube.com/watch?v=jMs7fCiEHRo",
        ),
        # El minuto del video sí cambia el link; los rastreadores de otros sitios no.
        ("https://youtu.be/jMs7fCiEHRo?t=30", "https://youtube.com/watch?t=30&v=jMs7fCiEHRo"),
        ("https://medio.mx/nota?si=1", "https://medio.mx/nota?si=1"),
    ],
)
def test_los_alias_de_cada_red_son_un_solo_link(url: str, expected: str) -> None:
    assert canonical_url(url) == expected


def test_la_misma_publicacion_por_dos_hosts_es_una() -> None:
    notes = [
        note("https://www.facebook.com/ivillasenor/posts/1", "Ignacio Gómez Villaseñor"),
        note(
            "https://m.facebook.com/ivillasenor/posts/1",
            "Ignacio Gómez Villaseñor",
            Provider.GOOGLE_NEWS_RSS,
            rank=4,
        ),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert kept.sightings == [Sighting("searchapi_web", 1), Sighting("google_news_rss", 4)]


def test_publicaciones_distintas_con_el_mismo_titulo_no_se_juntan() -> None:
    # Así vienen en la respuesta real: el título es el nombre de la página.
    notes = [
        note("https://x.com/ivillasenor/status/1", "Ignacio Gómez Villaseñor"),
        note("https://x.com/ivillasenor/status/2", "Ignacio Gómez Villaseñor", rank=2),
        note("https://www.facebook.com/ivillasenor/posts/3", "Ignacio Gómez Villaseñor", rank=3),
    ]

    assert len(dedupe(notes, title_similarity)) == 3


def test_una_red_no_se_junta_por_titulo_con_una_noticia() -> None:
    title = "El hacker Eternal ofrece 746 mil cuentas de celular a la venta"
    notes = [
        note("https://quintafuerza.mx/eternal", title, Provider.GOOGLE_NEWS_RSS),
        note("https://www.facebook.com/quintafuerza/posts/9", title),
    ]

    assert len(dedupe(notes, title_similarity)) == 2


def test_el_titulo_cortado_del_medio_reemplaza_al_link_de_google_news_y_queda_completo() -> None:
    notes = [
        note(GOOGLE_NEWS, FULL, Provider.GOOGLE_NEWS_RSS, source="Quinta Fuerza"),
        note(QUINTA, CUT, published=None, source="Quinta Fuerza", truncated=True, rank=5),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert kept.url_canonical == QUINTA
    assert (kept.article.title, kept.article.title_truncated) == (FULL, False)
    assert kept.title_norm == normalize_name(FULL)
    # Google web no dio fecha: se queda la de Google News.
    assert kept.article.published_at == NOON
    assert kept.sightings == [Sighting("google_news_rss", 1), Sighting("searchapi_web", 5)]


def test_si_llega_primero_el_cortado_toma_el_titulo_completo_despues() -> None:
    notes = [
        note(QUINTA, CUT, published=NOON - timedelta(days=2), truncated=True),
        note("https://otro.mx/hackean", FULL, Provider.GOOGLE_NEWS_RSS),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert kept.url_canonical == QUINTA
    assert (kept.article.title, kept.article.title_truncated) == (FULL, False)


@pytest.mark.parametrize(
    ("cut", "published"),
    [
        # Con menos de 6 palabras, un inicio genérico juntaría notas distintas.
        ("Detienen a dos", NOON),
        # Más de ±2 días: otro hecho con el mismo inicio.
        (CUT, NOON - timedelta(days=3)),
        # No es el inicio del título.
        ("Roban 746 mil cuentas de celular, incluidas las de", NOON),
    ],
)
def test_cortado_que_no_es_la_misma_nota(cut: str, published: datetime) -> None:
    full = FULL if cut != "Detienen a dos" else "Detienen a dos sujetos por robo en Iztapalapa"
    notes = [
        note(GOOGLE_NEWS, full, Provider.GOOGLE_NEWS_RSS),
        note(QUINTA, cut, published=published, truncated=True),
    ]

    assert len(dedupe(notes, title_similarity)) == 2


def test_sin_marca_de_cortado_el_inicio_del_titulo_no_basta() -> None:
    # Seis palabras de once: con la regla de siempre (§9, parecido de 0.72)
    # son notas distintas; solo el título que Google cortó cuenta como inicio.
    short = "Hackean 746 mil cuentas de celular"
    full = note(GOOGLE_NEWS, FULL, Provider.GOOGLE_NEWS_RSS)

    plain = dedupe([full, note(QUINTA, short, Provider.LOCAL_INDEX)], title_similarity)
    cut = dedupe([full, note(QUINTA, short, truncated=True)], title_similarity)

    assert (len(plain), len(cut)) == (2, 1)


def deduped(article: RawArticle) -> DedupedArticle:
    return DedupedArticle(article, canonical_url(article.url), normalize_name(article.title))


def test_una_publicacion_de_red_no_se_busca_por_titulo_en_lo_guardado() -> None:
    item = deduped(note("https://x.com/ivillasenor/status/1", "Ignacio Gómez Villaseñor"))
    known = KnownArticle(7, "https://x.com/ivillasenor/status/2", item.title_norm, NOON, "x.com")

    assert match_known(item, [known], title_similarity) is None


def test_una_noticia_no_se_junta_con_una_publicacion_guardada() -> None:
    title = "El hacker Eternal ofrece 746 mil cuentas de celular a la venta"
    item = deduped(note("https://quintafuerza.mx/eternal", title, Provider.GOOGLE_NEWS_RSS))
    social = KnownArticle(
        8, "https://facebook.com/quintafuerza/posts/9", item.title_norm, NOON, "facebook.com"
    )

    assert match_known(item, [social], title_similarity) is None


def test_un_cortado_reconoce_la_nota_guardada_con_el_titulo_completo() -> None:
    item = deduped(note(QUINTA, CUT, published=None, truncated=True))
    known = KnownArticle(1504, GOOGLE_NEWS, normalize_name(FULL), NOON, "quintafuerza.mx")

    found = match_known(item, [known], title_similarity)

    assert found == known
    assert refreshes_link(item, known) is True


def test_solo_el_link_de_google_news_se_cambia_por_el_del_medio() -> None:
    item = deduped(note(QUINTA, FULL))
    other_outlet = KnownArticle(3, "https://otro.mx/hackean", normalize_name(FULL), NOON)
    from_google = deduped(note(GOOGLE_NEWS, FULL, Provider.GOOGLE_NEWS_RSS))
    known_google = KnownArticle(4, GOOGLE_NEWS, normalize_name(FULL), NOON)

    assert refreshes_link(item, other_outlet) is False
    assert refreshes_link(from_google, known_google) is False


# --- Revisión del 18/11/2026 ---

INDEX_DATE = NOON - timedelta(hours=3)


def test_la_nota_web_sin_fecha_toma_la_del_rss_con_el_mismo_titulo() -> None:
    # Hallazgo 2: Google web llega primero (va antes en Provider) y casi nunca
    # trae fecha; la nota se guardaba sin fecha aunque el RSS sí la traía.
    title = "Detienen a Eternal, el hacker que expuso 746 mil cuentas de celular"
    notes = [
        note(QUINTA, title, published=None, source="Quinta Fuerza"),
        note(GOOGLE_NEWS, title, Provider.GOOGLE_NEWS_RSS, source="Quinta Fuerza", rank=2),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert kept.url_canonical == QUINTA
    assert kept.article.published_at == NOON
    assert kept.sightings == [Sighting("searchapi_web", 1), Sighting("google_news_rss", 2)]


def test_la_nota_web_sin_fecha_toma_la_del_indice_con_el_mismo_link() -> None:
    title = "Detienen a Eternal, el hacker que expuso 746 mil cuentas de celular"
    notes = [
        note(QUINTA, title, published=None),
        note(QUINTA, title, Provider.LOCAL_INDEX, published=INDEX_DATE, rank=3),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert (kept.article.provider, kept.article.published_at) == (
        Provider.SEARCHAPI_WEB,
        INDEX_DATE,
    )


def test_la_fecha_propia_no_se_cambia_por_la_de_la_otra_copia() -> None:
    title = "Detienen a Eternal, el hacker que expuso 746 mil cuentas de celular"
    notes = [
        note(QUINTA, title, published=NOON),
        note(QUINTA, title, Provider.LOCAL_INDEX, published=INDEX_DATE),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert kept.article.published_at == NOON


POST = "HACKEO MASIVO: ETERNAL expone 746 MIL cuentas de PILLOFON en Telegram"
FACEBOOK_POST = "https://www.facebook.com/ivillasenor/posts/pfbid02"


def social(
    url: str,
    title: str,
    provider: Provider,
    *,
    domain: str = "facebook.com",
    published: datetime | None = NOON,
    truncated: bool = False,
    rank: int = 1,
) -> RawArticle:
    # Google News RSS da la red en <source url> y su propio link (ADR-0021).
    return RawArticle.create(
        provider=provider,
        provider_rank=rank,
        url=url,
        title=title,
        published_at=published,
        source_domain=domain,
        title_truncated=truncated,
    )


def test_la_misma_publicacion_por_el_rss_y_por_google_web_es_una_con_el_link_real() -> None:
    # Hallazgo 7: el RSS trae el link de Google News y Google web el de Facebook.
    notes = [
        social(GOOGLE_NEWS, POST, Provider.GOOGLE_NEWS_RSS, rank=4),
        social(FACEBOOK_POST, POST, Provider.SEARCHAPI_WEB, published=None),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert kept.url_canonical == "https://facebook.com/ivillasenor/posts/pfbid02"
    assert kept.article.published_at == NOON
    assert kept.sightings == [Sighting("google_news_rss", 4), Sighting("searchapi_web", 1)]


def test_tambien_si_llega_primero_google_web_y_con_el_host_movil() -> None:
    notes = [
        social(
            "https://m.facebook.com/ivillasenor/posts/pfbid02",
            POST,
            Provider.SEARCHAPI_WEB,
            domain="m.facebook.com",
        ),
        social(GOOGLE_NEWS, POST, Provider.GOOGLE_NEWS_RSS, rank=2),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert kept.url_canonical == "https://facebook.com/ivillasenor/posts/pfbid02"


def test_el_titulo_cortado_de_google_web_tambien_es_la_misma_publicacion() -> None:
    cut = "HACKEO MASIVO: ETERNAL expone 746 MIL cuentas de"
    notes = [
        social(GOOGLE_NEWS, POST, Provider.GOOGLE_NEWS_RSS),
        social(FACEBOOK_POST, cut, Provider.SEARCHAPI_WEB, published=None, truncated=True),
    ]

    [kept] = dedupe(notes, title_similarity)

    assert kept.url_canonical == "https://facebook.com/ivillasenor/posts/pfbid02"
    assert (kept.article.title, kept.article.title_truncated) == (POST, False)


@pytest.mark.parametrize(
    "case",
    [
        # Otra red: no es la misma publicación aunque diga lo mismo.
        "otro_dominio",
        # Las dos con link real: dos publicaciones de la página con el mismo texto.
        "dos_links_reales",
        # El nombre de la página (corto) se repite en todas sus publicaciones.
        "titulo_corto",
        # Mismo texto pero de otra semana: otra publicación.
        "otra_fecha",
    ],
)
def test_publicaciones_que_no_se_juntan(case: str) -> None:
    rss_url, rss_title, rss_date, web_domain = GOOGLE_NEWS, POST, NOON, "facebook.com"
    if case == "otro_dominio":
        web_domain = "x.com"
    if case == "dos_links_reales":
        rss_url = "https://www.facebook.com/ivillasenor/posts/pfbid01"
    if case == "titulo_corto":
        rss_title = "Ignacio Gómez Villaseñor"
    if case == "otra_fecha":
        rss_date = NOON - timedelta(days=9)
    web_url = (
        FACEBOOK_POST if web_domain == "facebook.com" else "https://x.com/ivillasenor/status/9"
    )
    notes = [
        social(rss_url, rss_title, Provider.GOOGLE_NEWS_RSS, published=rss_date),
        social(web_url, rss_title, Provider.SEARCHAPI_WEB, domain=web_domain),
    ]

    assert len(dedupe(notes, title_similarity)) == 2


def test_la_publicacion_guardada_con_link_de_google_news_se_reconoce_con_el_real() -> None:
    item = deduped(social(FACEBOOK_POST, POST, Provider.SEARCHAPI_WEB, published=None))
    known = KnownArticle(21, GOOGLE_NEWS, normalize_name(POST), NOON, "facebook.com")
    other_post = KnownArticle(
        22,
        "https://facebook.com/ivillasenor/posts/pfbid01",
        normalize_name(POST),
        NOON,
        "facebook.com",
    )

    assert match_known(item, [other_post, known], title_similarity) == known
    assert refreshes_link(item, known) is True
