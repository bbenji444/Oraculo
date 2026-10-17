"""Volver a ubicar las notas de una búsqueda sin llamar a la IA (§11).

Cuando cambian las reglas del geolocalizador o el catálogo (por ejemplo,
alias nuevos), las menciones de lugar ya guardadas se resuelven de nuevo
contra el catálogo y se recalcula ``in_region``. No cuesta nada: la IA no
participa.

No hace: no vuelve a extraer el texto ni a resumir.
"""

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.geocoding import GazetteerPort
from app.application.ports.search_store import RelocationStorePort, SearchStorePort
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.run_search import SearchNotFoundError
from app.domain.errors import NotFoundError
from app.domain.geocoding import Place
from app.domain.search import in_region


@dataclass(frozen=True, slots=True)
class Relocation:
    """Cómo cambió la ubicación principal de una nota.

    Attributes:
        article_id: Nota.
        title: Título.
        before: Ubicación principal anterior.
        after: Ubicación principal nueva.
        in_region: Si ahora cae en la región buscada.
    """

    article_id: int
    title: str
    before: Place | None
    after: Place | None
    in_region: bool | None

    @property
    def changed(self) -> bool:
        """``True`` si cambió la ubicación principal."""
        return self.before != self.after


class RelocateSearch:
    """Resuelve otra vez las menciones guardadas de una búsqueda."""

    def __init__(
        self,
        searches: SearchStorePort,
        store: RelocationStorePort,
        gazetteer: GazetteerPort,
        geocoder: GeocodeMentions,
    ) -> None:
        """Recibe las piezas.

        Args:
            searches: Búsquedas (para la región buscada).
            store: Menciones y ubicaciones guardadas.
            gazetteer: Catálogo.
            geocoder: Geolocalizador con las reglas vigentes.
        """
        self._searches = searches
        self._store = store
        self._gazetteer = gazetteer
        self._geocoder = geocoder

    async def run(self, search_id: UUID) -> list[Relocation]:
        """Vuelve a ubicar todas las notas de la búsqueda.

        Args:
            search_id: Búsqueda.

        Returns:
            Una entrada por nota, con su antes y después.

        Raises:
            SearchNotFoundError: Si la búsqueda no existe.
            NotFoundError: Si su región ya no está en el catálogo.
        """
        search = await self._searches.load(search_id)
        if search is None:
            raise SearchNotFoundError(f"No existe la búsqueda {search_id}.")
        searched = await self._gazetteer.by_code(search.region_code)
        if searched is None:
            raise NotFoundError(f"No existe la región {search.region_code} en el catálogo.")
        relocations = []
        for item in await self._store.search_mentions(search_id):
            before = await self._gazetteer.by_code(item.primary_code) if item.primary_code else None
            after = before
            if item.mentions:
                resolutions = await self._geocoder.run(item.mentions, searched)
                await self._store.save_locations(item.article_id, resolutions)
                after = next((r.place for r in resolutions if r.is_primary), None)
            inside = in_region(after, searched)
            await self._store.set_in_region(search_id, item.article_id, inside)
            relocations.append(Relocation(item.article_id, item.title, before, after, inside))
        await self._store.merge_progress(
            search_id,
            {
                "in_region": sum(1 for r in relocations if r.in_region is True),
                "out_of_region": sum(1 for r in relocations if r.in_region is False),
                "unlocated": sum(1 for r in relocations if r.in_region is None),
            },
        )
        return relocations
