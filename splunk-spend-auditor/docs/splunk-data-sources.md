# Fuentes de datos de Splunk para Log Spend Auditor

Para cada fuente: qué entrega, permisos, compatibilidad, restricciones,
confiabilidad, costo/riesgo de performance, si requiere rol admin, y alternativa
si no hay acceso. Cada afirmación está marcada como **[HECHO]** (documentado o
confirmado en Splunk Community/documentación oficial), **[INFERENCIA]**
(conclusión razonable, no verificada directamente) o **[HIPÓTESIS]** (a
validar en un entorno real).

---

## 1. `license_usage.log` (vía `index=_internal source=*license_usage.log`)

**Qué entrega:** una línea por combinación `(host, index, source, sourcetype)`
reportada periódicamente por cada indexer, con los bytes indexados (`b`) en ese
intervalo. Es la fuente primaria de "cuánto se ingiere y dónde".

**Campos relevantes [HECHO]** (confirmados en Splunk Community, ya que Splunk
no publica una referencia formal de estos campos):
- `h` → host
- `i` → instancia/pool de licencia
- `idx` → index
- `s` → source
- `st` → sourcetype
- `b` → bytes
- `type` → se filtra por `type="Usage"` para quedarse solo con los eventos de
  consumo (hay otros tipos de evento en el mismo log).

**Query base [HECHO, confirmada en Splunk Community]:**
```
index=_internal source=*license_usage.log type="Usage"
| eval indexname=if(len(idx)=0 OR isnull(idx),"(UNKNOWN)",idx)
| stats sum(b) as bytes by _time, indexname, st
```

**Permisos:** requiere que el rol del usuario tenga acceso al índice
`_internal` y la capacidad `search`. **No requiere rol admin** — es una
capacidad de índice asignable a cualquier rol [HECHO, Splunk Community].

**Splunk Enterprise:** sí. **Splunk Cloud:** sí, pero el acceso a `_internal`
no siempre está habilitado por defecto para roles no-admin; debe concederse
explícitamente en el rol [HECHO].

**Restricción crítica — squashing [HECHO, documentado por Splunk]:** cuando el
número de tuplas distintas `(source, sourcetype, host, index)` observadas por
un indexer supera el parámetro `squash_threshold` (configurable en
`server.conf`, stanza `[license]`), Splunk **descarta los valores de `host` y
`source`** en los eventos que exceden el umbral y solo reporta la tupla
`(sourcetype, index)`. Esto significa:
- El desglose por **`(index, sourcetype)`** está garantizado completo — no se
  pierden bytes.
- El desglose por **host o por source** puede subestimar sistemáticamente el
  volumen en entornos con muchos hosts/sources distintos (alta cardinalidad).
- **Consecuencia de diseño (ver DECISIONS.md D004):** el motor de scoring usa
  `(index, sourcetype)` como unidad mínima. Host/source se muestran solo como
  información adicional, nunca como base de clasificación.

**Confiabilidad:** alta para `(index, sourcetype)`; variable para host/source
según cardinalidad del entorno **[HECHO + INFERENCIA sobre el impacto]**.

**Costo/riesgo de performance:** bajo — es una búsqueda sobre `_internal`, un
índice típicamente pequeño comparado con los índices de datos del cliente
**[INFERENCIA razonable, no medida]**.

**Alternativa si no hay acceso:** el endpoint REST
`/services/licenser/...` (introspección de licencia) da totales agregados de
alto nivel, pero no el desglose por sourcetype que necesita el producto
**[INFERENCIA, no se profundizó en Fase 2]**. Sin acceso a `_internal`, el
modo CSV (D002) sigue funcionando si el cliente exporta la query manualmente
con un usuario que sí tenga el permiso.

---

## 2. `_audit` (búsquedas interactivas)

**Qué entrega:** un evento por cada búsqueda ejecutada, con el usuario, el
texto SPL completo (`search`), el `search_id`, y si fue autorizada
(`info=granted`).

**Query base [HECHO, patrón estándar de Splunk Community]:**
```
index=_audit action=search info=granted search=*
NOT "user=splunk-system-user"
NOT "search='|history"
NOT "search='typeahead"
```

