"""Qué notas sobran en el índice local y cuál se queda (F12.1b, ADR-0025).

Desde F12.1b la ingesta ya no guarda duplicados (URL canónica, mismo medio
con el mismo texto a ±3 días, títulos sin letras). Este módulo decide qué
sobra de lo que entró **antes**, con las mismas reglas:

1. **Sin letras:** el título no llega a ``MIN_TITLE_LETTERS`` («🎦»).
2. **Misma URL:** la misma URL canónica con otra forma (``:443``, ``www.``).
3. **Mismo medio:** el mismo dominio, el mismo ``text_norm`` **y el mismo
   cuerpo** (o los dos sin cuerpo), con fechas encadenadas a
   ±``SAME_OUTLET_WINDOW``. Exigir el mismo cuerpo evita juntar notas
   distintas a las que GDELT les puso el título de la portada («Inicio |
   Periódico CiudadCCS» en dos artículos diferentes).

En cada grupo se queda la nota que conserva frases del cuerpo (sirven para
buscar) y, si empatan, la más antigua. Además se recalcula la huella
(``url_hash``) de las que se quedan para que coincida con la de la ingesta.

La misma nota en **otro** medio no se toca: es otra fuente.

No hace: no consulta ni borra nada (eso es ``CleanIndexDuplicates``).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.domain.dedupe import canonical_url, url_hash
from app.domain.news_index import SAME_OUTLET_WINDOW, has_title_letters

CleanupReason = Literal["sin_letras", "misma_url", "mismo_medio"]


@dataclass(frozen=True, slots=True)
class IndexKey:
    """Lo que hace falta de una nota del índice para decidir si sobra.

    Attributes:
        note_id: Id en ``news_index``.
        url: URL guardada.
        url_hash: Huella guardada (de la URL cruda, en notas viejas).
        title: Título.
        source_domain: Dominio del medio, si se conoce.
        text_norm: Título y fragmento normalizados.
        published_at: Fecha (UTC).
        has_body: Si conserva frases del cuerpo.
        body_fingerprint: Huella de las frases del cuerpo (``None`` sin cuerpo).
    """

    note_id: int
    url: str
    url_hash: str
    title: str
    source_domain: str | None
    text_norm: str
    published_at: datetime
    has_body: bool
    body_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class Removal:
    """Una nota que sobra.

    Attributes:
        note: La nota.
        reason: Por qué sobra.
        kept: La nota que se queda en su lugar (``None`` si es «sin letras»).
    """

    note: IndexKey
    reason: CleanupReason
    kept: IndexKey | None


@dataclass(slots=True)
class CleanupPlan:
    """Lo que hay que hacer con el índice.

    Attributes:
        removals: Notas que sobran, en orden de id.
        rehash: ``(id, huella nueva)`` de las que se quedan con huella vieja.
    """

    removals: list[Removal] = field(default_factory=list)
    rehash: list[tuple[int, str]] = field(default_factory=list)


def _keeper(group: Sequence[IndexKey]) -> IndexKey:
    """La que se queda: con cuerpo primero, luego la más antigua."""
    return min(group, key=lambda k: (not k.has_body, k.note_id))


def _drop(plan: CleanupPlan, group: Sequence[IndexKey], reason: CleanupReason) -> IndexKey:
    kept = _keeper(group)
    plan.removals.extend(Removal(k, reason, kept) for k in group if k is not kept)
    return kept


def _outlet_chains(group: Sequence[IndexKey]) -> list[list[IndexKey]]:
    """Parte un grupo del mismo medio y texto en tramos de fechas encadenadas."""
    chains: list[list[IndexKey]] = []
    for key in sorted(group, key=lambda k: (k.published_at, k.note_id)):
        if chains and key.published_at - chains[-1][-1].published_at <= SAME_OUTLET_WINDOW:
            chains[-1].append(key)
        else:
            chains.append([key])
    return chains


def plan_index_cleanup(keys: Sequence[IndexKey]) -> CleanupPlan:
    """Decide qué notas del índice sobran y qué huellas recalcular.

    Args:
        keys: Todas las notas del índice.

    Returns:
        Las que sobran (con la que se queda) y las huellas a recalcular.

    Example:
        >>> plan = plan_index_cleanup([nota_443, misma_nota_sin_puerto])
        >>> [(r.reason, r.kept.note_id) for r in plan.removals]
        [('misma_url', 1)]
    """
    plan = CleanupPlan()
    with_letters: list[IndexKey] = []
    for key in keys:
        if has_title_letters(key.title):
            with_letters.append(key)
        else:
            plan.removals.append(Removal(key, "sin_letras", None))

    by_url: dict[str, list[IndexKey]] = defaultdict(list)
    for key in with_letters:
        by_url[url_hash(canonical_url(key.url))].append(key)
    unique_url = [_drop(plan, group, "misma_url") for group in by_url.values()]

    by_outlet: dict[tuple[str, str, str | None], list[IndexKey]] = defaultdict(list)
    survivors: list[IndexKey] = []
    for key in unique_url:
        if key.source_domain is None:
            survivors.append(key)
        else:
            by_outlet[(key.source_domain, key.text_norm, key.body_fingerprint)].append(key)
    for group in by_outlet.values():
        survivors.extend(_drop(plan, chain, "mismo_medio") for chain in _outlet_chains(group))

    for key in sorted(survivors, key=lambda k: k.note_id):
        new_hash = url_hash(canonical_url(key.url))
        if new_hash != key.url_hash:
            plan.rehash.append((key.note_id, new_hash))
    plan.removals.sort(key=lambda r: r.note.note_id)
    return plan
