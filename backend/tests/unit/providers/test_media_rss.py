"""RSS de medios mexicanos con recortes de los feeds reales (16/10/2026)."""

from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from app.adapters.ingest.media_rss import (
    SNIPPET_MAX_CHARS,
    FeedError,
    MediaRssSource,
    clean_snippet,
    parse_feed,
    read_feeds,
)
from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.ingest import MediaFeed
from app.domain.queries import Provider

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"
JORNADA = MediaFeed("la-jornada", "La Jornada", "https://www.jornada.com.mx/rss/edicion.xml", True)
UNIVERSAL = MediaFeed("el-universal", "El Universal", "https://www.eluniversal.com.mx/rss", True)
INFOBAE = MediaFeed("infobae-mexico", "Infobae México", "https://www.infobae.com/rss", True)


def fixture(slug: str) -> bytes:
    return (FIXTURES / f"rss_{slug}.xml").read_bytes()


def test_la_lista_curada_tiene_los_tres_medios_inactivos() -> None:
    feeds = read_feeds()

    assert [f.slug for f in feeds] == ["la-jornada", "el-universal", "infobae-mexico"]
    # Inactivos hasta que Benji revise sus términos (ADR-0013).
    assert not any(f.active for f in feeds)
    assert feeds[0].source == "rss:la-jornada"


@pytest.mark.parametrize("feed", [JORNADA, UNIVERSAL, INFOBAE])
def test_los_tres_feeds_reales_se_leen_completos(feed: MediaFeed) -> None:
    result = parse_feed(fixture(feed.slug), feed)

    assert (result.seen, len(result.items), result.discarded) == (10, 10, 0)
    assert all(item.source == feed.source for item in result.items)
    assert all(item.source_name == feed.name for item in result.items)
    assert all(item.published_at.tzinfo is UTC for item in result.items)
    # Nunca se guarda más que un fragmento corto.
    assert all(len(item.snippet or "") <= SNIPPET_MAX_CHARS for item in result.items)


def test_una_nota_real_de_el_universal() -> None:
    first = parse_feed(fixture("el-universal"), UNIVERSAL).items[0]

    assert first.title.startswith("Javier Aguirre acepta")
    assert first.source_domain == "eluniversal.com.mx"
    assert first.published_at == datetime(2026, 10, 16, 19, 36, 6, tzinfo=UTC)


def test_el_fragmento_queda_sin_html_ni_entidades() -> None:
    assert clean_snippet("<p>Ataque en la alcald&iacute;a <b>Iztapalapa</b></p>") == (
        "Ataque en la alcaldía Iztapalapa"
    )
    assert clean_snippet("") is None
    assert len(clean_snippet("x" * 1000) or "") == SNIPPET_MAX_CHARS


def test_rss_roto_es_error() -> None:
    with pytest.raises(FeedError, match="La Jornada"):
        parse_feed(b"<html>Mantenimiento", JORNADA)


@pytest.mark.anyio
async def test_baja_y_lee_con_transporte_simulado() -> None:
    http = ProviderHttpClient(
        Provider.GDELT,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(
            lambda _r: httpx2.Response(200, content=fixture("la-jornada"))
        ),
    )

    result, size = await MediaRssSource(http).fetch(JORNADA)

    assert (len(result.items), size) == (10, len(fixture("la-jornada")))
    await http.aclose()
