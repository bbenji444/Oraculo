"""Leer la bitácora por páginas (``ReadAuditTrail``), con todo en memoria."""

import pytest

from app.application.audit import Actor, AuditEntry
from app.application.use_cases.audit_trail import ReadAuditTrail
from app.domain.access import AuthUser, Role
from app.domain.audit_trail import AuditGroup, AuditQuery
from app.domain.errors import ForbiddenError
from tests.unit.fake_access import FakeAccessStore, FakeAuditTrail, access_world

pytestmark = pytest.mark.anyio

BENJI = AuthUser(1, "benji", "Benji", Role.SUPERUSER)
ANA = AuthUser(2, "ana", "Ana", Role.USER)


def _trail_with(*actions: tuple[str, str]) -> tuple[ReadAuditTrail, FakeAccessStore]:
    store = access_world().store
    for who, action in actions:
        store.events.append((AuditEntry(Actor(who, "10.0.0.1"), action, {}), "1"))
    return ReadAuditTrail(FakeAuditTrail(store)), store


async def test_solo_un_superusuario_la_lee() -> None:
    trail, _ = _trail_with(("benji", "auth.login"))

    with pytest.raises(ForbiddenError):
        await trail.page(ANA, AuditQuery())


async def test_pagina_de_lo_nuevo_a_lo_viejo_con_cursor() -> None:
    trail, _ = _trail_with(
        ("benji", "auth.login"),
        ("benji", "search.finished"),
        ("pepe", "access_key.revealed"),
    )

    first = await trail.page(BENJI, AuditQuery(limit=2))
    second = await trail.page(BENJI, AuditQuery(before=first.next_before, limit=2))

    assert [e.action for e in first.events] == ["access_key.revealed", "search.finished"]
    assert first.next_before == first.events[-1].event_id
    assert [e.action for e in second.events] == ["auth.login"]
    assert second.next_before is None


async def test_filtra_por_grupo_y_por_persona() -> None:
    trail, _ = _trail_with(
        ("benji", "auth.login"),
        ("benji", "case.viewed"),
        ("pepe", "auth.login_failed"),
    )

    access = await trail.page(BENJI, AuditQuery(AuditGroup.ACCESS))
    pepe = await trail.page(BENJI, AuditQuery(actor="pepe"))

    assert [e.action for e in access.events] == ["auth.login_failed", "auth.login"]
    assert [(e.actor, e.action) for e in pepe.events] == [("pepe", "auth.login_failed")]
    assert access.events[0].ip == "10.0.0.1"
