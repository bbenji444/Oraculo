"""Las notas en la caché conservan la marca de título cortado (ADR-0115), sin Redis."""

import json
from datetime import UTC, datetime

from app.adapters.cache.redis_query_cache import from_json, to_json
from app.domain.articles import RawArticle
from app.domain.queries import Provider


def test_ida_y_vuelta_con_titulo_cortado() -> None:
    article = RawArticle.create(
        provider=Provider.SEARCHAPI_WEB,
        provider_rank=3,
        url="https://quintafuerza.mx/mexico/hackean",
        title="Hackean 746 mil cuentas de celular, incluidas las de",
        source_name="Quinta Fuerza",
        published_at=datetime(2026, 11, 18, 4, 3, tzinfo=UTC),
        title_truncated=True,
    )

    [back] = from_json(to_json((article,)))

    assert back == article
    assert back.title_truncated is True


def test_lo_guardado_antes_de_la_marca_sale_sin_cortar() -> None:
    article = RawArticle.create(
        provider=Provider.SEARCHAPI, provider_rank=1, url="https://milenio.com/n", title="Nota"
    )
    old = json.loads(to_json((article,)))
    for item in old:
        item.pop("title_truncated")

    [back] = from_json(json.dumps(old))

    assert back.title_truncated is False
