"""Reglas puras para reconocer a la misma entidad escrita de otra forma (Fase 9.5).

Los nombres son inventados: las pruebas no guardan datos de personas reales.
"""

import random
from itertools import combinations

import pytest

from app.domain.entity_resolution import (
    MERGE_REASON_LABEL,
    MergeCandidate,
    MergeReason,
    ResolutionRoot,
    check_merge,
    check_split,
    entity_name_norm,
    merge_reasons,
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


# --- Qué pares se sugieren -------------------------------------------------------


def root(
    entity_id: int,
    label: str,
    *,
    kind: EntityType = EntityType.PERSON,
    aliases: tuple[str, ...] = (),
    trigrams: frozenset[str] = frozenset(),
) -> ResolutionRoot:
    names = frozenset({label, *aliases})
    return ResolutionRoot(entity_id, kind, label, names, trigrams)


def test_mismo_nombre_y_alias_en_comun_solo_dentro_del_mismo_tipo() -> None:
    roots = [
        root(1, "JULIAN N"),
        root(2, "JULIAN N"),
        root(3, "RAMON SALAS", aliases=("RAMY STYLE",)),
        root(4, "RAMY STYLE"),
        root(5, "RAMY STYLE", kind=EntityType.ORG),
    ]

    found = merge_reasons(roots, [])

    assert found == {
        (1, 2): frozenset({MergeReason.SAME_NAME, MergeReason.SHARED_NAME}),
        (3, 4): frozenset({MergeReason.SHARED_NAME}),
    }


def test_un_par_descartado_no_se_sugiere() -> None:
    assert merge_reasons([root(1, "JULIAN N"), root(2, "JULIAN N")], [(1, 2)]) == {}


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b)


def test_el_filtro_por_prefijo_encuentra_lo_mismo_que_comparar_todos_contra_todos() -> None:
    # Conjuntos al azar (semilla fija): cada «nombre» de base tiene variantes
    # con uno o dos trigramas de más o de menos (como un nombre con y sin
    # segundo apellido). El atajo no puede perder ni inventar pares.
    rng = random.Random(95)  # noqa: S311 — datos de prueba con semilla fija, no criptografía
    alphabet = [f"t{n}" for n in range(60)]
    sets = []
    for _ in range(40):
        base = set(rng.sample(alphabet, 20))
        for _ in range(6):
            variant = set(base)
            for _ in range(rng.randint(0, 2)):
                variant.discard(rng.choice(sorted(variant)))
            variant.update(rng.sample(alphabet, rng.randint(0, 2)))
            sets.append(frozenset(variant))
    roots = [root(n + 1, f"N{n}", trigrams=s) for n, s in enumerate(sets)]
    for threshold in (0.5, 0.8, 0.9):
        expected = {
            (a.entity_id, b.entity_id)
            for a, b in combinations(roots, 2)
            if jaccard(a.trigrams, b.trigrams) >= threshold - 1e-9
        }
        found = {
            pair
            for pair, reasons in merge_reasons(roots, [], threshold).items()
            if MergeReason.SIMILAR_NAME in reasons
        }
        assert found == expected
        assert expected  # que la prueba sí compare algo


def test_el_umbral_exacto_cuenta() -> None:
    # 9 trigramas en común de 10 distintos: 0.9 justo (0.9 × 10 en flotante es
    # 9.000000000000002 y no debe perderse).
    first = frozenset(f"t{n}" for n in range(9))
    second = first | {"t9"}
    roots = [root(1, "A", trigrams=first), root(2, "B", trigrams=second)]

    assert merge_reasons(roots, [], 0.9) == {(1, 2): frozenset({MergeReason.SIMILAR_NAME})}
