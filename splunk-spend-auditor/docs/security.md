# Seguridad — Log Spend Auditor

## Principios (no negociables para el MVP)

1. **No customer events transmitted.** El motor de análisis nunca necesita
   leer eventos crudos de datos del cliente — solo metadata agregada (bytes
   por index/sourcetype, conteos de búsquedas, configuración de saved
   searches). Ningún flujo del producto envía `_raw` a ningún lado.
2. **No external telemetry by default.** El CLI no llama a ningún servidor
   nuestro. No hay analítica de uso, no hay "phone home", no hay
   actualización automática que reporte datos del cliente. Si en el futuro se
   agrega telemetría opcional (para saber cuánta gente usa la herramienta),
   será opt-in explícito y documentado, nunca por defecto.
3. **Credentials stored only locally**, y solo si el usuario elige el modo
   REST. Nunca se piden ni almacenan credenciales en el modo CSV.
4. **Operacionalmente read-only contra Splunk** -- no es lo mismo que "solo
   usa HTTP GET". El modo REST llama a `GET` para introspección
   (`/saved/searches`, `/authentication/current-context`,
   `/authorization/roles/...`) y a `POST /services/search/jobs` en modo
   `exec_mode=oneshot` para ejecutar cada query de solo lectura -- así
   funciona la API de búsqueda de Splunk incluso para queries que no
   escriben nada (`oneshot` ni siquiera deja un job persistente). Ninguna
   de las dos cosas modifica configuración, borra datos ni cambia inputs.
   Nunca se llama a un endpoint de escritura/borrado
   (`/data/inputs/...` `POST`/`DELETE`, `/services/.../acl` `POST`, etc.)
   -- verificado por inspección directa: los únicos métodos HTTP usados en
   todo `collector/rest_collector.py` son `GET` y ese único `POST` de
   búsqueda.

## Superficie de datos sensibles y cómo se trata

| Dato | Sensibilidad | Tratamiento |
|---|---|---|
| Texto SPL de búsquedas (`_audit` `search=`) | Puede contener nombres de campos, valores de negocio, a veces literales sensibles si el usuario buscó `password=X` por error | Se parsea solo para extraer `index=`/`sourcetype=`; el texto completo de la búsqueda **no se incluye en el reporte**, solo un resumen agregado (conteo, si es HIGH/PARTIAL/UNKNOWN) |
| Nombres de usuario (`_audit` `user=`) | Identifica personas | Se usa solo para el conteo `unique_users_30d`; el reporte muestra el número, no la lista de usuarios, salvo que el usuario active explícitamente un modo "detallado" que sí liste usuarios (fuera del MVP) |
| Nombres de host (`license_usage.log` `h=`) | Puede revelar topología interna | Se muestra en el reporte solo como información complementaria, nunca como clave de agrupación (ver D004); el usuario puede pasar `--redact-hosts` para ofuscarlos con hashes cortos en el reporte |
| Nombres de index/sourcetype | Bajo, pero pueden insinuar qué sistemas de negocio existen | Se muestran tal cual — son el objeto central del análisis; si el usuario necesita compartir el reporte externamente (ej. con un consultor), puede pasar `--redact-names` para reemplazarlos por identificadores genéricos (`idx_001`, `st_004`) manteniendo la tabla de mapeo solo local |
| Credenciales/token de Splunk (modo REST) | Alta | Nunca se escriben a disco por el CLI; se leen de variable de entorno (`SPLUNK_TOKEN`) o se piden interactivamente (`getpass`), nunca como argumento de línea de comandos en texto plano (para evitar que queden en el historial de shell) |

## Modelo de amenazas (resumido)

- **Amenaza: el reporte HTML se comparte externamente y expone topología
  interna.** Mitigación: flags `--redact-hosts`/`--redact-names` (sección
  anterior). Documentado en el propio reporte cuando no se usan.
- **Amenaza: el token de Splunk queda en un archivo de configuración
  versionado por error.** Mitigación: el CLI nunca escribe el token a un
  archivo de proyecto; solo lo lee de env var o prompt interactivo. Se
  documenta explícitamente en el `README.md` que el usuario no debe
  hardcodearlo en scripts que suba a git.
- **Amenaza: una query mal construida contra `_audit`/`_internal` genera
  carga excesiva en el search head del cliente.** Mitigación: todas las
  queries en `src/splunk_spend_auditor/queries/` acotan explícitamente `earliest=`/`latest=` (por
  defecto 30-90 días) y usan `stats`/`tstats` en vez de traer eventos crudos
  donde es posible.
- **Amenaza: falso positivo de "possible waste" sobre un dataset de
  seguridad/compliance causa que alguien borre datos regulados.** Mitigación:
  reglas de `PROTECTED` (docs/scoring.md sección 6) + lenguaje
  obligatoriamente no-imperativo ("candidato a revisión", nunca "eliminar") +
  disclaimer explícito en cada reporte.

## Qué NO se implementa en el MVP (y por qué no es necesario ahora)

- Cifrado en reposo del reporte generado: el reporte vive en la máquina del
  usuario, bajo su propio control de acceso de sistema de archivos — igual
  que cualquier otro archivo local que genere.
- SSO/autenticación propia: no hay backend, no hay "cuenta" de nuestro
  producto que proteger.
- Auditoría de quién ejecutó el CLI: es una herramienta local de una sola
  persona en esta fase; no hay multi-usuario que auditar.
