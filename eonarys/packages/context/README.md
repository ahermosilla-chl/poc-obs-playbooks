# @eonarys/context

Reservado para el Personal Context Graph (ver `docs/ARCHITECTURE.md` y
`docs/CONTEXT_ENGINE.md`): normalización de fuentes conectadas en
entidades, y los futuros Situation Engine / Impact Engine.

## Por qué está vacío en 0.1

`docs/ROADMAP.md` marca explícitamente el Context Graph real, el Situation
Engine y el Impact Engine como fuera de alcance de 0.1. Añadir interfaces o
tipos aquí ahora, sin ningún consumidor real, sería código especulativo
("por si acaso") — exactamente lo que `CLAUDE.md` pide evitar. Este paquete
existe únicamente para reservar el límite de la futura capa en la
estructura del monorepo (ver `docs/ARCHITECTURE.md`).

Se empieza a implementar en **0.3 — Personal Context** (ver
`docs/ROADMAP.md`), con su propio diseño y, si corresponde, su propio ADR.
