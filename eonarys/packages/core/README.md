# @eonarys/core

Tipos y utilidades de dominio compartidas entre `apps/web` y otros paquetes.

## Alcance en 0.1

Este paquete contiene únicamente lo que la home conceptual de 0.1 necesita:

- `ContextCard`: el tipo que representa una tarjeta de contexto en la
  Dynamic Context Surface (ver `docs/DESIGN_SYSTEM.md`). Es intencionalmente
  genérico (no "FinanceCard", "TravelCard", etc.) para no reintroducir la
  grilla fija de dominios que `docs/PRODUCT.md` prohíbe explícitamente.
- `sortByRelevance`: la función que ordena tarjetas de contexto por
  urgencia y proximidad temporal — la pieza mínima de lógica que hace que
  la home sea "preparada para dinámica" y no una lista hardcodeada.

No contiene tipos del Personal Context Graph, Situation o Impact reales —
esos viven conceptualmente en `packages/context` y no se implementan hasta
0.3+ (ver `docs/ROADMAP.md`).
