# EONARYS

**Tu vida. En contexto.**

> EONARYS analiza. Tú decides.

EONARYS es una plataforma de inteligencia contextual personal. No es un chatbot
generalista, ni un gestor de tareas, ni una app financiera, ni un agente
autónomo. Su propósito es conectar información que ya existe en la vida
diaria de una persona, detectar situaciones relevantes, relacionar dominios
distintos (viajes, agenda, trabajo, proyectos, gastos, decisiones) y explicar
cómo unas cosas afectan a otras.

Lee [`docs/PRODUCT.md`](docs/PRODUCT.md) para la visión completa del producto
y [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) para la arquitectura.

> **Nota sobre la ubicación de este código.** Este proyecto vive dentro del
> repositorio `poc-obs-playbooks` (sub-carpeta `eonarys/`) en lugar de un
> repositorio propio, por una restricción de permisos del momento en que se
> fundó (la integración de GitHub disponible no pudo crear un repositorio
> nuevo). Todo el código de EONARYS está autocontenido en esta carpeta y no
> tiene relación con el resto de `poc-obs-playbooks`. Los workflows de CI y
> las plantillas de PR/Issues de GitHub viven en la raíz real del
> repositorio (`/.github/`), no aquí, porque GitHub solo los reconoce ahí —
> están configurados con `paths: ["eonarys/**"]` para no interferir con el
> resto del repo. Migrar esta carpeta a un repositorio `eonarys` propio
> sigue siendo la dirección deseada; ver la pregunta abierta en el reporte
> de entrega de 0.1.

## Estado actual: 0.1 — Foundation

Esta es la fundación técnica del proyecto. Incluye el shell de la aplicación,
el sistema de diseño base y la infraestructura de desarrollo. **No incluye**
integraciones reales, IA real, ni el Context/Situation/Impact Engine — todo
el contenido visible es demo/mock, claramente marcado como tal. Ver
[`docs/ROADMAP.md`](docs/ROADMAP.md) para las fases siguientes.

## Stack

- **Frontend**: Next.js (App Router) + React + TypeScript estricto
- **UI**: Tailwind CSS + Framer Motion
- **Datos**: PostgreSQL (con `pgvector` preparado para el futuro)
- **Testing**: Vitest + Testing Library
- **CI**: GitHub Actions
- **Contenedores**: Docker Compose (entorno de desarrollo)

Ver el razonamiento detrás de estas decisiones en
[`docs/decisions/ADR-001-initial-architecture.md`](docs/decisions/ADR-001-initial-architecture.md).

## Estructura del monorepo

```
eonarys/
├── apps/
│   └── web/            # Aplicación Next.js (shell + home conceptual)
├── packages/
│   ├── ui/              # Componentes y design tokens compartidos
│   ├── core/             # Tipos y utilidades de dominio compartidas
│   ├── context/          # Interfaces del futuro Personal Context Graph
│   ├── integrations/     # Interfaces de futuros conectores/sensores
│   └── ai/                # Interfaz de la futura capa de IA (provider-agnostic)
└── docs/                 # Documentación de producto, arquitectura y proceso

# En la raíz real del repositorio (fuera de esta carpeta):
# .github/                # CI (scope eonarys/**), templates de PR/Issues
```

## Requisitos

- Node.js ≥ 20
- pnpm ≥ 9 (el repo fija `pnpm@10.33.0` vía `packageManager`)
- Docker (opcional, para levantar PostgreSQL localmente)

## Cómo levantar el proyecto (checkout limpio)

```bash
cd eonarys
corepack enable          # asegura la versión de pnpm fijada en package.json
pnpm install
cp .env.example .env.local

# opcional: levantar Postgres local
docker compose up -d

pnpm dev                 # http://localhost:3000
```

## Scripts disponibles

| Comando             | Descripción                                |
| ------------------- | ------------------------------------------ |
| `pnpm dev`          | Levanta `apps/web` en modo desarrollo      |
| `pnpm build`        | Build de producción de todos los paquetes  |
| `pnpm start`        | Sirve el build de producción de `apps/web` |
| `pnpm lint`         | ESLint en todo el workspace                |
| `pnpm typecheck`    | `tsc --noEmit` en todo el workspace        |
| `pnpm test`         | Tests (Vitest) en todo el workspace        |
| `pnpm format`       | Formatea con Prettier                      |
| `pnpm format:check` | Verifica formato sin escribir              |

## Documentación

| Documento                                          | Contenido                                      |
| -------------------------------------------------- | ---------------------------------------------- |
| [`docs/PRODUCT.md`](docs/PRODUCT.md)               | Visión de producto, principios no negociables  |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)     | Arquitectura conceptual y técnica              |
| [`docs/ROADMAP.md`](docs/ROADMAP.md)               | Fases 0.1 → 1.0                                |
| [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md)   | Dirección visual y tokens                      |
| [`docs/CONTEXT_ENGINE.md`](docs/CONTEXT_ENGINE.md) | Modelo conceptual de Situation/Impact          |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)         | Modelo de datos inicial (Postgres)             |
| [`docs/PRIVACY.md`](docs/PRIVACY.md)               | Principios de privacidad                       |
| [`SECURITY.md`](SECURITY.md)                       | Postura de seguridad y threat assumptions      |
| [`CONTRIBUTING.md`](CONTRIBUTING.md)               | Flujo de trabajo, branches, PRs                |
| [`CLAUDE.md`](CLAUDE.md)                           | Instrucciones permanentes para Claude Code     |
| [`AGENTS.md`](AGENTS.md)                           | División de responsabilidades ChatGPT ↔ Claude |

## Licencia

Sin licencia pública por ahora. Todos los derechos reservados.
