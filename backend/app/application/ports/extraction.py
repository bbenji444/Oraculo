"""Puerto de extracción del texto de una nota (§9, paso 4).

La implementación (``app/adapters/extraction/trafilatura_extractor.py``)
baja la página del medio y separa el cuerpo de menús y anuncios.

No hace: no decide si el texto alcanza (eso es ``app.domain.extraction``).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Extraction:
    """Lo que salió de intentar leer una nota.

    Attributes:
        text: Cuerpo de la nota, o ``None`` si no se pudo.
        failure: Por qué no se pudo, en español.
    """

    text: str | None
    failure: str | None = None


class TextExtractorPort(Protocol):
    """Lee el cuerpo de una nota a partir de su URL."""

    async def extract(self, url: str) -> Extraction:
        """Baja la página y extrae el cuerpo.

        Args:
            url: Link de la nota.

        Returns:
            El cuerpo o el motivo de la falla. Nunca lanza por una página
            que no se pudo leer: una nota que falla no detiene a las demás.
        """
        ...
