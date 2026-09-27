# @eonarys/ui

Componentes y design tokens compartidos, consumidos directamente como
código fuente TypeScript por `apps/web` (vía `transpilePackages` de
Next.js — sin paso de build propio, para no añadir una herramienta de
bundling adicional en 0.1).

## Contenido en 0.1

- `tokens`: los design tokens documentados en `docs/DESIGN_SYSTEM.md`
  (única fuente de verdad; `apps/web` los consume desde aquí, no los
  duplica).
- `ContextCardView`: el componente que renderiza un `ContextCard` de
  `@eonarys/core` como tarjeta glass, con su nivel de evidencia visible.
- `DemoBadge`: el badge que marca explícitamente cualquier contenido como
  demo/mock (ver `docs/ROADMAP.md`: 0.1 no debe simular inteligencia real).

No incluye un sistema de componentes genérico (botones, inputs, modales,
etc.) más allá de lo que la home conceptual de 0.1 necesita — eso se
construye cuando haya pantallas reales que lo requieran.
