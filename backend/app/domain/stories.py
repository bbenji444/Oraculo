"""Historias: el mismo hecho contado por varios medios (F12.1c, ADR-0026).

Nivel 3 de duplicados (ADR-0025). Las notas del mismo hecho no se borran:
se juntan en una historia para que el monitor muestre una tarjeta con
«▸ +N medios». Una historia se identifica con el id de su **primera nota**
(``story_id``); una nota sola no tiene historia.

Regla, calibrada con las 1,450 notas reales del 24/10/2026:

1. Se limpia el título: se quitan los segmentos finales que nombran al
   medio («… – Periódico Zócalo | Noticias de Saltillo…»).
2. Una nota entra a una historia si se parece a **su primera nota** (no a
   cualquiera: unir en cadena juntaba temas enteros, grupos de 61 notas):
   - títulos con parecido ≥ ``SAME_STORY_SIMILARITY``, o
   - parecido por palabras ≥ ``SAME_STORY_TOKEN_SIMILARITY`` **y** una señal:
     el mismo lugar principal (clave INEGI), dos palabras poco comunes en
     común, o el mismo estado y una palabra poco común.
3. A ≤ ``STORY_GAP`` de la última nota de la historia y a ≤ ``STORY_SPAN``
   de la primera.

Las similitudes se reciben como parámetro (rapidfuzz vive en un adaptador),
igual que en ``dedupe``.

No hace: no consulta la base ni decide qué notas revisar.
"""

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.names import normalize_name

# Parecido de títulos (fuzz.ratio) que basta solo: en la calibración, los
# pares ≥ 0.70 a ±2 días fueron casi siempre el mismo hecho.
SAME_STORY_SIMILARITY = 0.70
# Parecido por palabras (fuzz.token_set_ratio) que necesita además una señal.
SAME_STORY_TOKEN_SIMILARITY = 0.60
# Una palabra es «poco común» si aparece en a lo más tantos títulos de la
# ventana (calibrado: «Micky», «Cromo», «Janitzio»; no «balacera» ni «FGR»).
RARE_TOKEN_MAX_TITLES = 8
# Palabras poco comunes en común que bastan como señal sin lugar («Micky» + «Hair»).
RARE_TOKENS_ALONE = 2
# Palabras más cortas no distinguen un hecho («DOS», «DIA»).
MIN_TOKEN_LENGTH = 4
# Distancia máxima a la última nota de la historia y a la primera: la
# historia sigue al hecho unos días, no crece sin fin.
STORY_GAP = timedelta(days=2)
STORY_SPAN = timedelta(days=3)
# Una historia necesita al menos dos notas; una sola no se agrupa.
MIN_STORY_SIZE = 2
# Clave INEGI de estado: los dos primeros dígitos («09» de «09007»). Las
# claves de país (ISO-A3, «MEX») no cuentan como lugar: son muy amplias.
_STATE_DIGITS = 2
_OUTLET_SEPARATOR = re.compile(r"\s+[-–—|]\s+")
_OUTLET_WORDS = frozenset({"NOTICIAS", "PERIODICO", "DIARIO"})
_TOKEN = re.compile(r"[A-ZÑ0-9]+")
_STOPWORDS = frozenset(
    [
        "DESDE",
        "HASTA",
        "COMO",
        "ESTE",
        "ESTA",
        "ESTOS",
        "ESTAS",
        "PARA",
        "POR",
        "CON",
        "SOBRE",
        "ENTRE",
        "TRAS",
        "ANTE",
        "HACIA",
        "SEGUN",
        "DONDE",
        "CUANDO",
        "MAS",
        "MENOS",
        "TODO",
        "TODOS",
        "TODAS",
        "SUS",
        "LOS",
        "LAS",
        "DEL",
        "HOY",
        "AYER",
        "MEXICO",
        "CDMX",
    ]
)

Similarity = Callable[[str, str], float]


@dataclass(frozen=True, slots=True)
class StoryNote:
    """Lo que hace falta de una nota para decidir su historia.

    Attributes:
        article_id: Id en ``articles``.
        title: Título original.
        source_name: Nombre del medio, si se conoce.
        source_domain: Dominio del medio, si se conoce.
        published_at: Fecha de publicación (UTC).
        place_code: Clave de su ubicación principal, si tiene.
        story_id: Historia actual, si ya tiene.
    """

    article_id: int
    title: str
    source_name: str | None
    source_domain: str | None
    published_at: datetime
    place_code: str | None = None
    story_id: int | None = None


def strip_outlet(title: str, source_name: str | None, source_domain: str | None) -> str:
    """Quita del final del título los segmentos que nombran al medio.

    Args:
        title: Título original.
        source_name: Nombre del medio.
        source_domain: Dominio del medio.

    Returns:
        El título sin el nombre del medio.

    Example:
        >>> strip_outlet("Desfile de Día de Muertos - Quadratín México", "Quadratín", None)
        'Desfile de Día de Muertos'
    """
    parts = _OUTLET_SEPARATOR.split(title)
    if len(parts) == 1:
        return title
    marks = {
        word
        for text in (source_name or "", (source_domain or "").split(".")[0])
        for word in normalize_name(text).split()
        if len(word) >= MIN_TOKEN_LENGTH
    }
    kept = [parts[0]]
    for segment in parts[1:]:
        words = set(normalize_name(segment).split())
        if words & marks or words & _OUTLET_WORDS:
            break
        kept.append(segment)
    return " - ".join(kept)


