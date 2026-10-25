"""Índice local y registro de ingesta contra la base de pruebas."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.news_index_repository import (
    PostgresIngestRunLog,
    PostgresNewsIndex,
    index_stats,
    url_hash,
)
from app.application.ports.ingest import IngestRun
from app.application.use_cases.ingest import IngestGdeltGkg
from app.core.config import Settings
from app.domain.news_index import GdeltLocation, NewsItem
from tests.unit.fake_ingest import FILE, FakeGkg, parsed

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 16, 20, 0, tzinfo=UTC)


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM news_index"))
        conn.execute(text("DELETE FROM ingest_runs"))


@pytest.fixture
def sync_engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    _empty(engine)
    yield engine
    _empty(engine)
    engine.dispose()


def note(url: str, published_at: datetime = NOW, title: str | None = None) -> NewsItem:
    # Cada URL lleva su propio título: el mismo medio con el mismo texto es
    # la misma nota (ADR-0025), así que notas distintas necesitan títulos distintos.
    return NewsItem.create(
        source="gdelt_gkg",
        url=url,
        title=title or f"Cayó extorsionador tras cateo en Iztapalapa {url.rsplit('/', 1)[-1]}",
        snippet="Detienen a un hombre en la alcaldía.",
        published_at=published_at,
        language="es",
        gdelt_states=("09",),
        gdelt_locations=(
            GdeltLocation(4, "Iztapalapa, Distrito Federal, Mexico", "MX", "MX09", 19.35, -99.06),
        ),
        gdelt_themes=("ARREST",),
    )


async def test_guarda_la_nota_con_texto_normalizado_y_pistas(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    new = await PostgresNewsIndex(test_engine).add([note("https://medio.mx/a")])

    assert new == 1
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT url_hash, text_norm, gdelt_states, gdelt_locations, gdelt_themes "
                "FROM news_index"
            )
        ).one()
    assert row.url_hash == url_hash("https://medio.mx/a")
    assert row.text_norm.startswith("CAYO EXTORSIONADOR TRAS CATEO EN IZTAPALAPA")
    assert row.gdelt_states == ["09"]
    assert row.gdelt_themes == ["ARREST"]
    assert row.gdelt_locations[0]["adm1"] == "MX09"
    assert json.dumps(row.gdelt_locations, ensure_ascii=False).count("Iztapalapa") == 1


async def test_reingerir_la_misma_url_no_duplica(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    index = PostgresNewsIndex(test_engine)

    first = await index.add([note("https://medio.mx/a"), note("https://medio.mx/b")])
    second = await index.add([note("https://medio.mx/b"), note("https://medio.mx/c")])

    assert (first, second) == (2, 1)
    with sync_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM news_index")).scalar_one() == 3


async def test_la_limpieza_borra_solo_lo_viejo(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    index = PostgresNewsIndex(test_engine)
    await index.add(
        [note("https://medio.mx/vieja", NOW - timedelta(days=91)), note("https://medio.mx/nueva")]
    )

    deleted = await index.purge_before(NOW - timedelta(days=90))

    assert deleted == 1
    with sync_engine.connect() as conn:
        assert (
            conn.execute(text("SELECT url FROM news_index")).scalar_one()
            == "https://medio.mx/nueva"
        )


async def test_registro_de_corridas_y_archivo_ya_procesado(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    runs = PostgresIngestRunLog(test_engine)
    failed = IngestRun(
        "gdelt_gkg", FILE.name, FILE.url, "error", NOW, NOW, error_message="incompleto"
    )

    await runs.record(failed)
    assert not await runs.already_processed(FILE.url)

    run_id = await runs.record(
        IngestRun("gdelt_gkg", FILE.name, FILE.url, "ok", NOW, NOW, items_new=3)
    )
    assert run_id > 0
    assert await runs.already_processed(FILE.url)


async def test_caso_de_uso_completo_contra_la_base(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    use_case = IngestGdeltGkg(
        FakeGkg(parsed(4)), PostgresNewsIndex(test_engine), PostgresIngestRunLog(test_engine)
    )

    first, second = await use_case.run(), await use_case.run()

    assert (first.status, first.items_new, second.status) == ("ok", 4, "skipped")
    with sync_engine.connect() as conn:
        counts = conn.execute(
            text("SELECT (SELECT count(*) FROM news_index), (SELECT count(*) FROM ingest_runs)")
        ).one()
    assert tuple(counts) == (4, 1)


async def test_dos_corridas_ok_del_mismo_archivo_no_chocan(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    # El reloj y el historial pueden terminar el mismo archivo casi a la vez.
    runs = PostgresIngestRunLog(test_engine)
    ok = IngestRun("gdelt_gkg", FILE.name, FILE.url, "ok", NOW, NOW, items_new=3)

    first, second = await runs.record(ok), await runs.record(ok)

    assert first > 0
    assert second == 0
    with sync_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ingest_runs")).scalar_one() == 1


async def test_las_frases_del_cuerpo_se_guardan_y_se_vacian_a_su_tiempo(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    index = PostgresNewsIndex(test_engine)
    old = NewsItem.create(
        source="gdelt_ngrams",
        url="https://medio.mx/vieja",
        title="Robo en la colonia",
        published_at=NOW - timedelta(days=31),
        body_phrases=["detienen en Iztapalapa a", "en Iztapalapa a un"],
    )
    recent = NewsItem.create(
        source="gdelt_ngrams",
        url="https://medio.mx/nueva",
        title="Robo en la colonia",
        published_at=NOW,
        body_phrases=["asalto en Tlalpan con"],
    )
    await index.add([old, recent])

    cleared = await index.clear_bodies_before(NOW - timedelta(days=30))

    assert cleared == 1
    with sync_engine.connect() as conn:
        rows = conn.execute(text("SELECT url, body_terms FROM news_index")).all()
    bodies: dict[str, str | None] = {row.url: row.body_terms for row in rows}
    # La nota vieja se queda (título y link), sin su cuerpo.
    assert bodies == {
        "https://medio.mx/vieja": None,
        "https://medio.mx/nueva": "ASALTO EN TLALPAN CON",
    }


async def test_estadisticas_por_fuente(sync_engine: Engine, test_engine: AsyncEngine) -> None:
    await PostgresNewsIndex(test_engine).add(
        [
            note("https://medio.mx/a"),
            NewsItem.create(
                source="gdelt_ngrams",
                url="https://medio.mx/b",
                title="Nota",
                published_at=NOW,
                body_phrases=["frase del cuerpo uno"],
            ),
        ]
    )

    stats, total = await index_stats(test_engine)

    by_source = {s.source: s for s in stats}
    assert by_source["gdelt_gkg"].notes == 1
    assert by_source["gdelt_gkg"].with_body == 0
    assert (by_source["gdelt_ngrams"].with_body, by_source["gdelt_ngrams"].newest) == (1, NOW)
    assert by_source["gdelt_ngrams"].body_bytes > 0
    assert total > 0


async def test_no_guarda_la_misma_url_con_otro_puerto_ni_con_www(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    # Par real (24/10/2026): razon.com.mx con y sin :443 (F12.1b, ADR-0025).
    index = PostgresNewsIndex(test_engine)

    new = await index.add(
        [
            note("https://www.razon.com.mx/mexico/trudy", title="Huracán Trudy"),
            note("https://razon.com.mx:443/mexico/trudy", title="Huracán Trudy, versión 443"),
        ]
    )

    assert new == 1


async def test_el_mismo_medio_con_el_mismo_texto_es_la_misma_nota(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    index = PostgresNewsIndex(test_engine)
    title = "Perdió el control y chocó contra puente en el viaducto Díaz Ordaz"
    await index.add([note("https://puentelibre.mx/local/choque", title=title)])

    again = await index.add(
        [
            # Variante real con %20 en la ruta: otra URL, mismo medio y texto.
            note("https://puentelibre.mx/local%20/choque", NOW + timedelta(hours=6), title),
            # La misma nota sindicada en otro medio sí entra: es otra fuente.
            note("https://tiempo.com.mx/local/choque", title=title),
            # Mismo medio y texto pero una semana después: otra nota.
            note("https://puentelibre.mx/local/choque-2", NOW + timedelta(days=7), title),
        ]
    )

    assert again == 2
    with sync_engine.connect() as conn:
        urls = conn.execute(text("SELECT url FROM news_index ORDER BY id")).scalars().all()
    assert urls == [
        "https://puentelibre.mx/local/choque",
        "https://tiempo.com.mx/local/choque",
        "https://puentelibre.mx/local/choque-2",
    ]
