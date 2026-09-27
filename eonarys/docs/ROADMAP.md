# ROADMAP.md

Este roadmap es **documentación de dirección**, no un compromiso de
implementación inmediata. Cada fase se planifica y audita antes de
comenzarse (ver `CLAUDE.md`: no adelantar fases).

| Fase | Nombre                  | Contenido                                                       |
| ---- | ----------------------- | --------------------------------------------------------------- |
| 0.1  | Foundation              | Infraestructura y shell (este repositorio, estado actual)       |
| 0.2  | Google Context          | Gmail + Google Calendar como primeras fuentes conectadas        |
| 0.3  | Personal Context        | Normalización y modelo contextual real (Personal Context Graph) |
| 0.4  | Situations              | Situation Engine                                                |
| 0.5  | Impact                  | Cross-domain Impact Engine                                      |
| 0.6  | Dynamic Context Surface | Home verdaderamente dinámica                                    |
| 0.7  | Advisor                 | Conversación contextual                                         |
| 0.8  | Trust                   | Evidence, Confidence y Life Inbox                               |
| 0.9  | Hardening               | Seguridad, privacidad, rendimiento y observabilidad             |
| 1.0  | Private Beta            | Usuarios reales controlados                                     |

## Alcance de 0.1 — Foundation

- Monorepo funcional (pnpm workspaces)
- Aplicación web arrancable (Next.js + TypeScript estricto)
- Tailwind CSS configurado
- Estructura inicial de componentes + design tokens
- Shell de EONARYS y página inicial conceptual (contenido demo/mock,
  marcado explícitamente como tal)
- Responsive desktop/mobile
- Testing, lint, formatting, typecheck configurados y en verde
- CI en GitHub Actions
- `.env.example`
- Docker/dev environment razonable (Postgres)
- Arquitectura de paquetes preparada para el futuro Context Engine
  (sin implementación real)
- Accesibilidad básica
- Manejo de errores base

## Explícitamente fuera de alcance en 0.1

No se implementa en esta fase — ni siquiera parcialmente — nada de lo
siguiente. Solo se permiten interfaces/abstracciones mínimas cuando están
explícitamente justificadas para dejar el terreno preparado, nunca "por si
acaso":

- Gmail
- Google Calendar
- Google Drive
- Open Banking
- Plaid
- Fintoc
- Belvo
- IA real
- Llamadas a OpenAI
- Llamadas a Anthropic
- Embeddings
- RAG
- Memoria de usuario
- Context Graph real
- Situation Engine real
- Impact Engine real
- Notificaciones
- Voz
- Agentes
- Ejecución autónoma
- Pagos
- Suscripciones
- Analytics invasivos

## Después de 0.1

**No se comienza 0.2 sin planificación y auditoría explícita previa.** Este
roadmap documenta la dirección general de cada fase futura, pero cada una
debe especificarse (ChatGPT, ver `AGENTS.md`) antes de que Claude Code
comience a implementarla.

- **0.2 — Google Context**: Gmail + Google Calendar como primeras fuentes,
  vía la capa de `packages/integrations`.
- **0.3 — Personal Context**: normalización real hacia el Personal Context
  Graph sobre PostgreSQL (`packages/context`).
- **0.4 — Situations**: primer Situation Engine real.
- **0.5 — Impact**: Impact Engine cross-domain.
- **0.6 — Dynamic Context Surface**: la home deja de ser conceptual/mock y
  pasa a ser realmente dinámica.
- **0.7 — Advisor**: capa conversacional sobre el contexto (`packages/ai`).
- **0.8 — Trust**: Evidence + Confidence en la UI, Life Inbox.
- **0.9 — Hardening**: seguridad, privacidad, performance, observabilidad.
- **1.0 — Private Beta**: usuarios reales controlados.
