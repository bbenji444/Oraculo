"""Regla de las subdivisiones: la palabra del tema va en el título o el resumen.

En «FGR · Homicidio» la nota debe traer las dos cosas (ADR-0038). El
03/11/2026 se midió en el índice local que 79 de 109 notas de una semana
cumplían solo porque la palabra de homicidio aparecía una vez, perdida en
el cuerpo del artículo («Brota más corrupción en el INE» dice «asesinato»
en 11 mil caracteres). Benji eligió que cuente solo si está en el **título
o en el resumen** que trae la fuente.

Los buscadores (Google News, SearchApi) buscan en todo el artículo y no hay
forma confirmada de pedirles otra cosa, así que la regla se aplica al
recibir las notas: lo que no cumple no se guarda ni se paga a la IA.

Quién lo usa: ``RunSearch`` antes de deduplicar. El índice local aplica la
misma regla en su SQL (``text_norm``, el mismo texto normalizado).

No hace: no toca las palabras clave del concepto (la FGR se sigue buscando
también en el cuerpo) ni las búsquedas sin subdivisión.
"""

import re
from collections.abc import Sequence

from app.domain.names import normalize_name
from app.domain.news_index import index_text_norm


class TopicMatcher:
    """Reconoce si el título o el resumen de una nota traen una palabra del tema.

    Compara palabras completas y normalizadas, igual que el índice local:
    «Homicidio» encuentra «HOMICIDIO» pero no «HOMICIDIOS» (por eso las
    listas traen el plural aparte).
    """

    def __init__(self, terms: Sequence[str]) -> None:
        """Arma el reconocedor.

        Args:
            terms: Palabras del tema (``PlannedQuery.topic_terms``); vacío =
                sin subdivisión, todo pasa.
        """
        clean = sorted({normalize_name(t) for t in terms if t.strip()}, key=len, reverse=True)
        alternatives = "|".join(re.escape(term) for term in clean)
        self._pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)") if clean else None

    def found_in(self, title: str, snippet: str | None) -> bool:
        """Dice si la nota cumple la regla.

        Args:
            title: Título de la nota.
            snippet: Resumen o fragmento que trae la fuente, si hay.

        Returns:
            ``True`` si no hay subdivisión o si el título o el resumen traen
            una de sus palabras.

        Example:
            >>> TopicMatcher(["homicidio"]).found_in("FGR atrae el homicidio de un edil", None)
            True
            >>> TopicMatcher(["homicidio"]).found_in("Brota más corrupción en el INE", None)
            False
        """
        if self._pattern is None:
            return True
        return self._pattern.search(index_text_norm(title, snippet)) is not None
