"""Reglas de los vínculos entre entidades de un caso (Fase 9.5, decisiones D6 y D7)."""

import pytest

from app.domain.errors import RelationshipValidationError
from app.domain.investigation import RelationshipType
from app.domain.relationships import (
    COOCCURRENCE_CONFIDENCE_MAX,
    CUSTOM_LABEL_MAX_CHARS,
    HUMAN_RELATIONSHIP_CONFIDENCE,
    RELATIONSHIP_NOTES_MAX_CHARS,
    cooccurrence_confidence,
    manual_relationship,
)


@pytest.mark.parametrize(("shared", "expected"), [(1, 0.5), (2, 0.7), (3, 0.9), (12, 0.9)])
def test_la_confianza_crece_con_las_notas_compartidas(shared: int, expected: float) -> None:
    assert cooccurrence_confidence(shared) == expected


def test_la_coocurrencia_nunca_alcanza_lo_que_afirma_una_persona() -> None:
    assert COOCCURRENCE_CONFIDENCE_MAX < HUMAN_RELATIONSHIP_CONFIDENCE == 1.0


def test_sin_notas_compartidas_no_hay_vinculo() -> None:
    with pytest.raises(ValueError, match="Sin notas compartidas"):
        cooccurrence_confidence(0)


def test_un_vinculo_manual_se_limpia() -> None:
    assert manual_relationship("custom", "  socio en   el salón ", "  revisar  ") == (
        RelationshipType.CUSTOM,
        "socio en el salón",
        "revisar",
    )
    assert manual_relationship("family", None, "   ") == (RelationshipType.FAMILY, None, None)


@pytest.mark.parametrize(
    ("kind", "label", "notes", "message"),
    [
        ("enemigo", None, None, "no existe"),
        ("custom", "   ", None, "necesita su etiqueta"),
        ("family", "primo", None, "Solo un vínculo «otro»"),
        ("custom", "x" * (CUSTOM_LABEL_MAX_CHARS + 1), None, "etiqueta admite"),
        ("owns", None, "x" * (RELATIONSHIP_NOTES_MAX_CHARS + 1), "nota admite"),
    ],
)
def test_lo_que_no_es_un_vinculo_valido(
    kind: str, label: str | None, notes: str | None, message: str
) -> None:
    with pytest.raises(RelationshipValidationError, match=message):
        manual_relationship(kind, label, notes)
