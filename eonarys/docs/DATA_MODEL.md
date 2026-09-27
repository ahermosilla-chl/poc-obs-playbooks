# DATA_MODEL.md

## Alcance en 0.1

0.1 no persiste datos de usuario reales — la home consume datos mock desde
código (`apps/web`), no desde una base de datos. Este documento describe el
modelo de datos **preparatorio** para 0.3+ (Personal Context Graph), y el
entorno de desarrollo de Postgres que 0.1 sí deja levantado (`docker
compose`) para que las fases siguientes no empiecen desde cero.

## Por qué PostgreSQL (y no una graph database) para V1

Ver [`ADR-001`](decisions/ADR-001-initial-architecture.md) para el
razonamiento completo. Resumen: el Context Graph inicial (0.3) se modela con
tablas relacionales + JSONB para atributos variables por tipo de entidad, y
`pgvector` para búsqueda semántica cuando exista contenido embebible. Una
graph database dedicada solo se justificaría si las consultas de
travesía de grafo se volvieran el cuello de botella dominante — eso es una
decisión para un ADR futuro con datos reales, no una preparación especulativa
en 0.1.

## Modelo conceptual (0.3+, no implementado)

```
users
  └── identity_accounts      (cuentas de fuentes conectadas — 0.2+)
  └── context_entities        (Context: evidencia normalizada)
        └── entity_relations  (relaciones entre entidades)
  └── situations               (Situation: agrupaciones con sentido)
        └── situation_evidence (N:N situations ↔ context_entities)
  └── impacts                   (Impact: relaciones cross-domain entre situations)
        └── impact_situations   (N:N impacts ↔ situations)
```

Principios de diseño que este modelo debe respetar cuando se implemente:

- **Separación identidad / contexto / credenciales** (ver `SECURITY.md`):
  `identity_accounts` almacena credenciales de conectores cifradas; nunca en
  la misma tabla ni el mismo nivel de acceso que `context_entities`.
- **Evidence + Confidence como columnas de primera clase**, no como texto
  libre: cada `situation` e `impact` debe poder distinguir hechos,
  inferencias y estimaciones, con un campo de confianza numérico o
  categórico (ver `docs/CONTEXT_ENGINE.md`).
- **JSONB para atributos variables por tipo**, evitando una tabla
  hiper-normalizada por cada tipo de entidad (email, evento, transacción,
  etc.) mientras el número de tipos siga siendo manejable.
- **`pgvector`** se añade cuando exista contenido embebible real (0.3+ /
  0.7+), no antes.

## Entorno de desarrollo en 0.1

`docker-compose.yml` en la raíz levanta un Postgres local (ver
`DATABASE_URL` en `.env.example`) para que el desarrollo de 0.2/0.3 no
dependa de infraestructura adicional. En 0.1 esta base de datos no tiene
ningún esquema de aplicación — solo está disponible para desarrollo futuro
inmediato.

## Qué NO hacer en 0.1

- No crear migraciones para las tablas de arriba todavía: no hay código que
  las use, y una migración sin código que la lea es exactamente el tipo de
  "preparación especulativa" que `CLAUDE.md` pide evitar.
- No añadir un ORM todavía. Esa es una decisión para cuando exista código
  real que necesite persistir datos (0.2/0.3), y debería documentarse en un
  ADR si implica una dependencia significativa (p. ej. Prisma, Drizzle).
