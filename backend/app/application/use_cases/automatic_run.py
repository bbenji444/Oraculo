"""Qué busca cada corrida automática del monitor FGR (F12.8, ADR-0031).

El reloj de Celery lanza una corrida a las 07:00, 15:00 y 23:00 de la Ciudad
de México. Este caso de uso arma su petición, la misma que haría una persona
en Explorar:
- **concepto:** «Fiscalia General de la Republica» (con su regla FGR federal);
- **región:** todo México: la geolocalización reparte las notas por estado;
- **fechas:** solo las horas desde la corrida programada anterior del horario
  único (``RunSchedule.window``, ADR-0040);
- **fuentes:** solo las gratis, Google News RSS y el índice local.

Lo que ya se vio en otra corrida se reutiliza sin volver a pagar a la IA (caché
de §10), así que repetir días no cuesta.

No hace: no corre la búsqueda ni arma el reporte (eso es ``worker/automatic_jobs``).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.application.clock import MEXICO_CITY
from app.application.pagination import NameCursor
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.ports.regions import RegionRepositoryPort
from app.application.use_cases.plan_search import SearchRequest
from app.domain.errors import DomainError
from app.domain.names import normalize_name
from app.domain.queries import DateWindow, Provider
from app.domain.schedule import RunSchedule
from app.domain.search import SearchTrigger

# Conceptos por página al buscar el del monitor (paginación por cursor).
_PAGE = 100


class AutomaticRunConfigError(DomainError):
    """La corrida no se puede armar: falta el concepto o la región configurados.

    Pasa si alguien borró el concepto FGR o si la configuración nombra una
    región que no existe. La corrida no se lanza y queda en los logs.
    """

    code = "automatic_run_config"


@dataclass(frozen=True, slots=True)
class AutomaticProfile:
    """El perfil fijo de las corridas automáticas (sale de la configuración).

    Attributes:
        concept: Nombre del concepto que se busca.
        region_code: Clave de la región (``MEX``: todo México).
        sources: Fuentes, siempre las mismas para que las corridas se comparen.
        user_id: Firma de las corridas en la bitácora.
        margin_minutes: Minutos extra antes del inicio de la ventana; 0 es
            estricto (decisión de Benji, 28/10/2026).
    """

    concept: str
    region_code: str
    sources: tuple[Provider, ...]
    user_id: str
    margin_minutes: int = 0


class PrepareAutomaticRun:
    """Arma la petición de una corrida automática."""

    def __init__(
        self,
        concepts: ConceptRepositoryPort,
        regions: RegionRepositoryPort,
        profile: AutomaticProfile,
    ) -> None:
        """Recibe las piezas.

        Args:
            concepts: Conceptos (para encontrar el del monitor).
            regions: Catálogo de regiones.
            profile: El perfil fijo.
        """
        self._concepts = concepts
        self._regions = regions
        self._profile = profile

    async def request(self, scheduled_for: datetime, schedule: RunSchedule) -> SearchRequest:
        """La petición de la corrida programada para ``scheduled_for``.

        Cubre solo las horas desde la corrida anterior del horario: con 07:00,
        15:00 y 23:00, la de las 07:00 va de las 23:00 de ayer a las 07:00. A
        los buscadores se les piden esos días y el pipeline descarta lo
        publicado fuera de las horas.

        Args:
            scheduled_for: Hora programada de la corrida (CDMX).
            schedule: El horario vigente (para saber cuál fue la anterior).

        Returns:
            La petición, marcada como automática.

        Raises:
            AutomaticRunConfigError: Si no existe el concepto o la región.
        """
        concept_id = await self._concept_id()
        region = await self._regions.get_by_code(self._profile.region_code)
        if region is None:
            raise AutomaticRunConfigError(
                f"No existe la región {self._profile.region_code} del monitor automático.",
                {"region": self._profile.region_code},
            )
        hours = schedule.window(scheduled_for, timedelta(minutes=self._profile.margin_minutes))
        local_start = hours.start.astimezone(MEXICO_CITY)
        local_end = hours.end.astimezone(MEXICO_CITY)
        return SearchRequest(
            user_id=self._profile.user_id,
            concept_ids=(concept_id,),
            region_id=region.id,
            window=DateWindow.between(local_start.date(), local_end.date()),
            providers=self._profile.sources,
            trigger=SearchTrigger.AUTOMATIC,
            scheduled_for=scheduled_for,
            time_window=hours,
        )

    async def _concept_id(self) -> int:
        wanted = normalize_name(self._profile.concept)
        after: NameCursor | None = None
        while page := await self._concepts.list_concepts(None, after, _PAGE):
            for concept in page:
                if concept.data.name_norm == wanted:
                    return concept.id
            last = page[-1]
            after = NameCursor(last.data.name_norm, last.id)
        raise AutomaticRunConfigError(
            f"No existe el concepto «{self._profile.concept}» del monitor automático; "
            "créalo con make seed.",
            {"concepto": self._profile.concept},
        )
