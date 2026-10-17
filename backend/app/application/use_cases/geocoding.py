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
    UNKNOWN_CONFIDENCE,
    Choice,
    Mention,
    Place,
    Precision,
    Resolution,
    disambiguate,
    is_mexico_name,
    mark_primary,
    most_general,
)
from app.domain.names import normalize_name
from app.domain.region import RegionLevel


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
        return mark_primary(resolved, self._min_confidence)

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
        candidates = [p for p in await self._gazetteer.exact(name) if p.country_code == MEXICO_ISO3]
        confidence_factor = 1.0
        if not candidates:
            similar = await self._gazetteer.similar(name, FUZZY_MIN_SIMILARITY)
            candidates = [place for place, _ in similar]
            confidence_factor = FUZZY_CONFIDENCE_FACTOR
        if mention.kind_hint is not None:
            hinted = [c for c in candidates if c.level is mention.kind_hint]
            candidates = hinted or candidates
        if mention.state_hint and (hint := await self._state_of(mention.state_hint)):
            in_state = [c for c in candidates if hint in (c.state_code, c.code)]
            candidates = in_state or candidates
        choice = disambiguate(most_general(candidates), context, searched)
        return await self._from_choice(mention, choice, confidence_factor)

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
