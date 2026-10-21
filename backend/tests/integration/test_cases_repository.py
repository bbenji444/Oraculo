"""Repositorio de casos contra la base de pruebas (Fase 9.3, historia H9.1).

Comprueba lo que solo la base puede garantizar: que nadie ve un caso del que
no es miembro, que cada cambio deja su bitácora en la misma transacción y que
``case.viewed`` no se repite dentro de la ventana de minutos.
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.cases_repository import PostgresCaseRepository
from app.application.audit import Actor, AuditEntry
from app.application.pagination import TimeCursor
from app.core.config import Settings
from app.domain.case import CaseDraft
from app.domain.investigation import CaseMemberRole, CaseStatus, InvestigationAction

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
BENJI = Actor("benji", "10.0.0.1")
OPEN = (CaseStatus.OPEN, CaseStatus.CLOSED)


def created(actor: Actor = BENJI) -> AuditEntry:
    return AuditEntry(actor, InvestigationAction.CASE_CREATED, {"after": {"name": "x"}})


@pytest.fixture(scope="module")
def sync_engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean(sync_engine: Engine) -> Iterator[None]:
    yield
    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM cases"))
        conn.execute(text("DELETE FROM audit_log WHERE entity_type = 'case'"))


def audit_actions(engine: Engine, case_id: object) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT action FROM audit_log WHERE entity_type = 'case' "
                    "AND entity_id = :id ORDER BY id"
                ),
                {"id": str(case_id)},
            ).scalars()
        )


async def test_crear_deja_dueno_y_bitacora_y_nadie_mas_lo_ve(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresCaseRepository(test_engine)
    draft = CaseDraft.validated("Homicidio estilista Polanco", "", "confidential")

    case = await repo.create(draft, "benji", created())
    mine = await repo.get_view(case.id, "benji")

    assert (case.status, case.sensitivity, case.article_count) == (
        CaseStatus.OPEN,
        "confidential",
        0,
    )
    assert mine is not None and mine.role is CaseMemberRole.OWNER
    assert await repo.get_view(case.id, "otra-analista") is None
    assert await repo.get_view(uuid4(), "benji") is None
    assert audit_actions(sync_engine, case.id) == ["case.created"]


async def test_la_lista_trae_solo_mis_casos_del_mas_reciente_con_cursor(
    test_engine: AsyncEngine,
) -> None:
    repo = PostgresCaseRepository(test_engine)
    first = await repo.create(CaseDraft.validated("Primero", "", "normal"), "benji", created())
    second = await repo.create(CaseDraft.validated("Segundo", "", "normal"), "benji", created())
    await repo.create(CaseDraft.validated("Ajeno", "", "normal"), "otra", created())

    page = await repo.list_for_user("benji", OPEN, None, None, 1)
    last = page[0].case
    rest = await repo.list_for_user(
        "benji", OPEN, None, TimeCursor(last.updated_at, str(last.id)), 5
    )

    assert [v.case.id for v in page + rest] == [second.id, first.id]
    assert page[0].has_article is None


async def test_la_lista_dice_si_un_caso_ya_tiene_la_nota(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresCaseRepository(test_engine)
    with_note = await repo.create(CaseDraft.validated("Con nota", "", "normal"), "benji", created())
    without = await repo.create(CaseDraft.validated("Sin nota", "", "normal"), "benji", created())
    with sync_engine.begin() as conn:
        article = conn.execute(
            text(
                "INSERT INTO articles (url_canonical, url_hash, title, title_norm) VALUES "
                "('https://m.mx/caso', md5('https://m.mx/caso'), 'Nota', 'NOTA') "
                "ON CONFLICT (url_hash) DO UPDATE SET title = 'Nota' RETURNING id"
            )
        ).scalar_one()
        conn.execute(
            text("INSERT INTO case_articles (case_id, article_id, added_by) VALUES (:c, :a, 'b')"),
            {"c": with_note.id, "a": article},
        )

    views = await repo.list_for_user("benji", OPEN, article, None, 10)

    flags = {v.case.id: (v.has_article, v.case.article_count) for v in views}
    assert flags == {with_note.id: (True, 1), without.id: (False, 0)}


async def test_editar_cambia_estado_y_cierre_y_deja_bitacora(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresCaseRepository(test_engine)
    case = await repo.create(CaseDraft.validated("Caso", "", "normal"), "benji", created())

    closed = await repo.update(
        case.id,
        data=CaseDraft.validated("Caso Polanco", "Ya resuelto", "restricted"),
        status=CaseStatus.CLOSED,
        closed_at=case.created_at,
        audit=AuditEntry(BENJI, InvestigationAction.CASE_CLOSED, {}),
    )

    assert (closed.name, closed.description, closed.status, closed.closed_at) == (
        "Caso Polanco",
        "Ya resuelto",
        CaseStatus.CLOSED,
        case.created_at,
    )
    assert closed.updated_at > case.updated_at
    assert audit_actions(sync_engine, case.id) == ["case.created", "case.closed"]
    assert await repo.list_for_user("benji", (CaseStatus.OPEN,), None, None, 5) == []


async def test_ver_un_caso_se_registra_una_vez_por_ventana(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresCaseRepository(test_engine)
    case = await repo.create(CaseDraft.validated("Caso", "", "normal"), "benji", created())
    viewed = AuditEntry(BENJI, InvestigationAction.CASE_VIEWED, {})

    first = await repo.record_view(case.id, viewed, 5)
    again = await repo.record_view(case.id, viewed, 5)
    other = await repo.record_view(case.id, AuditEntry(Actor("otra"), viewed.action, {}), 5)
    # Con ventana 0 ya no cuenta la anterior: es como si hubieran pasado los minutos.
    later = await repo.record_view(case.id, viewed, 0)

    assert (first, again, other, later) == (True, False, True, True)
    assert audit_actions(sync_engine, case.id).count("case.viewed") == 3
