# Contributing

## Flujo de branches

```
main
  ↓
feature/*
  ↓
Pull Request
  ↓
review
  ↓
main
```

- `main` contiene siempre una versión funcional y validada.
- El trabajo nuevo se hace en `feature/<descripción-corta>` (o
  `fix/<descripción-corta>` para bugfixes).
- No se hace force-push sobre `main`. No se reescribe historial existente.
- Los PRs deben pasar CI (lint, typecheck, test, build) antes de mergear.

## Antes de abrir un PR

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Todo debe pasar en verde localmente antes de pushear.

## Commits

Mensajes claros y descriptivos, en imperativo, explicando el _por qué_ del
cambio cuando no sea obvio por el _qué_. Evita commits tipo "fix", "wip",
"changes".

## Pull Requests

Usa la plantilla de `.github/pull_request_template.md`. Un PR debe incluir
como mínimo: resumen, scope, cambios, tests, consideraciones de seguridad,
capturas si hay cambios de UI, qué queda fuera de alcance y limitaciones
conocidas.

## Decisiones de producto y arquitectura

Si tu cambio implica una decisión no documentada en `docs/`, no la decidas
tú solo/a como parte del PR de implementación: documenta la pregunta (ver
`AGENTS.md`) y, si es arquitectónica, propone un ADR en
`docs/decisions/` siguiendo el formato de `ADR-001-initial-architecture.md`.
