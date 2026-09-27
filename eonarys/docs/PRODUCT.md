# PRODUCT.md — Visión de producto

## Qué es EONARYS

**Tagline:** Tu vida. En contexto.
**Principio:** EONARYS analiza. Tú decides.

EONARYS es una plataforma de inteligencia contextual personal. Conecta
información que ya existe en la vida diaria del usuario, detecta situaciones
relevantes, relaciona dominios distintos y explica cómo unas cosas afectan a
otras.

## Qué NO es EONARYS

- No es otro chatbot generalista.
- No es un gestor de tareas.
- No es una aplicación financiera.
- No es un agente autónomo que actúa por el usuario.

## El ejemplo canónico

Una reserva de vuelo no es simplemente un email. Puede convertirse en:

```
Reserva
   ↓
Viaje
   ↓
Calendario
   ↓
Gastos
   ↓
Trabajo
   ↓
Proyectos
   ↓
Compromisos
```

EONARYS debería poder terminar explicando algo como:

> "Este viaje coincide con dos compromisos laborales y con una fecha
> importante de tu proyecto. Además podría modificar significativamente tus
> gastos de ese mes."

Ese salto — de un dato aislado a una explicación cross-domain accionable —
es el valor central del producto. Todo lo demás (integraciones, IA, UI) está
al servicio de hacer ese salto posible, confiable y explicable.

## Principios no negociables

Estos principios se documentan aquí para que ninguna decisión técnica los
contradiga silenciosamente. Cambiarlos requiere un ADR explícito y
autorización (ver `CLAUDE.md`).

### 1. Zero-input first

EONARYS debe obtener la mayor cantidad posible de contexto desde fuentes
conectadas. El usuario debería corregir información ocasionalmente, no
mantener manualmente una base de datos sobre su vida.

### 2. Situation-first

La entidad conceptual principal **no** es un email, un evento, una tarea, una
compra o un documento. Es una **Situation** (situación).

Ejemplos de situaciones:

- viaje próximo
- cambio laboral
- compra importante
- semana sobrecargada
- proyecto bloqueado
- gasto extraordinario
- decisión pendiente

Los emails, eventos, documentos, etc. son _evidencia_ que alimenta
situaciones — no el modelo central del producto.

### 3. Cross-domain impact

El valor fundamental de EONARYS está en encontrar relaciones entre
diferentes ámbitos de la vida (viajes, trabajo, finanzas, proyectos,
relaciones, salud, etc.), no en gestionar cada ámbito de forma aislada.

### 4. Dynamic Context Surface

La página principal **no** es un dashboard tradicional con módulos fijos.
Lo que aparece en la home cambia según:

- relevancia
- proximidad temporal
- urgencia
- impacto
- cambios respecto del comportamiento habitual
- asuntos sin resolver

No existe una grilla fija de secciones tipo "Finanzas / Viajes / Agenda /
Proyectos". Ver `docs/DESIGN_SYSTEM.md`.

### 5. Advisor, not executor

EONARYS puede: observar, organizar contexto, relacionar información,
analizar, explicar, estimar, simular escenarios, sugerir.

EONARYS **no** debe: comprar, transferir dinero, cancelar servicios, enviar
comunicaciones por decisión propia, modificar calendarios automáticamente,
invertir, ni ejecutar decisiones relevantes en nombre del usuario.

**La persona siempre decide.** Este principio tiene rango de restricción de
seguridad, no solo de producto (ver `SECURITY.md`).

### 6. Evidence + Confidence

Todo insight importante debe poder indicar:

- qué evidencia lo respalda;
- cuáles son datos conocidos (hechos);
- cuáles son inferencias;
- cuáles son estimaciones;
- nivel de confianza.

Un insight sin esta trazabilidad no es un insight confiable, y EONARYS no
debe presentarlo como si lo fuera.

## Relación con la arquitectura

Estos principios se traducen directamente en la arquitectura conceptual
(`docs/ARCHITECTURE.md`) y en el modelo `Context → Situation → Impact`
(`docs/CONTEXT_ENGINE.md`). Ningún cambio de arquitectura o de modelo de
datos debería poder implementarse sin poder trazarse de vuelta a alguno de
estos seis principios.
