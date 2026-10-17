"""Repositorios de PostgreSQL de conceptos y de datos de lugar, contra la base de pruebas."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.application.audit import CONCEPT_CREATED, Actor, AuditEntry
from app.application.pagination import NameCursor
from app.application.use_cases.concepts import DeleteConcept
from app.core.config import Settings
from app.domain.concept import ConceptDraft
from app.domain.errors import ConceptNameTakenError, ConceptNotFoundError
from app.domain.queries import CountryFilter
from app.domain.region import RegionLevel
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
AUDIT = AuditEntry(Actor("prueba", "10.0.0.1"), CONCEPT_CREATED, {"after": {"name": "x"}})


def draft(name: str = "Secuestro", **overrides: Any) -> ConceptDraft:
    data: dict[str, Any] = {
        "name": name,
        "description": "",
        "keywords": ("secuestro", "plagio"),
        "exclude_terms": ("simulacro",),
        "color": "#E74C3C",
    }
    data.update(overrides)
    return ConceptDraft.validated(**data)


@pytest.fixture(scope="module")
def sync_engine(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(engine, settings, tmp_path_factory.mktemp("geodata"))
    # Un segundo "Cuauhtémoc" en otro estado, como el real de Chihuahua, para
    # probar nombres repetidos.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO regions (level, code, parent_id, country_code, name, name_norm,
                                     display_prefix, geom, centroid, bbox, source)
                SELECT 'municipality', '05999', s.id, 'MEX', 'Cuauhtémoc', 'CUAUHTEMOC',
                       'Municipio', s.geom, s.centroid, s.bbox, 'prueba'
                FROM regions s WHERE s.code = '05'
                """
            )
        )
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM regions WHERE code = '05999'"))
    engine.dispose()


def _empty_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        # Las búsquedas apuntan a los conceptos: se quitan primero.
        conn.execute(text("DELETE FROM searches"))
        conn.execute(text("DELETE FROM concepts"))
        conn.execute(text("DELETE FROM audit_log"))


@pytest.fixture
def clean(sync_engine: Engine) -> Iterator[Engine]:
    # Antes y después: estas pruebas confirman transacciones de verdad (como la
    # aplicación), así que no deben dejar conceptos a las demás pruebas.
    _empty_tables(sync_engine)
    yield sync_engine
    _empty_tables(sync_engine)


@pytest.fixture
def repo(test_engine: AsyncEngine, clean: Engine) -> PostgresConceptRepository:
    return PostgresConceptRepository(test_engine)


def audit_rows(engine: Engine) -> list[tuple[Any, ...]]:
    with engine.connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                text(
                    "SELECT action, entity_type, entity_id, user_id, host(ip), payload "
                    "FROM audit_log ORDER BY id"
                )
            )
        ]


def region_id(engine: Engine, code: str) -> int:
    with engine.connect() as conn:
        found: int = conn.execute(
            text("SELECT id FROM regions WHERE code = :c"), {"c": code}
        ).scalar_one()
        return found


# --- Conceptos -------------------------------------------------------------------


async def test_crear_y_leer_conserva_acentos_y_registra_auditoria(
    repo: PostgresConceptRepository, clean: Engine
) -> None:
    created = await repo.create(draft("Extorsión"), "prueba", AUDIT)

    loaded = await repo.get(created.id)

    assert loaded == created
    assert loaded is not None and loaded.data.name == "Extorsión"
    assert audit_rows(clean) == [
        (
            "concept.created",
            "concept",
            str(created.id),
            "prueba",
            "10.0.0.1",
            {"after": {"name": "x"}},
        )
    ]


async def test_la_base_rechaza_el_nombre_repetido_aunque_se_salte_la_revision(
    repo: PostgresConceptRepository, clean: Engine
) -> None:
    await repo.create(draft("Secuestro"), "prueba", AUDIT)

    with pytest.raises(ConceptNameTakenError):
        await repo.create(draft("SECUESTRO"), "prueba", AUDIT)
    # La transacción fallida no dejó registro de auditoría huérfano.
    assert len(audit_rows(clean)) == 1


async def test_name_taken_ignora_al_propio_concepto(repo: PostgresConceptRepository) -> None:
    created = await repo.create(draft("Secuestro"), "prueba", AUDIT)

    assert await repo.name_taken("SECUESTRO", None) is True
    assert await repo.name_taken("SECUESTRO", created.id) is False
    assert await repo.name_taken("PLAGIO", None) is False


async def test_lista_paginada_y_filtro_de_activos(repo: PostgresConceptRepository) -> None:
    for name in ("Secuestro", "Abigeato", "Extorsión"):
        await repo.create(draft(name), "prueba", AUDIT)
    await repo.create(draft("Inactivo", is_active=False), "prueba", AUDIT)

    first = await repo.list_concepts(None, None, 2)
    rest = await repo.list_concepts(None, NameCursor(first[-1].data.name_norm, first[-1].id), 10)
    active = await repo.list_concepts(True, None, 10)

    assert [c.data.name for c in first + rest] == [
        "Abigeato",
        "Extorsión",
        "Inactivo",
        "Secuestro",
    ]
    assert [c.data.name for c in active] == ["Abigeato", "Extorsión", "Secuestro"]


