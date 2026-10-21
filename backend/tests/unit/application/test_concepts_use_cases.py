"""Casos de uso de conceptos con repositorios en memoria."""

from datetime import date
from typing import Any

import pytest

from app.application.audit import CONCEPT_CREATED, CONCEPT_DELETED, CONCEPT_UPDATED, Actor
from app.application.use_cases.concepts import (
    ConceptInput,
    CreateConcept,
    DeleteConcept,
    GetConcept,
    ListConcepts,
    PreviewConceptQueries,
    UpdateConcept,
)
from app.domain.concept import ConceptChanges
from app.domain.errors import (
    ConceptNameTakenError,
    ConceptNotFoundError,
    ConceptValidationError,
    InvalidRequestError,
    RegionNotFoundError,
)
from app.domain.queries import Provider
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import CDMX, IZTAPALAPA, FakeRegionRepository, make_region

ACTOR = Actor("desarrollo", "127.0.0.1")
TODAY = date(2026, 10, 16)


def concept_input(**overrides: Any) -> ConceptInput:
    data: dict[str, Any] = {
        "name": "Ciberseguridad",
        "description": "Ataques informáticos",
        "keywords": ("ciberataque", "hackeo", "ransomware", "filtración de datos", "phishing"),
        "exclude_terms": ("curso", "webinar", "diplomado"),
        "color": "#2E86DE",
    }
    data.update(overrides)
    return ConceptInput(**data)


@pytest.fixture
def repo() -> FakeConceptRepository:
    return FakeConceptRepository()


# --- Crear -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_crear_guarda_y_registra_en_la_bitacora(repo: FakeConceptRepository) -> None:
    concept = await CreateConcept(repo).execute(concept_input(name="  Ciberseguridad "), ACTOR)

    assert concept.data.name == "Ciberseguridad"
    assert concept.created_by == "desarrollo"
    [(entity_id, entry)] = repo.audit
    assert (entity_id, entry.action, entry.actor) == (concept.id, CONCEPT_CREATED, ACTOR)
    assert entry.payload["after"] == {
        "name": "Ciberseguridad",
        "description": "Ataques informáticos",
        "keywords": ["ciberataque", "hackeo", "ransomware", "filtración de datos", "phishing"],
        "exclude_terms": ["curso", "webinar", "diplomado"],
        "color": "#2E86DE",
        "is_active": True,
    }


@pytest.mark.anyio
async def test_nombre_repetido_sin_importar_mayusculas_ni_acentos(
    repo: FakeConceptRepository,
) -> None:
    await CreateConcept(repo).execute(concept_input(name="Extorsión"), ACTOR)

    with pytest.raises(ConceptNameTakenError, match="Ya existe un concepto llamado"):
        await CreateConcept(repo).execute(concept_input(name="EXTORSION"), ACTOR)
    assert len(repo.audit) == 1


@pytest.mark.anyio
async def test_crear_invalido_no_guarda_nada(repo: FakeConceptRepository) -> None:
    with pytest.raises(ConceptValidationError):
        await CreateConcept(repo).execute(concept_input(keywords=()), ACTOR)

    assert repo.concepts == {}
    assert repo.audit == []


# --- Leer y listar ------------------------------------------------------------


@pytest.mark.anyio
async def test_obtener_inexistente_es_404(repo: FakeConceptRepository) -> None:
    with pytest.raises(ConceptNotFoundError):
        await GetConcept(repo).execute(99)


@pytest.mark.anyio
async def test_obtener_existente(repo: FakeConceptRepository) -> None:
    created = await CreateConcept(repo).execute(concept_input(), ACTOR)

    assert await GetConcept(repo).execute(created.id) == created


