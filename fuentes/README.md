# fuentes/

Listas curadas de fuentes de noticias que usa la ingesta periódica (ADR-0013).

| Archivo | Qué es |
|---|---|
| `medios_rss.csv` | RSS propios de medios mexicanos. Columnas: `slug` (nombre corto, va en `rss:<slug>`), `medio`, `url`, `activo` (`si`/`no`), `terminos` y `nota`. |

## Reglas

- **Un medio solo se activa (`activo = si`) después de que Benji revisa sus términos de uso.** Anota en `terminos` la fecha y el link de lo que se revisó.
- **De cada nota se guardan solo título, fragmento corto, fecha y link** (CLAUDE.md §8), aunque el feed traiga el texto completo (El Universal e Infobae lo traen).
- **Para agregar un medio:** busca la dirección de su RSS, agrégalo con `activo = no` y corre `wsl make ingesta` para ver 5 ejemplos antes de activarlo.
- **Google News RSS no va aquí:** sus términos solo permiten uso personal (ADR-0011).
