"""Geolocalizar las menciones de lugar de una nota (especificación §11).

Aplica el algoritmo de §11 a todas las menciones que encontró la IA:

1. **Otro país:** se resuelve al país y ahí termina.
2. **Normalizar** (mayúsculas, sin acentos, con Ñ) y buscar por nombre o
   alias ("CDMX", "Edomex", "Neza", "la capital del país").
3. **Coincidencia exacta** en el nivel que sugiere la IA y, si hay pista
   de estado, dentro de ese estado.
4. **Varias coincidencias:** desempate por los estados que nombra la misma
   nota y por la región buscada; si sigue ambigua, se sube al estado común o
   queda sin ubicar (``app.domain.geocoding.disambiguate``).
5. **Sin coincidencia exacta:** nombres parecidos (trigramas ≥ 0.85) con
   confianza reducida.
6. **Ubicación principal:** el lugar del hecho más específico con confianza
   suficiente.
7. **Punto del mapa:** el del catálogo. Nunca coordenadas de la IA.

No hace: no llama a la IA ni guarda nada.
"""

from collections.abc import Sequence

from app.application.ports.geocoding import GazetteerPort
from app.domain.geocoding import (
    DEFAULT_MIN_CONFIDENCE,
    EXACT_CONFIDENCE,
    FUZZY_CONFIDENCE_FACTOR,
    FUZZY_MIN_SIMILARITY,
    MEXICO_ISO3,
    STATE_HINT_CONFIDENCE,
    TIEBREAK_CONFIDENCE,
    UNKNOWN_CONFIDENCE,
    Choice,
    Mention,
    Place,
    Precision,
    Resolution,
    choose_neighborhood,
    disambiguate,
    is_mexico_name,
    mark_primary,
    most_general,
    seat_area,
    strip_generic_prefix,
    strip_leading_article,
)
from app.domain.names import normalize_name
from app.domain.region import RegionLevel

# Clave INEGI de municipio: los 5 primeros dígitos de la de una localidad (ADR-0002).
MUNICIPALITY_CODE_LENGTH = 5


async def search_area(gazetteer: GazetteerPort, searched: Place) -> Place:
    """La zona que de verdad cubre una búsqueda (ver ``seat_area``).

    Args:
        gazetteer: Catálogo.
        searched: Región elegida para la búsqueda.

    Returns:
        Su municipio si es la localidad cabecera homónima; si no, la misma región.
    """
    if searched.level is not RegionLevel.LOCALITY:
        return searched
    return seat_area(searched, await gazetteer.by_code(searched.code[:MUNICIPALITY_CODE_LENGTH]))


