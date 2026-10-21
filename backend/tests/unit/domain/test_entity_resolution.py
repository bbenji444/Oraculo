"""Reglas puras para reconocer a la misma entidad escrita de otra forma (Fase 9.5).

Los nombres son inventados: las pruebas no guardan datos de personas reales.
"""

import pytest

from app.domain.entity_resolution import (
    MERGE_REASON_LABEL,
    MergeCandidate,
    MergeReason,
    check_merge,
    check_split,
    entity_name_norm,
    ordered_ids,
    strongest_reason,
)
from app.domain.errors import EntityMergeError
from app.domain.investigation import EntityType, ReviewStatus


@pytest.mark.parametrize(
    "written",
    ["Julián N", "Julián “N”", "Julián 'N'", "Julián «N»", 'Julián "N"', "julián  ‘N’"],
)
def test_las_comillas_no_separan_un_nombre(written: str) -> None:
    # En las notas mexicanas «Julián “N”» es la forma normal de nombrar a un
    # detenido; cada medio usa otras comillas.
    assert entity_name_norm(written) == "JULIAN N"


def test_se_conserva_la_regla_del_proyecto() -> None:
    # Mayúsculas, sin acentos, con Ñ y sin espacios repetidos (CLAUDE.md §6.3).
    assert entity_name_norm("  Peña   Nieto ") == "PEÑA NIETO"


def test_una_comilla_dentro_de_una_palabra_la_parte_igual_en_todas_sus_formas() -> None:
    assert entity_name_norm("O'Higgins") == entity_name_norm("O’Higgins") == "O HIGGINS"


def test_solo_comillas_queda_vacio() -> None:
    assert entity_name_norm(" “” '' ") == ""


# --- Motivos de una sugerencia ---------------------------------------------------


def test_el_motivo_mas_seguro_gana() -> None:
    reasons = {MergeReason.SIMILAR_NAME, MergeReason.SHARED_NAME}

    assert strongest_reason(reasons) is MergeReason.SHARED_NAME
    assert strongest_reason([MergeReason.SAME_NAME, *reasons]) is MergeReason.SAME_NAME


def test_sin_motivo_no_hay_sugerencia() -> None:
    with pytest.raises(ValueError, match="al menos un motivo"):
        strongest_reason([])


def test_cada_motivo_tiene_su_etiqueta_en_espanol() -> None:
    assert set(MERGE_REASON_LABEL) == set(MergeReason)
    assert MERGE_REASON_LABEL[MergeReason.SHARED_NAME] == "nombre o alias en común"


def test_un_par_se_ordena_con_el_menor_primero() -> None:
    assert ordered_ids(9, 4) == (4, 9)
    with pytest.raises(EntityMergeError):
        ordered_ids(4, 4)


# --- Fusionar --------------------------------------------------------------------


def candidate(
    entity_id: int,
    *,
    kind: EntityType = EntityType.PERSON,
    review: ReviewStatus = ReviewStatus.SUGGESTED,
    merged_into: int | None = None,
) -> MergeCandidate:
    return MergeCandidate(entity_id, kind, review, merged_into)


def test_una_sugerencia_se_une_a_una_confirmada() -> None:
    # El caso de la 9.4: las menciones nuevas de una persona ya confirmada.
    check_merge(candidate(1, review=ReviewStatus.CONFIRMED), candidate(2))
    # Dos confirmadas que resultan ser la misma también se unen.
    confirmed = ReviewStatus.CONFIRMED
    check_merge(candidate(1, review=confirmed), candidate(2, review=confirmed))


@pytest.mark.parametrize(
    ("keep", "merge", "message"),
    [
        (candidate(1), candidate(1), "dos entidades distintas"),
        (candidate(1), candidate(2, kind=EntityType.ORG), "mismo tipo"),
        (candidate(1, review=ReviewStatus.DISCARDED), candidate(2), "descartada"),
        (candidate(1), candidate(2, review=ReviewStatus.DISCARDED), "descartada"),
        (candidate(1, merged_into=7), candidate(2), "ya está unida"),
        (candidate(1), candidate(2, merged_into=1), "ya está unida"),
        (candidate(1), candidate(2, review=ReviewStatus.CONFIRMED), "quedar la entidad confirmada"),
    ],
)
def test_lo_que_no_se_puede_unir(keep: MergeCandidate, merge: MergeCandidate, message: str) -> None:
    with pytest.raises(EntityMergeError, match=message):
        check_merge(keep, merge)


# --- Separar menciones -----------------------------------------------------------


def test_se_separan_algunas_menciones_propias() -> None:
    check_split([2], [1, 2, 3])


@pytest.mark.parametrize(
    ("selected", "message"),
    [([], "al menos una"), ([4], "propias"), ([1, 2, 3], "deja al menos una")],
)
def test_lo_que_no_se_puede_separar(selected: list[int], message: str) -> None:
    with pytest.raises(EntityMergeError, match=message):
        check_split(selected, [1, 2, 3])