@pytest.mark.anyio
async def test_lista_en_paginas_alfabeticas_sin_repetir_ni_saltar(
    repo: FakeConceptRepository,
) -> None:
    for name in ("Secuestro", "Extorsión", "Ciberseguridad", "Robo de vehículos", "Abigeato"):
        await CreateConcept(repo).execute(concept_input(name=name), ACTOR)

    names: list[str] = []
    cursor = None
    while True:
        page = await ListConcepts(repo).execute(cursor=cursor, limit=2)
        names.extend(c.data.name for c in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert names == ["Abigeato", "Ciberseguridad", "Extorsión", "Robo de vehículos", "Secuestro"]


@pytest.mark.anyio
async def test_lista_solo_activos(repo: FakeConceptRepository) -> None:
    await CreateConcept(repo).execute(concept_input(name="Activo"), ACTOR)
    await CreateConcept(repo).execute(concept_input(name="Inactivo", is_active=False), ACTOR)

    page = await ListConcepts(repo).execute(active=True)

    assert [c.data.name for c in page.items] == ["Activo"]


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [0, 201])
async def test_limite_fuera_de_rango(repo: FakeConceptRepository, limit: int) -> None:
    with pytest.raises(InvalidRequestError, match="límite"):
        await ListConcepts(repo).execute(limit=limit)


# --- Editar ------------------------------------------------------------------------


@pytest.mark.anyio
async def test_desactivar_registra_solo_el_campo_que_cambio(repo: FakeConceptRepository) -> None:
    created = await CreateConcept(repo).execute(concept_input(), ACTOR)

    updated = await UpdateConcept(repo).execute(created.id, ConceptChanges(is_active=False), ACTOR)

    assert updated.data.is_active is False
    _, entry = repo.audit[-1]
    assert entry.action == CONCEPT_UPDATED
    assert entry.payload["changed"] == ["is_active"]


@pytest.mark.anyio
async def test_editar_sin_cambios_no_escribe_ni_registra(repo: FakeConceptRepository) -> None:
    created = await CreateConcept(repo).execute(concept_input(), ACTOR)

    result = await UpdateConcept(repo).execute(
        created.id, ConceptChanges(name="Ciberseguridad", color="#2e86de"), ACTOR
    )

    assert result == created
    assert len(repo.audit) == 1


@pytest.mark.anyio
async def test_renombrar_a_un_nombre_ocupado(repo: FakeConceptRepository) -> None:
    await CreateConcept(repo).execute(concept_input(name="Secuestro"), ACTOR)
    other = await CreateConcept(repo).execute(concept_input(name="Plagio"), ACTOR)

    with pytest.raises(ConceptNameTakenError):
        await UpdateConcept(repo).execute(other.id, ConceptChanges(name="secuestro"), ACTOR)


@pytest.mark.anyio
async def test_cambiar_solo_mayusculas_del_propio_nombre_se_permite(
    repo: FakeConceptRepository,
) -> None:
    created = await CreateConcept(repo).execute(concept_input(name="secuestro"), ACTOR)

    updated = await UpdateConcept(repo).execute(created.id, ConceptChanges(name="Secuestro"), ACTOR)

    assert updated.data.name == "Secuestro"


@pytest.mark.anyio
async def test_editar_inexistente_es_404(repo: FakeConceptRepository) -> None:
    with pytest.raises(ConceptNotFoundError):
        await UpdateConcept(repo).execute(99, ConceptChanges(is_active=False), ACTOR)


# --- Borrar ------------------------------------------------------------------------


@pytest.mark.anyio
async def test_borrar_sin_busquedas_es_fisico(repo: FakeConceptRepository) -> None:
    created = await CreateConcept(repo).execute(concept_input(), ACTOR)

    result = await DeleteConcept(repo).execute(created.id, ACTOR)

    assert result.logical is False
    assert repo.deleted == {}
    _, entry = repo.audit[-1]
    assert (entry.action, entry.payload["logical"]) == (CONCEPT_DELETED, False)


@pytest.mark.anyio
async def test_borrar_con_busquedas_es_logico(repo: FakeConceptRepository) -> None:
    created = await CreateConcept(repo).execute(concept_input(), ACTOR)
    repo.used_in_searches.add(created.id)

    result = await DeleteConcept(repo).execute(created.id, ACTOR)

    assert result.logical is True
    assert created.id in repo.deleted
    assert await repo.get(created.id) is None


