"""Casos de uso de los envíos programados (ADR-0046), con piezas en memoria."""

from datetime import datetime, timedelta

import pytest

from app.application.clock import MEXICO_CITY
from app.application.use_cases.delivery_schedules import (
    ManageSchedules,
    PendingRuns,
    ScheduleScope,
    StarterSchedule,
    StarterTemplate,
    recipients_of,
)
from app.domain.concept import ConceptDraft
from app.domain.deliveries import RecipientDraft
from app.domain.delivery_schedules import MAX_DAILY_RUNS_USER, ScheduleDraft
from app.domain.errors import DeliveryNotFoundError, DeliveryValidationError
from app.domain.schedule import RunSchedule
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_deliveries import FakeDeliveryStore
from tests.unit.fake_delivery_schedules import FakeDeliveryScheduleStore
from tests.unit.fake_regions import CDMX, MEXICO, FakeRegionRepository

pytestmark = pytest.mark.anyio

ANA = ScheduleScope("ana", MAX_DAILY_RUNS_USER)
BENJI = ScheduleScope("benji", 8, is_superuser=True)
FGR = "Fiscalia General de la Republica"
GRACE = timedelta(minutes=10)
AT_1600 = datetime(2026, 11, 11, 16, 0, tzinfo=MEXICO_CITY)


class World:
    def __init__(self) -> None:
        self.schedules = FakeDeliveryScheduleStore()
        self.recipients = FakeDeliveryStore()
        self.concepts = FakeConceptRepository()
        self.regions = FakeRegionRepository()
        for name in (FGR, "Extorsión"):
            self.concepts.add(
                ConceptDraft.validated(
                    name=name,
                    description="",
                    keywords=(name,),
                    exclude_terms=(),
                    color="#00D2FF",
                    is_active=True,
                )
            )

    def manage(self) -> ManageSchedules:
        return ManageSchedules(self.schedules, self.recipients, self.concepts, self.regions)

    async def email(self, owner: str, address: str, *, active: bool = True) -> int:
        draft = RecipientDraft.validated(owner, address, None, active)
        return (await self.recipients.create_recipient(draft, owner)).id


def schedule(
    times: tuple[int, ...], *, recipients: tuple[int, ...] = (), concept: int = 2
) -> ScheduleDraft:
    return ScheduleDraft.validated(
        name="Extorsión CDMX",
        concept_ids=[concept],
        region_id=CDMX.id,
        times=list(times),
        recipient_ids=list(recipients),
    )


async def test_un_usuario_arma_su_envio_a_las_horas_que_quiera() -> None:
    world = World()
    mail = await world.email("ana", "ana@x.mx")

    saved = await world.manage().create(schedule((960, 1200), recipients=(mail,)), ANA)

    assert (saved.owner, saved.data.schedule.times, saved.data.recipient_ids) == (
        "ana",
        (960, 1200),
        (mail,),
    )


async def test_un_usuario_no_pasa_de_3_corridas_al_dia() -> None:
    world = World()
    await world.manage().create(schedule((420, 900)), ANA)
    # Lo de otra persona no cuenta para su tope.
    await world.manage().create(schedule((480, 600, 720, 840)), BENJI)

    with pytest.raises(DeliveryValidationError, match="hasta 3 corridas"):
        await world.manage().create(schedule((1000, 1200)), ANA)
    third = await world.manage().create(schedule((1200,)), ANA)
    # Editar uno no cuenta dos veces sus propias horas.
    await world.manage().update(third.id, schedule((1260,)), ANA)


async def test_solo_se_manda_a_sus_propios_correos() -> None:
    world = World()
    ajeno = await world.email("benji", "benji@hotmail.com")

    with pytest.raises(DeliveryValidationError, match="correos"):
        await world.manage().create(schedule((960,), recipients=(ajeno,)), ANA)


async def test_temas_y_region_deben_existir() -> None:
    world = World()

    with pytest.raises(DeliveryValidationError, match="temas"):
        await world.manage().create(schedule((960,), concept=99), ANA)
    bad_region = ScheduleDraft.validated(name="X", concept_ids=[1], region_id=999, times=[960])
    with pytest.raises(DeliveryValidationError, match="región"):
        await world.manage().create(bad_region, ANA)


async def test_el_superusuario_edita_el_envio_de_otra_persona_sin_cambiar_su_dueno() -> None:
    world = World()
    mail = await world.email("ana", "ana@x.mx")
    own = await world.manage().create(schedule((420,), recipients=(mail,)), ANA)

    edited = await world.manage().update(own.id, schedule((480,), recipients=(mail,)), BENJI)

    assert (edited.owner, edited.data.schedule.times) == ("ana", (480,))


async def test_nadie_edita_ni_borra_lo_ajeno() -> None:
    world = World()
    own = await world.manage().create(schedule((420,)), BENJI)
    world.schedules.visible_to = "ana"  # como la seguridad por filas

    with pytest.raises(DeliveryNotFoundError):
        await world.manage().update(own.id, schedule((480,)), ANA)
    with pytest.raises(DeliveryNotFoundError):
        await world.manage().delete(own.id)
    world.schedules.visible_to = None
    await world.manage().delete(own.id)
    assert world.schedules.schedules == {}


async def test_cada_persona_nueva_empieza_con_la_fgr_de_siempre() -> None:
    world = World()
    template = StarterTemplate("Monitor FGR", FGR, "MEX", RunSchedule.from_hours((7, 15, 23)))

    given = await StarterSchedule(world.schedules, world.concepts, world.regions, template).give(
        "ana"
    )

    assert given is not None
    assert (given.owner, given.data.name, given.data.region_id) == ("ana", "Monitor FGR", MEXICO.id)
    assert (given.data.schedule.times, given.data.recipient_ids) == ((420, 900, 1380), ())
    missing = StarterTemplate("X", "No existe", "MEX", RunSchedule.from_hours((7,)))
    assert (
        await StarterSchedule(world.schedules, world.concepts, world.regions, missing).give("pepe")
        is None
    )


async def test_el_reloj_lanza_cada_corrida_una_sola_vez_y_solo_si_tiene_correos() -> None:
    world = World()
    mail = await world.email("ana", "ana@x.mx")
    await world.manage().create(schedule((960,), recipients=(mail,)), ANA)
    await world.manage().create(schedule((960,), concept=1), BENJI)  # sin correos
    pending = PendingRuns(world.schedules, GRACE)

    first = await pending.execute(AT_1600)
    again = await pending.execute(AT_1600 + timedelta(minutes=1))

    assert ([r.schedule_ids for r in first], again) == ([(1,)], [])


async def test_la_corrida_va_a_los_correos_activos_de_sus_envios_sin_repetir() -> None:
    world = World()
    ana = await world.email("ana", "ana@x.mx")
    apagado = await world.email("ana", "viejo@x.mx", active=False)
    benji = await world.email("benji", "benji@hotmail.com")
    first = await world.manage().create(schedule((960,), recipients=(ana, apagado)), ANA)
    second = await world.manage().create(schedule((960,), recipients=(ana,)), ANA)
    third = await world.manage().create(schedule((960,), recipients=(benji,)), BENJI)

    found = await recipients_of(
        world.schedules, world.recipients, [first.id, second.id, third.id, 99]
    )

    assert sorted(r.data.email or "" for r in found) == ["ana@x.mx", "benji@hotmail.com"]