**Cómo distinguir interactivo de programado [HECHO]:** las búsquedas
disparadas por el scheduler tienen `search_id` con el prefijo `scheduler_...`;
filtrar `NOT search_id=scheduler*` dentro del `_audit` aísla las búsquedas
verdaderamente interactivas (un usuario tecleando en Search). Las búsquedas
programadas se obtienen mejor y de forma más confiable desde el endpoint REST
`/saved/searches/{name}/history` (fuente 3), no desde `_audit`.

**Permisos:** igual que `_internal` — requiere acceso al índice `_audit` y
capacidad `search`; no requiere admin per se, pero por defecto suele estar
más restringido que `_internal` en instalaciones que siguen buenas prácticas
de seguridad **[INFERENCIA]**.

**Splunk Enterprise:** sí. **Splunk Cloud:** sí, con la misma salvedad de rol
que `_internal`.

**Restricciones conocidas [HECHO, reportado repetidamente en Splunk
Community]:** en algunos search heads, campos como `search` o `user` pueden
faltar en `_audit` si la configuración de forwarding del search head a los
indexers no está completa, o si el usuario está en modo "fast mode" en vez de
"verbose mode" al inspeccionar resultados. El producto debe tratar la ausencia
de estos campos como señal de baja confiabilidad de la fuente, no como
"cero búsquedas".

**Confiabilidad:** media-alta cuando el entorno está bien configurado; el
propio `search` es texto libre en SPL y su parsing tiene los límites descritos
en `docs/scoring.md` (confianza HIGH/PARTIAL/UNKNOWN).

**Costo/riesgo de performance:** bajo-medio; `_audit` puede ser voluminoso en
entornos con muchos usuarios y mucho uso interactivo — se recomienda acotar
por rango de tiempo (30-90 días) **[INFERENCIA]**.

**Alternativa si no hay acceso:** ninguna equivalente completa; el producto
puede operar en modo degradado usando solo saved searches (fuente 3) y marcar
explícitamente que no se evaluó uso interactivo ad-hoc.

---

## 3. REST API — `/services/saved/searches` y `/saved/searches/{name}/history`

**Qué entrega:** la configuración de cada saved search/alerta/reporte
programado (incluye el SPL en `search`, si está programado `is_scheduled`, cron
`cron_schedule`, si dispara una acción de alerta) y, vía `/history`, el
historial de ejecuciones de esa saved search concreta.

**Endpoints confirmados [HECHO, documentación oficial Splunk REST API
Tutorials]:**
- `/saved/searches` — listar/crear saved searches.
- `/saved/searches/{name}` — detalle de una.
- `/saved/searches/{name}/history` — historial de ejecuciones.
- `/search/jobs` — crear un job de búsqueda ad-hoc (usado por el modo REST
  del collector para ejecutar las queries SPL de este mismo producto).

**Gotcha de scoping por app/usuario [HECHO, Splunk Community + Splunk Dev
forum]:** el SDK/REST por defecto solo devuelve las saved searches del
namespace (app/usuario) de la conexión. Para obtener **todas** las saved
searches del entorno hay que:
- Usar `servicesNS/-/-/saved/searches` (wildcard user/app), o
- En el SDK Python, conectar con `app="-"`.
Si el collector no hace esto explícitamente, subestimará el uso real y
generará falsos positivos de "sin uso". **Esto es un requisito de
implementación, no opcional.**

**Permisos:** requiere capacidad `list_settings`/acceso de lectura a saved
searches; para ver saved searches de *otros* usuarios/apps se requiere
típicamente un rol con `search` amplio o admin, dependiendo de los permisos
compartidos de cada saved search **[INFERENCIA basada en el modelo de
permisos estándar de Splunk]**.

**Splunk Enterprise:** sí. **Splunk Cloud:** sí, la REST API estándar está
disponible en Splunk Cloud igual que en Enterprise [HECHO].

**Confiabilidad:** alta para metadata (existe/no existe, está programada o
no); alta para el conteo de ejecuciones en `/history`.

**Costo/riesgo de performance:** bajo — colecciones de configuración, no
datos de eventos.

**Alternativa si no hay acceso:** exportar `savedsearches.conf` manualmente
(si el usuario tiene acceso de archivo al sistema, fuera del alcance típico
de un admin de Splunk Cloud) — se descarta como poco realista para el MVP.