async def test_actualizar_y_updated_at(repo: PostgresConceptRepository) -> None:
    created = await repo.create(draft(), "prueba", AUDIT)

    updated = await repo.update(created.id, draft(keywords=("levantón",)), AUDIT)

    assert updated.data.keywords == ("levantón",)
    assert updated.updated_at >= created.updated_at


async def test_actualizar_inexistente(repo: PostgresConceptRepository) -> None:
    with pytest.raises(ConceptNotFoundError):
        await repo.update(999_999, draft(), AUDIT)


async def test_borrado_fisico_quita_la_fila(repo: PostgresConceptRepository, clean: Engine) -> None:
    created = await repo.create(draft(), "prueba", AUDIT)

    await repo.delete(created.id, logical=False, audit=AUDIT)

    with clean.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM concepts")).scalar_one() == 0
    assert len(audit_rows(clean)) == 2


async def test_borrado_logico_conserva_la_fila_y_libera_el_nombre(
    repo: PostgresConceptRepository, clean: Engine
) -> None:
    created = await repo.create(draft(), "prueba", AUDIT)

    await repo.delete(created.id, logical=True, audit=AUDIT)

    assert await repo.get(created.id) is None
    with clean.connect() as conn:
        assert conn.execute(
            text("SELECT deleted_at IS NOT NULL FROM concepts WHERE id = :id"), {"id": created.id}
        ).scalar_one()
    await repo.create(draft(), "prueba", AUDIT)


async def test_borrar_dos_veces_es_404(repo: PostgresConceptRepository) -> None:
    created = await repo.create(draft(), "prueba", AUDIT)
    await repo.delete(created.id, logical=True, audit=AUDIT)

    with pytest.raises(ConceptNotFoundError):
        await repo.delete(created.id, logical=True, audit=AUDIT)


async def test_un_concepto_usado_en_una_busqueda_se_borra_solo_logicamente(
    repo: PostgresConceptRepository, clean: Engine
) -> None:
    used = await repo.create(draft(), "prueba", AUDIT)
    unused = await repo.create(draft("Robo"), "prueba", AUDIT)
    with clean.begin() as conn:
        search = conn.execute(
            text(
                "INSERT INTO searches (user_id, region_id, date_from, date_to) "
                "SELECT 'prueba', id, '2026-10-10', '2026-10-16' FROM regions "
                "WHERE code = '09' RETURNING id"
            )
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO search_concepts (search_id, concept_id, concept_name, keywords) "
                "VALUES (:s, :c, 'Secuestro', '{secuestro}')"
            ),
            {"s": search, "c": used.id},
        )

    assert await repo.is_used_in_searches(used.id) is True
    assert await repo.is_used_in_searches(unused.id) is False
    # Antes se intentaba un borrado físico y la llave foránea lo rechazaba (500).
    result = await DeleteConcept(repo).execute(used.id, Actor("prueba"))
    assert result.logical is True
    with clean.connect() as conn:
        kept = conn.execute(
            text("SELECT deleted_at IS NOT NULL FROM concepts WHERE id = :id"), {"id": used.id}
        ).scalar_one()
    assert kept is True


# --- Datos del lugar para armar consultas ---------------------------------------------


async def test_datos_de_una_alcaldia_unica(test_engine: AsyncEngine, sync_engine: Engine) -> None:
    facts = await PostgresRegionRepository(test_engine).place_facts(region_id(sync_engine, "09007"))

    assert facts is not None
    assert (facts.level, facts.name, facts.name_is_repeated) == (
        RegionLevel.MUNICIPALITY,
        "Iztapalapa",
        False,
    )
    assert (facts.state_name, facts.state_search_terms) == (
        "Ciudad de México",
        ("Ciudad de México", "CDMX"),
    )
    assert facts.country == CountryFilter("México", "MX", "MX", "Mexico")
    assert facts.state_code == "09"


async def test_nombre_repetido_en_otro_estado(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    facts = await PostgresRegionRepository(test_engine).place_facts(region_id(sync_engine, "09015"))

    assert facts is not None and facts.name_is_repeated is True


async def test_estado_con_terminos_curados_y_sin_estado_padre(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    facts = await PostgresRegionRepository(test_engine).place_facts(region_id(sync_engine, "15"))

    assert facts is not None
    assert facts.search_terms == ("Estado de México", "Edomex")
    assert facts.state_name is None
    # Un estado lleva su propia clave (pista de GDELT del índice local).
    assert facts.state_code == "15"


async def test_pais_sin_fips_conserva_su_nombre_en_ingles(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    facts = await PostgresRegionRepository(test_engine).place_facts(region_id(sync_engine, "FRA"))

    assert facts is not None
    assert facts.country == CountryFilter("Francia", "FR", None, "France")
    assert facts.state_code is None


async def test_region_inexistente(test_engine: AsyncEngine) -> None:
    assert await PostgresRegionRepository(test_engine).place_facts(999_999_999) is None


async def test_terminos_de_los_estados_para_reconocer_notas_de_mexico(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    terms = await PostgresRegionRepository(test_engine).state_terms()

    # Nombre oficial y términos curados, sin repetir (ADR-0014).
    assert {"Ciudad de México", "CDMX", "Estado de México", "Edomex"} <= set(terms)
    assert len(terms) == len(set(terms))
