"""Grupos y tamaño de página de la bitácora (``app.domain.audit_trail``)."""

from app.domain.audit_trail import (
    DEFAULT_PAGE_SIZE,
    GROUP_PREFIXES,
    MAX_PAGE_SIZE,
    AuditGroup,
    AuditQuery,
)


def test_todos_los_grupos_tienen_sus_temas() -> None:
    assert set(GROUP_PREFIXES) == set(AuditGroup)
    assert AuditQuery().prefixes == ()
    assert "access_key" in AuditQuery(AuditGroup.ACCESS).prefixes
    assert AuditQuery(AuditGroup.REPORTS).prefixes == ("report",)


def test_ningun_tema_cae_en_dos_grupos() -> None:
    temas = [t for group, ts in GROUP_PREFIXES.items() if group is not AuditGroup.ALL for t in ts]
    assert len(temas) == len(set(temas))


def test_el_tamano_de_pagina_queda_entre_1_y_el_tope() -> None:
    assert AuditQuery().size == DEFAULT_PAGE_SIZE
    assert AuditQuery(limit=0).size == 1
    assert AuditQuery(limit=10_000).size == MAX_PAGE_SIZE
