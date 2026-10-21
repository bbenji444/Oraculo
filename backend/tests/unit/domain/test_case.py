"""Reglas de un caso de investigación (Fase 9.3, historia H9.1)."""

from datetime import UTC, datetime

import pytest

from app.domain.case import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    CaseDraft,
    can_edit,
    can_manage_members,
    closed_at_for,
    is_read_only,
)
from app.domain.errors import CaseValidationError
from app.domain.investigation import CaseMemberRole, CaseStatus, Sensitivity

NOW = datetime(2026, 10, 21, 18, tzinfo=UTC)


def test_un_caso_valido_limpia_espacios_y_normaliza_el_nombre() -> None:
    draft = CaseDraft.validated("  Homicidio   estilista Polanco ", "  Caso Micky Hair ", "normal")

    assert draft.name == "Homicidio estilista Polanco"
    assert draft.name_norm == "HOMICIDIO ESTILISTA POLANCO"
    assert draft.description == "Caso Micky Hair"
    assert draft.sensitivity is Sensitivity.NORMAL


def test_reporta_todos_los_problemas_con_su_campo() -> None:
    with pytest.raises(CaseValidationError) as error:
        CaseDraft.validated(" ", "x" * (DESCRIPTION_MAX_LENGTH + 1), "secreto")

    problems = error.value.details["problemas"]
    assert isinstance(problems, list)
    assert [p["campo"] for p in problems] == ["name", "description", "sensitivity"]


def test_el_nombre_tiene_tope() -> None:
    CaseDraft.validated("x" * NAME_MAX_LENGTH, "", "restricted")

    with pytest.raises(CaseValidationError):
        CaseDraft.validated("x" * (NAME_MAX_LENGTH + 1), "", "normal")


@pytest.mark.parametrize(
    ("role", "edit", "members"),
    [
        (CaseMemberRole.OWNER, True, True),
        (CaseMemberRole.EDITOR, True, False),
        (CaseMemberRole.VIEWER, False, False),
    ],
)
def test_permisos_por_rol(role: CaseMemberRole, edit: bool, members: bool) -> None:
    assert (can_edit(role), can_manage_members(role)) == (edit, members)


def test_solo_un_caso_abierto_se_puede_cambiar() -> None:
    assert not is_read_only(CaseStatus.OPEN)
    assert is_read_only(CaseStatus.CLOSED)
    assert is_read_only(CaseStatus.ARCHIVED)


def test_la_fecha_de_cierre_sigue_al_estado() -> None:
    before = datetime(2026, 10, 1, tzinfo=UTC)

    assert closed_at_for(CaseStatus.CLOSED, None, NOW) == NOW
    # Archivar un caso ya cerrado conserva cuándo se cerró.
    assert closed_at_for(CaseStatus.ARCHIVED, before, NOW) == before
    assert closed_at_for(CaseStatus.OPEN, before, NOW) is None
