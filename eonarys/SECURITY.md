# Security

EONARYS potencialmente manejará información extremadamente sensible (correo,
calendario, finanzas, documentos personales). La seguridad se trata como
requisito de fundación, no como algo a añadir después.

## Postura desde 0.1

- **Secure-by-default.** Ninguna funcionalidad se habilita "por si acaso";
  todo lo que no está implementado en 0.1 simplemente no existe en el código.
- **Mínimo privilegio.** Cuando existan credenciales de conectores (0.2+),
  se solicitarán los scopes mínimos necesarios para cada fuente.
- **Secretos fuera del repositorio.** Nada de tokens, claves o credenciales
  reales se commitea. `.env.example` solo contiene nombres de variables y
  valores de ejemplo no funcionales.
- **Sin PII innecesaria en logs.** El código de 0.1 no procesa PII real (todo
  el contenido de la home es mock), pero el principio aplica desde ahora:
  ningún log debe incluir contenido de correo, ubicación, datos financieros
  ni identificadores personales.
- **No enviar datos a terceros accidentalmente.** 0.1 no hace llamadas
  salientes a servicios de terceros. Cualquier integración futura deberá
  documentar explícitamente qué datos salen, hacia dónde, y por qué.
- **Dependencias auditadas.** `pnpm audit` se ejecuta en CI. Vulnerabilidades
  críticas conocidas bloquean el merge.
- **Headers de seguridad razonables.** `apps/web` configura headers HTTP
  básicos (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) a
  nivel de Next.js config.

## Separación conceptual: identidad, contexto y credenciales

Aunque 0.1 no implementa conectores reales, el modelo de datos (ver
`docs/DATA_MODEL.md`) se diseña desde ahora separando tres conceptos que
nunca deben mezclarse en el mismo almacén ni en el mismo nivel de acceso:

1. **Identidad** — quién es el usuario (cuenta, sesión).
2. **Contexto** — la información derivada/normalizada sobre su vida
   (situaciones, entidades, relaciones).
3. **Credenciales de conectores** — tokens de acceso a fuentes externas
   (Gmail, Calendar, bancos, etc.), cuando existan.

Las credenciales de conectores, cuando se implementen, se cifrarán en reposo
y nunca se expondrán al frontend ni se incluirán en exports de contexto.

## Threat assumptions iniciales

- El usuario es el único actor autorizado a tomar decisiones ejecutables;
  EONARYS es un _advisor_, nunca un _executor_ (ver `docs/PRODUCT.md`,
  principio "Advisor, not executor"). Esto reduce (pero no elimina) el
  impacto de una cuenta comprometida: un atacante con acceso a la sesión
  puede leer contexto, no ejecutar acciones irreversibles en nombre del
  usuario, porque esa capacidad no existe en el sistema.
- Las fuentes conectadas (0.2+) son puntos de entrada de alto valor: un
  atacante con acceso a un token de conector podría exfiltrar información
  personal extensa. El diseño de credenciales (separadas, cifradas, con
  scope mínimo) parte de este supuesto.
- El propio EONARYS es un objetivo atractivo por agregación: aunque cada
  fuente individual (un email, un evento) sea de bajo riesgo, la
  correlación cross-domain que hace valioso al producto también lo hace un
  objetivo de mayor impacto si se compromete. Esto refuerza por qué la
  separación identidad/contexto/credenciales y el cifrado en reposo no son
  opcionales.

## Reportar una vulnerabilidad

Este es un repositorio privado en fase de fundación (pre-beta, sin usuarios
reales). Si encuentras un problema de seguridad, repórtalo como issue
privado o directamente al mantenedor del repositorio — no hay aún un
proceso de disclosure público porque no hay superficie expuesta a terceros.
