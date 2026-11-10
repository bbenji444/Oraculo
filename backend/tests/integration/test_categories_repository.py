"""Catálogo de categorías y categoría de cada nota contra la base de pruebas (F12.4)."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.categories_repository import PostgresCategoryStore
from app.application.audit import Actor, AuditEntry
from app.core.config import Settings
from app.domain.authority import Authority
from app.domain.categories import CategoryChanges, CategoryChoice, other_category
from app.domain.concept import ConceptDraft
from app.domain.errors import CategoryNameTakenError

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
PREFIX = "https://categorias.mx/"


def _clean(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM articles WHERE url_canonical LIKE :p"), {"p": f"{PREFIX}%"})


@pytest.fixture
def sync_engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    _clean(engine)
    yield engine
    _clean(engine)
    engine.dispose()


def _article(
    engine: Engine, slug: str, title: str, summary: str | None, snippet: str | None
) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "INSERT INTO articles (url_canonical, url_hash, title, title_norm, summary, "
                    "snippet) VALUES (:url, md5(:url), :title, upper(:title), :summary, :snippet) "
                    "RETURNING id"
                ),
                {"url": f"{PREFIX}{slug}", "title": title, "summary": summary, "snippet": snippet},
            ).scalar_one()
        )


async def test_el_catalogo_sembrado_tiene_15_y_un_solo_otros(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    categories = await PostgresCategoryStore(test_engine).active_categories()

    # 14 de la migración 0026 más «Seguridad nacional» de la 0029.
    assert len(categories) == 15
    assert categories[0].name == "Narcotráfico y delitos contra la salud"
    assert other_category(categories).name == "Otros"
    # Cada una con su color desde la 0032, todos distintos; el símbolo sigue sin decidirse.
    colors = [c.color for c in categories]
    assert all(color is not None and re.fullmatch(r"#[0-9A-F]{6}", color) for color in colors)
    assert len(set(colors)) == len(colors)
    assert all(c.symbol is None for c in categories)


async def test_seguridad_nacional_va_justo_antes_de_otros(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    categories = await PostgresCategoryStore(test_engine).active_categories()

    assert [c.name for c in categories[-2:]] == [
        "Seguridad nacional (traición a la patria)",
        "Otros",
    ]
    assert "traición a la patria" in categories[-2].description.lower()
    assert not categories[-2].is_other


async def test_pendientes_guardar_y_volver_a_pedir(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresCategoryStore(test_engine)
    armas = _article(sync_engine, "a", "FGR asegura armas", "Aseguran 40 rifles.", "fragmento")
    sin_resumen = _article(sync_engine, "b", "Detienen a exfiscal", None, "Del medio.")
    categories = await store.active_categories()
    weapons = next(c for c in categories if c.name == "Armas y explosivos")

    pending = await store.pending_notes([armas, sin_resumen], "classify_v1")
    count_before = await store.count_pending("classify_v1")
    await store.save(
        [
            CategoryChoice(armas, weapons, "tráfico de armas", Authority.FGR),
        ],
        "classify_v1",
    )
    # La base de pruebas puede tener otras notas: se mide la diferencia.
    assert await store.count_pending("classify_v1") == count_before - 1
    again = await store.pending_notes([armas, sin_resumen], "classify_v1")
    newer = await store.pending_notes([armas, sin_resumen], "classify_v2")

    # Sin resumen de la IA se usa el fragmento del medio.
    assert [(n.article_id, n.summary) for n in pending] == [
        (armas, "Aseguran 40 rifles."),
        (sin_resumen, "Del medio."),
    ]
    assert [n.article_id for n in again] == [sin_resumen]
    # Otra versión del prompt: se vuelve a clasificar.
    assert [n.article_id for n in newer] == [armas, sin_resumen]
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT category_id, category_raw, category_version, authority "
                "FROM articles WHERE id = :id"
            ),
            {"id": armas},
        ).one()
    assert tuple(row) == (weapons.category_id, "tráfico de armas", "classify_v1", "fgr")


# --- Editor de subdivisiones (02/11/2026) ---

HOMICIDIO_ID = 5
TOPIC_BY = "prueba-subdivisiones"


@pytest.fixture
def topic_concept(sync_engine: Engine) -> Iterator[int]:
    """Un tema general ligado a «Homicidio»; al final se borra y la categoría se restaura."""
    with sync_engine.begin() as conn:
        original = conn.execute(
            text("SELECT name, name_norm, color, is_active FROM categories WHERE id = :id"),
            {"id": HOMICIDIO_ID},
        ).one()
        concept_id = int(
            conn.execute(
                text(
                    "INSERT INTO concepts (name, name_norm, keywords, color, created_by, "
                    "category_id) VALUES ('Tema de prueba 0034', 'TEMA DE PRUEBA 0034', "
                    "ARRAY['homicidio'], '#FF4D6D', :by, :category) RETURNING id"
                ),
                {"by": TOPIC_BY, "category": HOMICIDIO_ID},
            ).scalar_one()
        )
    yield concept_id
    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM concepts WHERE created_by = :by"), {"by": TOPIC_BY})
        conn.execute(
            text(
                "UPDATE categories SET name = :name, name_norm = :name_norm, color = :color, "
                "is_active = :is_active WHERE id = :id"
            ),
            {**original._asdict(), "id": HOMICIDIO_ID},
        )


async def test_el_catalogo_completo_trae_su_tema_general(
    topic_concept: int, test_engine: AsyncEngine
) -> None:
    store = PostgresCategoryStore(test_engine)

    homicidio = await store.get_category(HOMICIDIO_ID)
    everything = await store.all_categories()

    assert homicidio is not None and homicidio.topic_concept_id == topic_concept
    assert [c.category_id for c in everything] == [
        c.category_id for c in await store.active_categories()
    ]
    assert await store.get_category(9999) is None


async def test_editar_renombra_su_tema_apaga_ambos_y_queda_en_la_bitacora(
    sync_engine: Engine, topic_concept: int, test_engine: AsyncEngine
) -> None:
    store = PostgresCategoryStore(test_engine)
    current = await store.get_category(HOMICIDIO_ID)
    assert current is not None
    edited = CategoryChanges(name="Homicidio doloso", color="#ff0000", is_active=False)

    saved = await store.update_category(
        edited.apply_to(current),
        AuditEntry(Actor(TOPIC_BY), "category.updated", {"changed": ["name"]}),
    )

    assert (saved.name, saved.color, saved.is_active, saved.topic_concept_id) == (
        "Homicidio doloso",
        "#FF0000",
        False,
        topic_concept,
    )
    assert HOMICIDIO_ID not in [c.category_id for c in await store.active_categories()]
    assert HOMICIDIO_ID in [c.category_id for c in await store.all_categories()]
    with sync_engine.connect() as conn:
        concept = conn.execute(
            text("SELECT name, name_norm, is_active FROM concepts WHERE id = :id"),
            {"id": topic_concept},
        ).one()
        audit = conn.execute(
            text(
                "SELECT action, payload FROM audit_log WHERE entity_type = 'category' "
                "AND entity_id = :id AND user_id = :by ORDER BY id DESC LIMIT 1"
            ),
            {"id": str(HOMICIDIO_ID), "by": TOPIC_BY},
        ).one()
    assert tuple(concept) == ("Homicidio doloso", "HOMICIDIO DOLOSO", False)
    assert (audit.action, audit.payload) == ("category.updated", {"changed": ["name"]})


async def test_editar_con_el_nombre_de_otra_subdivision_es_conflicto(
    topic_concept: int, test_engine: AsyncEngine
) -> None:
    store = PostgresCategoryStore(test_engine)
    current = await store.get_category(HOMICIDIO_ID)
    assert current is not None

    with pytest.raises(CategoryNameTakenError):
        await store.update_category(
            CategoryChanges(name="secuestro").apply_to(current),
            AuditEntry(Actor(TOPIC_BY), "category.updated", {}),
        )

    # Nada se guardó a medias: ni la categoría ni su tema.
    after = await store.get_category(HOMICIDIO_ID)
    assert after is not None and after.name == current.name


async def test_agregar_y_borrar_una_subdivision(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    # Benji, 09/11/2026: las subdivisiones se agregan y se borran.
    store = PostgresCategoryStore(test_engine)
    actor = Actor("prueba-alta-baja-subdivisiones")
    before = await store.all_categories()
    topic = ConceptDraft.validated(
        name="Prueba Feminicidio",
        description="",
        keywords=("feminicidio",),
        exclude_terms=(),
        color="#FF4D6D",
    )
    template = CategoryChanges("Prueba Feminicidio", "Asesinato de mujeres", "#FF4D6D")
    created = await store.create_category(
        template.apply_to(before[0]),
        topic,
        actor.user_id,
        AuditEntry(actor, "category.created", {}),
    )
    try:
        after = await store.all_categories()
        # Va antes de «Otros», que sigue al final, y trae su tema general.
        assert [c.name for c in after][-2:] == ["Prueba Feminicidio", "Otros"]
        assert created.topic_concept_id is not None
        note = _article(sync_engine, "feminicidio", "Nota de prueba", None, None)
        with sync_engine.begin() as conn:
            conn.execute(
                text("UPDATE articles SET category_id = :c WHERE id = :a"),
                {"c": created.category_id, "a": note},
            )

        moved = await store.delete_category(created, AuditEntry(actor, "category.deleted", {}))

        assert moved == 1
        assert [c.name for c in await store.all_categories()] == [c.name for c in before]
        with sync_engine.connect() as conn:
            category_name = conn.execute(
                text(
                    "SELECT c.name FROM articles a JOIN categories c ON c.id = a.category_id "
                    "WHERE a.id = :a"
                ),
                {"a": note},
            ).scalar_one()
            topic_row = conn.execute(
                text("SELECT deleted_at IS NOT NULL, category_id FROM concepts WHERE id = :t"),
                {"t": created.topic_concept_id},
            ).one()
            actions = conn.execute(
                text(
                    "SELECT action, payload->>'notes_moved_to_other' FROM audit_log "
                    "WHERE user_id = :u ORDER BY id"
                ),
                {"u": actor.user_id},
            ).all()
        assert category_name == "Otros"
        assert tuple(topic_row) == (True, None)
        assert [tuple(a) for a in actions] == [
            ("category.created", None),
            ("category.deleted", "1"),
        ]
    finally:
        with sync_engine.begin() as conn:
            conn.execute(text("DELETE FROM concepts WHERE name = 'Prueba Feminicidio'"))
            conn.execute(text("DELETE FROM categories WHERE name = 'Prueba Feminicidio'"))
            conn.execute(text("DELETE FROM audit_log WHERE user_id = :u"), {"u": actor.user_id})