def story_tokens(clean_title_norm: str) -> frozenset[str]:
    """Palabras de un título que pueden distinguir un hecho.

    Args:
        clean_title_norm: Título sin el medio, ya normalizado.

    Returns:
        Las palabras de al menos ``MIN_TOKEN_LENGTH`` letras que no son
        palabras vacías.
    """
    return frozenset(
        word
        for word in _TOKEN.findall(clean_title_norm)
        if len(word) >= MIN_TOKEN_LENGTH and word not in _STOPWORDS
    )


def _state_of(code: str | None) -> str | None:
    if code is None or not code.isdigit():
        return None
    return code[:_STATE_DIGITS]


@dataclass(slots=True)
class _Prepared:
    note: StoryNote
    clean: str
    tokens: frozenset[str]

    @property
    def place(self) -> str | None:
        code = self.note.place_code
        return code if code is not None and code.isdigit() else None


@dataclass(slots=True)
class _Story:
    leader: _Prepared
    members: list[_Prepared] = field(default_factory=list)

    @property
    def last(self) -> datetime:
        return max(m.note.published_at for m in self.members)


def _prepare(note: StoryNote) -> _Prepared:
    clean = normalize_name(strip_outlet(note.title, note.source_name, note.source_domain))
    return _Prepared(note, clean, story_tokens(clean))


class _Rule:
    """La regla de «misma historia», con la frecuencia de palabras de la ventana."""

    def __init__(
        self, notes: Sequence[_Prepared], similarity: Similarity, token_similarity: Similarity
    ) -> None:
        self._counts = Counter(token for n in notes for token in n.tokens)
        self._similarity = similarity
        self._token_similarity = token_similarity

    def same(self, leader: _Prepared, note: _Prepared) -> bool:
        if self._similarity(leader.clean, note.clean) >= SAME_STORY_SIMILARITY:
            return True
        if self._token_similarity(leader.clean, note.clean) < SAME_STORY_TOKEN_SIMILARITY:
            return False
        rare = {t for t in leader.tokens & note.tokens if self._counts[t] <= RARE_TOKEN_MAX_TITLES}
        same_place = leader.place is not None and leader.place == note.place
        state = _state_of(leader.place)
        same_state = state is not None and state == _state_of(note.place)
        return same_place or len(rare) >= RARE_TOKENS_ALONE or (same_state and len(rare) >= 1)


def _fits(story: _Story, note: _Prepared) -> bool:
    at = note.note.published_at
    return (
        abs(at - story.last) <= STORY_GAP and abs(at - story.leader.note.published_at) <= STORY_SPAN
    )


def _existing_stories(existing: Sequence[_Prepared]) -> list[_Story]:
    """Historias que ya hay en la ventana (las notas solas también pueden crecer)."""
    by_story: dict[int, list[_Prepared]] = {}
    for p in existing:
        by_story.setdefault(p.note.story_id or p.note.article_id, []).append(p)
    stories = []
    for story_id, members in by_story.items():
        leader = next(
            (m for m in members if m.note.article_id == story_id),
            min(members, key=lambda m: (m.note.published_at, m.note.article_id)),
        )
        stories.append(_Story(leader, members))
    return stories


def assign_stories(
    existing: Sequence[StoryNote],
    new: Sequence[StoryNote],
    similarity: Similarity,
    token_similarity: Similarity,
) -> dict[int, int]:
    """Decide a qué historia va cada nota nueva.

    Las nuevas se revisan en orden cronológico. Cada una entra a la historia
    más antigua cuya primera nota se le parezca según la regla; si ninguna,
    abre la suya. Las notas de ``existing`` conservan su historia.

    Args:
        existing: Notas de la ventana que ya tienen historia o están solas.
        new: Notas por agrupar (sin historia todavía).
        similarity: Parecido de títulos normalizados, de 0 a 1 (``fuzz.ratio``).
        token_similarity: Parecido por palabras, de 0 a 1 (``token_set_ratio``).

    Returns:
        ``article_id → story_id`` de las notas cuya historia cambia: las
        nuevas que quedaron acompañadas y las que pasan a encabezar una
        historia. Las que siguen solas no aparecen.

    Example:
        >>> assign_stories([], [balacera_milenio, balacera_infobae], ratio, token_set)
        {101: 101, 102: 101}
    """
    prepared_existing = [_prepare(n) for n in existing]
    prepared_new = sorted(
        (_prepare(n) for n in new), key=lambda p: (p.note.published_at, p.note.article_id)
    )
    rule = _Rule([*prepared_existing, *prepared_new], similarity, token_similarity)
    stories = _existing_stories(prepared_existing)
    for note in prepared_new:
        candidates = sorted(
            (s for s in stories if _fits(s, note)),
            key=lambda s: (s.leader.note.published_at, s.leader.note.article_id),
        )
        story = next((s for s in candidates if rule.same(s.leader, note)), None)
        if story is None:
            stories.append(_Story(note, [note]))
        else:
            story.members.append(note)
    changes: dict[int, int] = {}
    for story in stories:
        if len(story.members) < MIN_STORY_SIZE:
            continue
        leader_id = story.leader.note.article_id
        for member in story.members:
            if member.note.story_id != leader_id:
                changes[member.note.article_id] = leader_id
    return changes
