# ADR-001 — Arquitectura técnica inicial (0.1 Foundation)

- **Estado**: Aceptado
- **Fecha**: 2026-09-27

## Contexto

EONARYS necesita una fundación técnica para 0.1 que sea moderna, productiva
para un equipo pequeño, y que no comprometa la dirección de producto
documentada en `docs/PRODUCT.md` (Situation-first, Cross-domain impact,
Dynamic Context Surface). Al mismo tiempo, el mandato explícito para 0.1 es
evitar sobreingeniería: no hay usuarios reales, no hay fuentes conectadas, y
construir para una escala hipotética antes de tener datos reales es
contraproducente.

## Decisión

### Frontend: Next.js (App Router) + React + TypeScript estricto

Next.js da SSR/SSG, App Router, y un ecosistema maduro sin requerir decidir
entre múltiples librerías de routing/data-fetching por separado. TypeScript
estricto (`strict: true`) desde el día uno evita deuda de tipado que sería
costosa de introducir después en un producto centrado en modelar relaciones
entre entidades.

### UI: Tailwind CSS + Framer Motion

Tailwind permite implementar el sistema de diseño (`docs/DESIGN_SYSTEM.md`)
como tokens consistentes sin mantener una capa CSS-in-JS adicional. Framer
Motion es la opción estándar para las animaciones suaves que pide la
dirección visual, sin construir un sistema de animación propio.

### Datos: PostgreSQL (con `pgvector` preparado, no usado en 0.1)

Ver el razonamiento detallado en `docs/DATA_MODEL.md`. Resumen: el Context
Graph (0.3+) se modela sobre relacional + JSONB; `pgvector` se añade cuando
exista contenido embebible real. Se descarta explícitamente una graph
database dedicada para V1 — no hay evidencia todavía de que las consultas
de travesía de grafo sean el cuello de botella dominante, y añadir ese
motor ahora sería infraestructura especulativa.

### IA: capa independiente de proveedor (no implementada en 0.1)

`packages/ai` existe solo como paquete vacío/interfaz mínima. Ninguna
llamada real a un proveedor de IA se implementa en 0.1 (ver
`docs/ROADMAP.md`, fuera de alcance). Cuando se implemente (0.7+), la capa
debe ser agnóstica de proveedor para no acoplar el producto a un vendor
específico — eso se decidirá en su propio ADR con el contexto de esa fase.

### Integraciones: capa de adapters/connectors (no implementada en 0.1)

`packages/integrations` existe solo como estructura. Las fuentes conectadas
se tratan como sensores de contexto (`docs/ARCHITECTURE.md`), lo que implica
que cada conector futuro debe implementar una interfaz común en lugar de
integrarse ad-hoc en el producto principal.

### Testing: Vitest + Testing Library

Vitest se integra nativamente con el ecosistema Vite/Next.js moderno, es
más rápido que Jest para este tamaño de proyecto, y comparte configuración
de TypeScript con el resto del monorepo sin capas de transpilación
adicionales.

### CI: GitHub Actions

Ya es la plataforma del repositorio; no se introduce un sistema de CI
externo.

### Contenedores: Docker Compose (solo entorno de desarrollo)

Docker Compose levanta Postgres localmente para desarrollo reproducible.
**No** se introduce Kubernetes — no hay necesidad de orquestación en 0.1 (ni
siquiera un ambiente de producción desplegado todavía).

### Monorepo: pnpm workspaces, sin orquestador de tareas

Se evalúa Turborepo/Nx y se descartan para 0.1: con un solo app real, el
caching de tareas de un orquestador no aporta valor proporcional a la
dependencia y configuración que introduce. Revisar si el número de
apps/packages con build real (no placeholder) crece.

## Alternativas consideradas y descartadas

| Alternativa                   | Por qué se descarta para 0.1                                                                                                                                            |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Microservicios                | No hay múltiples equipos ni escalas independientes que lo justifiquen; una sola app Next.js es suficiente y más simple de operar.                                       |
| Kubernetes                    | No hay carga de producción real; Docker Compose cubre desarrollo.                                                                                                       |
| Kafka / bus de eventos        | No hay múltiples productores/consumidores de eventos todavía; se reevaluará cuando exista más de una fuente conectada emitiendo eventos de forma asíncrona real.        |
| Graph database (p. ej. Neo4j) | El modelo relacional + JSONB + pgvector es suficiente para V1 del Context Graph; introducir un segundo motor de datos sin evidencia de necesidad sería sobreingeniería. |
| Turborepo/Nx                  | Aporta valor cuando hay múltiples paquetes con build/test real y se necesita cachear tareas entre ellos; en 0.1 la mayoría de `packages/*` son placeholders.            |

## Consecuencias

- La fundación es deliberadamente pequeña en superficie técnica: fácil de
  auditar, fácil de razonar sobre ella.
- Cualquier decisión de esta lista que se quiera revertir o ampliar
  (introducir un orquestador de monorepo, cambiar de base de datos,
  introducir microservicios) requiere su propio ADR, no un cambio silencioso
  durante una feature.
- Las fases 0.2+ que requieran infraestructura no cubierta aquí (colas de
  trabajo para sincronizar fuentes, por ejemplo) deben documentar esa
  necesidad con un ADR propio cuando llegue el momento, con datos reales del
  problema que resuelven.
