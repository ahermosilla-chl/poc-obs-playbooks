# PRIVACY.md

## Principio rector

EONARYS existe para dar contexto sobre la vida del usuario. Eso implica que,
a medida que el producto crece (0.2+), procesará información potencialmente
muy sensible: correo, calendario, finanzas, documentos, ubicación implícita.
La privacidad se diseña desde la fundación, no se añade después.

## Compromisos desde 0.1

- **Ningún dato real se procesa en 0.1.** La home muestra contenido
  claramente marcado como demo/mock. No hay conectores, no hay
  autenticación de terceros, no hay almacenamiento de datos de usuario
  real.
- **El usuario es dueño de su contexto.** Cuando existan fuentes conectadas
  (0.2+), el usuario podrá ver qué fuentes están conectadas y desconectarlas.
- **Minimización de datos.** Solo se normaliza y almacena lo necesario para
  construir Situations e Impacts (ver `docs/CONTEXT_ENGINE.md`), no un
  espejo completo de cada fuente "por si sirve después".
- **Sin compartición con terceros no solicitada.** EONARYS no comparte
  datos del usuario con terceros salvo que el usuario lo solicite
  explícitamente (p. ej. exportar información).
- **El usuario decide, siempre.** Consistente con el principio de producto
  "Advisor, not executor" (`docs/PRODUCT.md`): EONARYS no actúa sobre datos
  de terceros en nombre del usuario sin una decisión explícita en el
  momento.

## Relación con SECURITY.md

Este documento cubre _qué datos se tratan y con qué propósito_.
`SECURITY.md` cubre _cómo se protegen técnicamente_. Ambos comparten el
principio de separación conceptual entre identidad, contexto y credenciales
de conectores.

## Pendiente para fases futuras

Cuando existan fuentes conectadas y usuarios reales (0.2+ → 1.0), este
documento debe ampliarse con: política de retención de datos, proceso de
eliminación de cuenta y sus datos asociados, y — si aplica según la
jurisdicción de los usuarios — cumplimiento normativo (p. ej. GDPR). Esto se
documenta como pendiente explícito y no se implementa especulativamente en
0.1.
