# CONTEXT_ENGINE.md

Este documento describe el modelo conceptual `Context → Situation → Impact`.
**No implementado en 0.1** — ver `docs/ROADMAP.md`. Se documenta ahora para
que el modelo de datos de 0.1 (`docs/DATA_MODEL.md`) no contradiga esta
dirección más adelante.

## Los tres niveles

### 1. Context (evidencia)

El nivel más bajo: hechos normalizados provenientes de fuentes conectadas.
Un email, un evento de calendario, una transacción, un documento. Cada
elemento de contexto es evidencia, no producto final — el usuario no
"navega su contexto" como quien navega una bandeja de entrada.

### 2. Situation (agrupación con sentido)

Un Situation Engine agrupa evidencia relacionada en una **Situation**: una
unidad con sentido para el usuario (ver `docs/PRODUCT.md`, Situation-first).
Ejemplos: "viaje a Buenos Aires en octubre", "renovación de contrato
pendiente", "semana sobrecargada".

Una Situation tiene, conceptualmente:

- un tipo (viaje, decisión pendiente, gasto extraordinario, etc.)
- evidencia asociada (los elementos de Context que la componen)
- una ventana temporal relevante
- un estado (activa, resuelta, ignorada por el usuario)

### 3. Impact (relación cross-domain)

El Impact Engine encuentra relaciones **entre** Situations de dominios
distintos. Es la capa que produce explicaciones como la del ejemplo
canónico de `docs/PRODUCT.md`: un viaje que impacta compromisos laborales y
gastos del mes.

Un Impact, conceptualmente:

- conecta dos o más Situations
- tiene una explicación en lenguaje natural del porqué de la relación
- lleva asociado el nivel de Evidence + Confidence correspondiente (ver
  `docs/PRODUCT.md`, principio Evidence + Confidence)

## Evidence + Confidence, en términos de datos

Todo insight (una Situation relevante, o un Impact) debe poder distinguir:

- **hechos** — datos directamente observados desde una fuente conectada
- **inferencias** — conclusiones derivadas de hechos mediante reglas o
  modelos
- **estimaciones** — proyecciones con incertidumbre explícita (p. ej. un
  gasto estimado)

y exponer un **nivel de confianza** asociado a inferencias y estimaciones.
Esto no es un detalle de UI: es un requisito del modelo de datos desde
`docs/DATA_MODEL.md` en adelante, para que ninguna fase futura tenga que
retrofit-ear esta distinción.

## Por qué esto no se implementa en 0.1

Construir el Context Graph, el Situation Engine o el Impact Engine sin
fuentes conectadas reales (0.2+) produciría necesariamente lógica simulada
o hardcodeada disfrazada de inteligencia — exactamente lo que
`docs/ROADMAP.md` prohíbe explícitamente para 0.1 ("no simular inteligencia
como si fueran datos reales"). 0.1 se limita a dejar la estructura de
paquetes (`packages/context`, `packages/ai`) preparada conceptualmente, sin
implementación funcional.
