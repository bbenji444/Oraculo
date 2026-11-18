"""Plataforma de cada nota: red social, noticia u otro sitio (ADR-0115)."""

import pytest

from app.domain.platforms import (
    PLATFORM_LABELS,
    Platform,
    is_google_redirect,
    is_social,
    platform_of,
    social_platform,
)

WEB = ("searchapi_web",)
RSS = ("google_news_rss",)


def test_los_valores_son_el_contrato_con_la_pantalla() -> None:
    assert [p.value for p in Platform] == [
        "news",
        "facebook",
        "x",
        "youtube",
        "instagram",
        "tiktok",
        "reddit",
        "telegram",
        "web",
    ]
    assert [PLATFORM_LABELS[p] for p in Platform] == [
        "Noticias",
        "Facebook",
        "X",
        "YouTube",
        "Instagram",
        "TikTok",
        "Reddit",
        "Telegram",
        "Otros sitios",
    ]


@pytest.mark.parametrize(
    ("domain", "url", "expected"),
    [
        ("facebook.com", "https://www.facebook.com/metronewsmx/posts/1", Platform.FACEBOOK),
        (None, "https://m.facebook.com/x/posts/1", Platform.FACEBOOK),
        (None, "https://fb.watch/abc/", Platform.FACEBOOK),
        ("x.com", "https://x.com/ivillasenor/status/1", Platform.X),
        (None, "https://twitter.com/ivillasenor/status/1", Platform.X),
        (None, "https://www.youtube.com/watch?v=jMs7fCiEHRo", Platform.YOUTUBE),
        (None, "https://youtu.be/jMs7fCiEHRo", Platform.YOUTUBE),
        (None, "https://www.instagram.com/p/abc/", Platform.INSTAGRAM),
        (None, "https://www.tiktok.com/@u/video/1", Platform.TIKTOK),
        (None, "https://www.reddit.com/r/mexico/comments/1", Platform.REDDIT),
        (None, "https://t.me/canal/1", Platform.TELEGRAM),
    ],
)
def test_red_social_por_dominio_exacto_o_subdominio(
    domain: str | None, url: str, expected: Platform
) -> None:
    assert platform_of(domain, url, WEB) is expected


def test_un_dominio_que_solo_termina_igual_no_es_la_red() -> None:
    # «box.com» termina en «x.com» pero no es X.
    assert social_platform("box.com") is None
    assert platform_of("box.com", "https://box.com/s/1", WEB) is Platform.WEB
    assert platform_of("notfacebook.com", "https://notfacebook.com/1", RSS) is Platform.NEWS


def test_google_news_rss_con_facebook_de_medio_es_facebook() -> None:
    # Así llegan las de Facebook por Google News RSS: el link es de Google.
    url = "https://news.google.com/rss/articles/CBMi123"

    assert platform_of("facebook.com", url, RSS) is Platform.FACEBOOK


def test_sin_dominio_util_se_usa_el_nombre_que_da_google() -> None:
    url = "https://news.google.com/rss/articles/CBMi123"

    assert platform_of(None, url, WEB, "YouTube · La Saga - US") is Platform.YOUTUBE
    assert platform_of(None, url, WEB, "X · ivillasenor") is Platform.X
    assert platform_of(None, url, WEB, "Instagram · ivillasenor87") is Platform.INSTAGRAM


def test_el_dominio_gana_sobre_el_nombre() -> None:
    # Un medio que se llama «X» no vuelve red social a su sitio.
    assert platform_of("quintafuerza.mx", "https://quintafuerza.mx/n", WEB, "X") is Platform.WEB


@pytest.mark.parametrize(
    ("providers", "expected"),
    [
        (("searchapi",), Platform.NEWS),
        (("google_news_rss",), Platform.NEWS),
        (("gdelt",), Platform.NEWS),
        (("indice_local",), Platform.NEWS),
        (("searchapi_web", "indice_local"), Platform.NEWS),
        (("searchapi_web",), Platform.WEB),
        ((), Platform.NEWS),
    ],
)
def test_noticia_si_la_encontro_una_fuente_de_prensa(
    providers: tuple[str, ...], expected: Platform
) -> None:
    assert platform_of("quintafuerza.mx", "https://quintafuerza.mx/n", providers) is expected


# Cambió el requisito (revisión del 18/11/2026, hallazgo 8): el medio se guarda
# limpio («Milenio», no «Noticias · Milenio») porque la marca salía en el CSV
# y en los reportes. Lo que decide «Noticias» es quién la encontró.
def test_una_noticia_destacada_es_noticia_si_tambien_la_trajo_la_prensa() -> None:
    url = "https://www.milenio.com/n"

    assert platform_of("milenio.com", url, (*WEB, *RSS), "Milenio") is Platform.NEWS
    assert platform_of("milenio.com", url, WEB, "Milenio") is Platform.WEB


def test_un_medio_que_se_llama_noticias_no_cambia_la_plataforma() -> None:
    # Antes «Noticias · X» marcaba la sección; ya no hay marca en el nombre.
    url = "https://quintafuerza.mx/n"

    assert platform_of("quintafuerza.mx", url, WEB, "Noticias · Quinta Fuerza") is Platform.WEB


def test_es_red_social() -> None:
    assert is_social("facebook.com", "https://facebook.com/p/1")
    assert is_social(None, "https://news.google.com/rss/articles/x", "X · ivillasenor")
    assert not is_social("milenio.com", "https://www.milenio.com/n")
    assert not is_social(None, "https://quintafuerza.mx/n", "Quinta Fuerza")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.google.com/goto?url=CAES", True),
        ("https://google.com/goto?url=CAES", True),
        ("https://www.google.com/url?q=https://medio.mx", False),
        ("https://news.google.com/rss/articles/CBMi", False),
        ("https://quintafuerza.mx/goto", False),
        ("https://[malformado/goto", False),
    ],
)
def test_redireccion_de_google_web(url: str, expected: bool) -> None:
    assert is_google_redirect(url) is expected
