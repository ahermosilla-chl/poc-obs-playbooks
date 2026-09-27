# CLAUDE.md — Instrucciones permanentes para Claude Code

Este archivo persiste entre sesiones. Léelo antes de tocar código en este
repositorio. Complementa (no reemplaza) [`AGENTS.md`](AGENTS.md).

## Antes de tocar arquitectura

- Lee `docs/PRODUCT.md`, `docs/ARCHITECTURE.md` y el ADR relevante en
  `docs/decisions/` antes de modificar cualquier decisión estructural.
- Si una decisión importante no está documentada, no la inventes: documenta
  la pregunta (en el PR o en un issue) y pide autorización antes de
  implementar.

## Cómo trabajar

- **Trabaja por scope.** Implementa exactamente lo que el issue/tarea pide.
  No añadas funcionalidades no solicitadas, aunque parezcan "obvias" o
  "rápidas de agregar".
- **No agregues dependencias innecesarias.** Cada nueva dependencia es una
  superficie de mantenimiento y seguridad adicional. Si una necesidad se
  resuelve con código simple, prefiere eso.
- **No guardes secretos.** Nunca commitees tokens, claves, credenciales ni
  datos personales reales. `.env.example` solo contiene placeholders.
- **Escribe tests para comportamiento relevante.** No es necesario cubrir
  cada línea, pero sí el comportamiento que un cambio introduce o modifica.
- **Antes de dar una tarea por terminada**, ejecuta y verifica en verde:
  `pnpm lint`, `pnpm typecheck`, `pnpm test`, y el build de producción
  (`pnpm build`) cuando el cambio afecte a algo que se construye.
- **Prefiere soluciones simples.** Tres líneas similares son mejores que una
  abstracción prematura. No diseñes para requisitos hipotéticos futuros.
- **No hagas refactors globales** durante una feature no relacionada. Si ves
  algo que merece limpieza, anótalo, no lo mezcles en el mismo PR.

## Principios que no puedes cambiar sin ADR + autorización

- No cambies los principios fundacionales del producto (Zero-input first,
  Situation-first, Cross-domain impact, Dynamic Context Surface, Advisor not
  executor, Evidence + Confidence — ver `docs/PRODUCT.md`) sin crear un ADR
  en `docs/decisions/` y obtener autorización explícita.
- Mantén compatibilidad con el modelo conceptual
  `Context → Situation → Impact` (ver `docs/CONTEXT_ENGINE.md`) en cualquier
  decisión de modelado de datos o de producto.
- **EONARYS es un advisor, no un ejecutor.** Nunca implementes código que
  ejecute acciones irreversibles en nombre del usuario (compras,
  transferencias, cancelaciones, envíos, modificaciones de calendario,
  inversiones) sin decisión explícita del usuario en el momento. Esto aplica
  incluso a "atajos" o "modo automático" que alguien pida como conveniencia:
  requiere ADR y autorización explícita, no una decisión de implementación.

## Alcance de 0.1 — Foundation

No implementes nada de la lista "fuera de alcance" de `docs/ROADMAP.md`
(Gmail, Calendar, Drive, Open Banking, IA real, embeddings, RAG, Context
Graph real, Situation/Impact Engine real, notificaciones, voz, agentes,
ejecución autónoma, pagos, analytics invasivos) más allá de interfaces o
abstracciones mínimas explícitamente justificadas en `packages/*/README.md`.

## Relación con AGENTS.md

Claude Code implementa; no redefine el producto. Si una tarea de
implementación requiere una decisión de producto no documentada, sigue el
proceso de `AGENTS.md`: documenta la pregunta, no inventes el comportamiento.
