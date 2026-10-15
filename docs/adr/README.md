# Registros de decisiones de arquitectura (ADR)

Cada archivo documenta **una** decisión importante: el contexto, lo que se decidió, las alternativas y sus consecuencias.
Sirven para que alguien nuevo entienda *por qué* el proyecto es como es, no solo *cómo*.

## Reglas

- Nombre: `NNNN-titulo-en-minusculas.md`, numeración consecutiva.
- Secciones obligatorias: Contexto, Decisión, Alternativas consideradas y Consecuencias.
- Un ADR aceptado no se reescribe: si la decisión cambia, se crea uno nuevo que lo reemplaza y se marca el anterior como "reemplazado por ADR-XXXX".
- Cualquier cambio a la tabla de stack de la especificación (sección 5.4) requiere un ADR.

## Índice

| ADR | Título | Estado |
|---|---|---|
| [0006](0006-entorno-desarrollo-sin-docker.md) | Entorno de desarrollo sin Docker: servicios nativos en WSL | Aceptado |