@pytest.mark.anyio
async def test_borrar_inexistente_es_404(repo: FakeConceptRepository) -> None:
    with pytest.raises(ConceptNotFoundError):
        await DeleteConcept(repo).execute(99, ACTOR)


# --- Probar concepto -------------------------------------------------------------


def preview_use_case(
    repo: FakeConceptRepository, regions: FakeRegionRepository | None = None
) -> PreviewConceptQueries:
    return PreviewConceptQueries(repo, regions or FakeRegionRepository(), today=lambda: TODAY)


@pytest.mark.anyio
async def test_probar_concepto_guardado_en_iztapalapa(repo: FakeConceptRepository) -> None:
    created = await CreateConcept(repo).execute(concept_input(), ACTOR)

    preview = await preview_use_case(repo).for_saved(created.id, IZTAPALAPA.id, 7)

    assert preview.concept_name == "Ciberseguridad"
    assert preview.region.breadcrumb == "México › Ciudad de México › Iztapalapa"
    assert preview.window.describe() == "últimos 7 días"
    assert [q.provider for q in preview.queries] == list(Provider)
    assert preview.queries[0].text == (
        '(ciberataque OR hackeo OR ransomware OR "filtración de datos" OR phishing) '
        "Iztapalapa -curso -webinar -diplomado"
    )
    assert preview.total_credits == 1


@pytest.mark.anyio
async def test_probar_borrador_no_guarda_nada(repo: FakeConceptRepository) -> None:
    preview = await preview_use_case(repo).for_draft(concept_input(), CDMX.id, 30)

    assert '("Ciudad de México" OR CDMX)' in preview.queries[0].text
    assert preview.queries[1].text.endswith("when:30d")
    assert repo.concepts == {}
    assert repo.audit == []


@pytest.mark.anyio
async def test_probar_con_alcaldia_de_nombre_repetido_agrega_el_estado(
    repo: FakeConceptRepository,
) -> None:
    regions = FakeRegionRepository()
    for region in (
        make_region(10, "Benito Juárez", parent_id=CDMX.id, code="09014", prefix="Alcaldía"),
        make_region(11, "Benito Juárez", code="23005"),
    ):
        regions.regions[region.id] = region

    preview = await preview_use_case(repo, regions).for_draft(concept_input(), 10, 7)

    assert '"Benito Juárez" ("Ciudad de México" OR CDMX) -curso' in preview.queries[0].text


@pytest.mark.anyio
async def test_probar_con_region_inexistente(repo: FakeConceptRepository) -> None:
    with pytest.raises(RegionNotFoundError):
        await preview_use_case(repo).for_draft(concept_input(), 999, 7)


@pytest.mark.anyio
async def test_probar_concepto_inexistente(repo: FakeConceptRepository) -> None:
    with pytest.raises(ConceptNotFoundError):
        await preview_use_case(repo).for_saved(999, IZTAPALAPA.id, 7)


@pytest.mark.anyio
async def test_probar_con_rango_invalido(repo: FakeConceptRepository) -> None:
    with pytest.raises(InvalidRequestError, match="1 a 90"):
        await preview_use_case(repo).for_draft(concept_input(), IZTAPALAPA.id, 120)


@pytest.mark.anyio
async def test_probar_solo_muestra_los_proveedores_que_se_usarian(
    repo: FakeConceptRepository,
) -> None:
    # Con GDELT y el RSS de Google apagados (ADR-0011 y 0012) la búsqueda real
    # manda 2 consultas; "Probar concepto" decía 4.
    use = PreviewConceptQueries(
        repo,
        FakeRegionRepository(),
        providers=(Provider.SEARCHAPI, Provider.LOCAL_INDEX),
        today=lambda: TODAY,
    )

    preview = await use.for_draft(concept_input(), IZTAPALAPA.id, 7)

    assert [q.provider for q in preview.queries] == [Provider.SEARCHAPI, Provider.LOCAL_INDEX]
