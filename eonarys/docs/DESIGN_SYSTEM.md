# DESIGN_SYSTEM.md

## Dirección visual

EONARYS debe verse: futurista, premium, oscuro, elegante, tecnológico,
limpio. **No** debe parecer un videojuego ni abusar de efectos.

## Identidad

- **Fondos**: azul noche / negro azulado.
- **Acento principal**: cyan/azul luminoso.
- **Acentos cálidos**: pequeños, y solo cuando tienen significado (p. ej. una
  urgencia o una alerta), nunca decorativos.
- **Superficies glass/translúcidas**: con moderación, no como default de
  cada tarjeta.
- **Profundidad**: mediante iluminación sutil, no mediante sombras duras ni
  bordes gruesos.
- **Animaciones**: suaves (Framer Motion), nunca llamativas por sí mismas.
- **Tipografía**: limpia, alta legibilidad.
- **Espacio**: generoso. El contenido respira.

## Concepto de IA visual

Puede existir una representación visual de EONARYS (por ejemplo, un
indicador sutil de "presencia"), pero siempre **secundaria a la
información**. La información es el producto; la representación de la IA no
compite visualmente con ella.

## Home conceptual

```
EONARYS

Buenos días.

¿Qué tienes en mente?

[Contexto relevante A]
[Contexto relevante B]
[Contexto relevante C]

EONARYS analiza. Tú decides.
```

En 0.1, `[Contexto relevante A/B/C]` son tarjetas con datos **demo/mock
explícitamente marcados como tales** (ver `apps/web`), no una simulación de
inteligencia real.

## Regla explícita: no dashboard fijo

**No** construir una cuadrícula fija de secciones del tipo:

```
Finanzas | Viajes | Agenda | Proyectos | Compras | Decisiones
```

La interfaz principal (`Context Surface`, ver `docs/PRODUCT.md`) debe estar
preparada estructuralmente para ser dinámica: una lista/superficie de
tarjetas de contexto ordenable y reemplazable, no módulos de dominio fijos
con posiciones predefinidas. En 0.1 esto significa: el layout de la home
renderiza una colección de "context cards" desde datos (aunque esos datos
sean mock), no componentes hardcodeados por dominio.

## Design tokens (0.1)

Los tokens viven en `packages/ui` y se consumen vía Tailwind (`tailwind.config`
extiende la paleta con estos tokens, no valores hardcodeados en componentes).

| Token                | Valor aproximado            | Uso                                       |
| -------------------- | --------------------------- | ----------------------------------------- |
| `background.base`    | `#05070d`                   | Fondo principal (negro azulado)           |
| `background.surface` | `#0b1120`                   | Superficies elevadas (azul noche)         |
| `background.glass`   | `rgba(15, 23, 42, 0.55)`    | Superficies glass, con moderación         |
| `accent.primary`     | `#22d3ee`                   | Cyan luminoso — acento principal          |
| `accent.warm`        | `#f59e0b`                   | Acento cálido — solo urgencia/significado |
| `text.primary`       | `#e6edf7`                   | Texto principal sobre fondo oscuro        |
| `text.muted`         | `#8b96ac`                   | Texto secundario                          |
| `border.subtle`      | `rgba(148, 163, 184, 0.12)` | Bordes sutiles                            |

Estos valores son el punto de partida de 0.1 y pueden refinarse en fases
posteriores; cualquier cambio se hace en `packages/ui` (fuente única de
verdad), nunca duplicando valores en componentes de `apps/web`.

## Accesibilidad (0.1)

- Contraste de texto principal sobre fondo ≥ WCAG AA.
- Todo elemento interactivo es navegable por teclado y tiene estado de foco
  visible.
- Imágenes/iconos decorativos con `aria-hidden`; los que comunican
  información tienen texto alternativo.
- Respeto a `prefers-reduced-motion` en las animaciones.
