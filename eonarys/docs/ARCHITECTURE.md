# ARCHITECTURE.md

## Arquitectura conceptual

Esta es la dirección de producto a largo plazo. **No** está implementada en
0.1 más allá del shell de UI y placeholders documentados; se documenta aquí
para que la arquitectura técnica de cada fase futura tenga un norte claro.

```
Connected Sources
       ↓
Normalization Layer
       ↓
Personal Context Graph
       ↓
Situation Engine
       ↓
Impact Engine
       ↓
Context Surface
       ↓
EONARYS Advisor
```

- **Connected Sources** — Gmail, Calendar, Drive, proveedores financieros,
  viajes, GitHub, Microsoft, MCP, etc. Se tratan como **sensores de
  contexto**, no como módulos principales del producto. Ninguna integración
  es "el" producto; todas alimentan al mismo grafo.
- **Normalization Layer** — convierte datos heterogéneos de cada fuente en
  entidades y eventos normalizados.
- **Personal Context Graph** — el grafo de entidades, eventos y relaciones
  de la vida del usuario. Ver `docs/DATA_MODEL.md` para cómo se modela
  inicialmente sobre PostgreSQL.
- **Situation Engine** — agrupa evidencia normalizada en _Situations_
  (ver `docs/PRODUCT.md`, principio Situation-first).
- **Impact Engine** — encuentra relaciones cross-domain entre situaciones
  (ver `docs/CONTEXT_ENGINE.md`).
- **Context Surface** — la superficie dinámica (home) que decide qué
  mostrar y cuándo (ver `docs/DESIGN_SYSTEM.md`).
- **EONARYS Advisor** — la capa conversacional/explicativa sobre todo lo
  anterior.

Ninguna de las capas desde "Personal Context Graph" hacia abajo tiene
implementación real en 0.1. Ver `docs/ROADMAP.md` para el orden de
construcción.

## Arquitectura técnica inicial (0.1 — Foundation)

Elegida deliberadamente simple, sin sobreingeniería. Razonamiento completo
en [`docs/decisions/ADR-001-initial-architecture.md`](decisions/ADR-001-initial-architecture.md).

```
Frontend      Next.js (App Router) + React + TypeScript estricto
UI            Tailwind CSS + Framer Motion
Data          PostgreSQL (pgvector preparado, no usado aún)
AI            (futura capa independiente de proveedor — no implementada)
Integrations  (futura capa de adapters/connectors — no implementada)
Testing       Vitest + Testing Library
CI            GitHub Actions
Containers    Docker Compose (entorno de desarrollo)
```

### Restricciones explícitas para 0.1

- **Sin microservicios.** Una sola aplicación Next.js.
- **Sin Kubernetes.**
- **Sin Kafka** ni ningún bus de eventos.
- **Sin graph database.** El Context Graph, cuando exista (0.3+), se modela
  inicialmente sobre PostgreSQL con relaciones + JSONB, y `pgvector` para
  búsqueda semántica cuando aplique. Una graph database dedicada (p. ej.
  Neo4j) es una decisión que requeriría su propio ADR si el modelo
  relacional dejara de ser suficiente.

### Estructura de monorepo

```
apps/
  web/              # Next.js — la única app en 0.1
packages/
  ui/               # componentes + design tokens compartidos
  core/             # tipos y utilidades de dominio compartidas
  context/          # interfaces del futuro Personal Context Graph (0.3+)
  integrations/     # interfaces de futuros adapters/connectors (0.2+)
  ai/               # interfaz de la futura capa de IA provider-agnostic (0.7+)
```

Los paquetes `context`, `integrations` y `ai` existen en 0.1 solo como
estructura y, cuando está justificado, un tipo/interfaz mínima — nunca como
implementación funcional. Ver el `README.md` de cada paquete para el
alcance exacto.

### Gestión de paquetes

pnpm workspaces. Se evalúa deliberadamente **no** usar un orquestador de
monorepo (Turborepo, Nx) en 0.1: con un solo app real y paquetes placeholder,
`pnpm -r` es suficiente y evita una dependencia y una capa de configuración
que no aporta valor todavía. Si el número de paquetes/apps crece lo
suficiente como para que el caching de tareas importe, esa es una decisión
para un ADR futuro, no una que se tome silenciosamente.

## Cambios de arquitectura

Cualquier cambio a esta arquitectura que no sea puramente aditivo (por
ejemplo: introducir un orquestador de monorepo, cambiar de base de datos,
introducir microservicios) requiere un nuevo ADR en `docs/decisions/`.