---

## 4. `tstats` sobre data models

**Qué entrega:** agregaciones rápidas sobre datos ya acelerados en un data
model (usado típicamente en Splunk Enterprise Security / CIM).

**Uso en este producto:** **no se usa en el MVP.** Se documenta aquí porque
una búsqueda que usa `| tstats ... from datamodel=X` no menciona `index=` ni
`sourcetype=` explícitamente — es exactamente el caso que el parser marca
`PARTIAL`/`UNKNOWN` (ver `docs/scoring.md`). Resolver qué índices alimentan un
data model requiere leer su definición (`datamodels.conf` /
`/services/datamodel/model`), lo cual queda fuera del alcance del MVP.

**Confiabilidad del producto sobre estos casos:** intencionalmente baja —
cualquier dataset que solo aparezca referenciado a través de `tstats`/data
models se marca `UNKNOWN` y nunca `POSSIBLE_WASTE` (ver DECISIONS.md D006).

---

## 5. `metadata` command

**Qué entrega:** `| metadata type=sourcetypes index=*` da, por índice, la
lista de sourcetypes presentes y sus timestamps de primer/último evento —
**no** da bytes ingeridos ni uso.

**Uso en este producto:** como fuente complementaria de "última vez que se vio
un evento de este sourcetype" (`recentTime`), útil para distinguir un dataset
inactivo (ya no ingiere) de uno activo pero no buscado. No reemplaza a
`license_usage.log` para el cálculo de GB/día.

**Permisos/compatibilidad:** igual que cualquier búsqueda normal sobre los
índices del cliente — no requiere acceso especial a `_internal`/`_audit`.

---

## 6. Saved searches / scheduled searches (detalle de uso — ver fuente 3)

Documentado en la fuente 3. Se separa aquí conceptualmente porque en el
producto es una fuente de **señal de uso**, no de **volumen de ingest**.

---

## 7. Dashboards

**Qué entrega:** los paneles de un dashboard (`.xml` o Studio JSON) contienen
las queries que ese dashboard ejecuta.

**Estado en el MVP:** **fuera de alcance de detección automática.** Splunk no
expone una API directa y confiable para "qué dataset usa cada panel de cada
dashboard" sin parsear el XML/JSON de cada dashboard uno por uno. Para el MVP,
el producto permite al usuario **pegar manualmente** una lista de
datasets-usados-en-dashboards (CSV opcional) que se incorpora al scoring como
señal `dashboards>0` — ver `docs/product-spec.md`. Automatizar la extracción
completa queda como mejora post-MVP.

**Riesgo si se omite:** un dataset usado solo por un dashboard y por ninguna
búsqueda ni alerta se clasificaría como `REVIEW` en vez de `HIGH_VALUE` sin
este dato manual — **por diseño, `REVIEW` nunca es `POSSIBLE_WASTE`**, así que
el riesgo de falso positivo grave queda acotado incluso sin esta fuente.

---

## 8. Alertas (`alert_actions`, triggered alerts)

**Qué entrega:** si una saved search tiene configurada una acción de alerta
(`actions=email`, `actions=webhook`, etc.), viene incluido en el mismo detalle
de `/saved/searches` (fuente 3) — no es un endpoint separado.

**Estado en el MVP:** cubierto como parte de la fuente 3 (`is_scheduled` +
presencia de `actions` no vacío).

---

## Resumen de confiabilidad por fuente

| Fuente | Admin requerido | Splunk Cloud | Confiabilidad | Base del scoring |
|---|---|---|---|---|
| `license_usage.log` (idx+st) | No | Sí (con rol) | Alta | Sí — volumen |
| `license_usage.log` (host/source) | No | Sí (con rol) | Media-baja (squashing) | No — solo informativo |
| `_audit` interactivo | No | Sí (con rol) | Media-alta | Sí — uso |
| `/saved/searches` + `/history` | No | Sí | Alta | Sí — uso |
| `tstats`/data models | No | Sí | Baja (fuera de alcance) | No |
| `metadata` | No | Sí | Alta (para lo que mide) | Complementaria |
| Dashboards | No | Sí, pero manual | N/A (manual) | Complementaria opcional |
