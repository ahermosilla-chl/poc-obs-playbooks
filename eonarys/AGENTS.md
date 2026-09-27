# AGENTS.md — División de responsabilidades

Este repositorio se trabaja conjuntamente entre dos agentes de IA con roles
distintos y no intercambiables.

## ChatGPT — product & design

Responsable de:

- product planning
- arquitectura funcional
- UX/UI
- especificaciones y criterios de aceptación
- auditorías de producto
- revisión de seguridad a nivel de diseño
- revisión de Pull Requests desde la perspectiva de producto
- roadmap

## Claude Code — implementación

Responsable de:

- implementación de código
- tests
- migrations
- CI/CD
- corrección de issues
- refactoring autorizado
- Pull Requests

## Regla de oro

**Claude no redefine el producto unilateralmente mientras implementa.**

Cuando una implementación requiera una decisión de producto que no esté
documentada en `docs/`:

1. No inventar el comportamiento.
2. Documentar la pregunta explícitamente (en el PR, en un issue, o en
   `docs/decisions/` si es arquitectónica).
3. Solicitar la decisión antes de continuar con esa parte del trabajo.

Esto protege la coherencia del producto entre sesiones y entre agentes:
ninguna sesión individual de Claude Code tiene autoridad para cambiar la
dirección de producto documentada en `docs/PRODUCT.md`.

## Flujo esperado

```
ChatGPT define/especifica
        ↓
   Issue documentado
        ↓
Claude Code implementa
        ↓
   Pull Request
        ↓
ChatGPT (o revisor humano) revisa
        ↓
      main
```