class GeocodeMentions:
    """Resuelve las menciones de una nota contra el catálogo."""

    def __init__(
        self, gazetteer: GazetteerPort, min_confidence: float = DEFAULT_MIN_CONFIDENCE
    ) -> None:
        """Recibe el catálogo y el umbral de la ubicación principal.

        Args:
            gazetteer: Búsquedas en ``regions``.
            min_confidence: ``GEO_MIN_CONFIDENCE`` (§11).
        """
        self._gazetteer = gazetteer
        self._min_confidence = min_confidence

    async def run(self, mentions: Sequence[Mention], searched: Place | None) -> list[Resolution]:
        """Resuelve todas las menciones y marca la principal.

        Args:
            mentions: Menciones que encontró la IA (puede no haber ninguna:
                la nota queda "sin ubicación").
            searched: Región de la búsqueda, para desempatar.

        Returns:
            Una resolución por mención, en el mismo orden.
        """
        context = await self._context_states(mentions)
        resolved = [await self._resolve(m, context, searched) for m in mentions]
        return mark_primary(resolved, self._min_confidence, searched)

    async def _state_of(self, name: str) -> str | None:
        """Clave del estado con ese nombre o alias, si es uno solo."""
        states = [
            p
            for p in await self._gazetteer.exact(normalize_name(name))
            if p.level is RegionLevel.STATE
        ]
        return states[0].code if len(states) == 1 else None

    async def _context_states(self, mentions: Sequence[Mention]) -> set[str]:
        """Estados que nombra la nota: pistas de la IA y menciones que son estados."""
        states: set[str] = set()
        for mention in mentions:
            if mention.is_abroad:
                continue
            names = [mention.state_hint, mention.text]
            if is_mexico_name(mention.text) and mention.kind_hint is not RegionLevel.STATE:
                # "México" es el país, no el Estado de México (estado 15).
                names = [mention.state_hint]
            for name in names:
                if name and (code := await self._state_of(name)):
                    states.add(code)
        return states

    async def _resolve(
        self, mention: Mention, context: set[str], searched: Place | None
    ) -> Resolution:
        name = normalize_name(mention.text)
        if not name:
            return Resolution(mention, None, Precision.UNKNOWN, UNKNOWN_CONFIDENCE)
        if mention.is_abroad or mention.kind_hint is RegionLevel.COUNTRY:
            return await self._resolve_country(mention, name)
        hint = await self._state_of(mention.state_hint) if mention.state_hint else None
        bare = strip_generic_prefix(name)
        candidates, confidence_factor = await self._candidates(name, bare)
        if mention.kind_hint is not None:
            hinted = [c for c in candidates if c.level is mention.kind_hint]
            candidates = hinted or candidates
        if hint:
            # El estado que dice la IA manda: un homónimo de otro estado nunca
            # gana (antes "Polanco, CDMX" terminaba en Jalisco).
            candidates = [c for c in candidates if hint in (c.state_code, c.code)]
        choice = disambiguate(most_general(candidates), context, searched)
        resolution = await self._from_choice(mention, choice, confidence_factor)
        if resolution.place is not None:
            return resolution
        state = hint or (searched.state_code if searched is not None else None)
        fallback = await self._inside_state(mention, bare, state) if state and bare else None
        if fallback is not None:
            return fallback
        if hint:
            return await self._state_from_hint(mention, hint)
        return resolution

    async def _candidates(self, name: str, bare: str) -> tuple[list[Place], float]:
        """Coincidencias en INEGI: exactas (con y sin palabra genérica o artículo) o parecidas."""
        for option in dict.fromkeys((name, bare, strip_leading_article(bare))):
            found = [
                p for p in await self._gazetteer.exact(option) if p.country_code == MEXICO_ISO3
            ]
            if option and found:
                return found, 1.0
        if not bare:
            return [], 1.0
        similar = await self._gazetteer.similar(bare, FUZZY_MIN_SIMILARITY)
        return [place for place, _ in similar], FUZZY_CONFIDENCE_FACTOR

    async def _inside_state(self, mention: Mention, bare: str, state: str) -> Resolution | None:
        """Lo que INEGI no tiene, dentro de un estado conocido: colonia o municipio de la IA."""
        if mention.kind_hint not in (None, RegionLevel.LOCALITY):
            return None
        municipality = await self._municipality_of(mention.municipality_hint, state)
        found = choose_neighborhood(
            bare, await self._gazetteer.neighborhoods(bare, state), municipality
        )
        if found is not None:
            place, confidence = found
            return Resolution(mention, place, Precision.LOCALITY, confidence)
        if municipality is not None and (seat := await self._gazetteer.by_code(municipality)):
            # Ni INEGI ni las colonias la tienen ("Parque Bicentenario"), pero
            # la IA dice en qué municipio está: se ubica en el municipio.
            return Resolution(mention, seat, Precision.MUNICIPALITY, TIEBREAK_CONFIDENCE)
        return None

    async def _municipality_of(self, name: str | None, state_code: str) -> str | None:
        """Clave del municipio que sugiere la IA, si es uno solo en ese estado."""
        if not name:
            return None
        core = strip_generic_prefix(normalize_name(name))
        found = {
            p.code
            for p in await self._gazetteer.exact(core)
            if p.level is RegionLevel.MUNICIPALITY and p.state_code == state_code
        }
        return found.pop() if len(found) == 1 else None

    async def _state_from_hint(self, mention: Mention, state_code: str) -> Resolution:
        """Último recurso: el lugar no está en el catálogo, pero sí su estado."""
        state = await self._gazetteer.by_code(state_code)
        if state is None:
            return Resolution(mention, None, Precision.UNKNOWN, UNKNOWN_CONFIDENCE)
        return Resolution(mention, state, Precision.STATE, STATE_HINT_CONFIDENCE)

    async def _resolve_country(self, mention: Mention, name: str) -> Resolution:
        country_name = (
            normalize_name(mention.country) if mention.is_abroad and mention.country else name
        )
        place = await self._gazetteer.country(country_name) or await self._gazetteer.country(name)
        if place is None:
            return Resolution(mention, None, Precision.UNKNOWN, UNKNOWN_CONFIDENCE)
        return Resolution(mention, place, Precision.COUNTRY, EXACT_CONFIDENCE)

    async def _from_choice(self, mention: Mention, choice: Choice, factor: float) -> Resolution:
        place = choice.place
        if place is None and choice.state_code is not None:
            place = await self._gazetteer.by_code(choice.state_code)
        if place is None:
            return Resolution(mention, None, Precision.UNKNOWN, UNKNOWN_CONFIDENCE)
        return Resolution(mention, place, place.precision, choice.confidence * factor)
