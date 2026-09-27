# @eonarys/ai

Reservado para la futura capa de IA independiente de proveedor
(ver `docs/ARCHITECTURE.md` y `ADR-001`), usada por el futuro EONARYS
Advisor y por el Situation/Impact Engine para generar explicaciones e
inferencias.

## Por qué está vacío en 0.1

`docs/ROADMAP.md` excluye explícitamente de 0.1 cualquier llamada real a un
proveedor de IA (OpenAI, Anthropic u otro), embeddings y RAG. Este paquete
existe solo para reservar el límite de la capa en la estructura del
monorepo — no contiene ninguna interfaz todavía porque no hay ningún
consumidor real que la necesite.

Se empieza a implementar en **0.7 — Advisor** (ver `docs/ROADMAP.md`), y la
decisión de qué proveedor(es) soportar y cómo abstraerlos debe quedar en su
propio ADR en ese momento.
