# Especificación de producto — Log Spend Auditor

## Problema

Las organizaciones pagan por grandes volúmenes de datos ingeridos en Splunk,
pero una parte de esos datos puede tener muy poco uso operativo o analítico.
No existe hoy una herramienta de autoservicio (sin consultoría, sin
plataforma de pipeline cara) que responda con evidencia: **¿qué datos estoy
pagando por ingerir pero casi nunca utilizo?**

## Usuario objetivo

Administrador de Splunk o ingeniero de plataforma en una organización que ya
sospecha que está pagando de más, y quiere una evidencia concreta (en GB y en
dólares) para llevar a su jefe o a la renovación del contrato — sin pasar por
una consultora ni una plataforma de pipeline que requiere implementación.

## Qué hace la herramienta (MVP)

1. Recolecta ingest por `(index, sourcetype)` desde `license_usage.log`.
2. Recolecta señales de uso real: búsquedas interactivas (`_audit`), saved
   searches / alertas programadas (REST `/saved/searches`), y opcionalmente
   una lista manual de datasets usados en dashboards.
3. Cruza ambas cosas y clasifica cada dataset en una categoría explicable
   (ver `docs/scoring.md`).
4. Calcula un ahorro potencial estimado en dólares, dado el spend anual o el
   costo por GB/día que el usuario indique.
5. Genera un reporte HTML y Markdown listo para compartir.

## Qué NO hace (fuera de alcance del MVP, explícito)

- No borra, modifica ni filtra datos en Splunk.
- No envía datos del cliente a ningún servidor externo (local-first).
- No resuelve el 100% del parsing de SPL (macros anidadas, data models
  complejos) — lo marca `UNKNOWN` en vez de adivinar.
- No descubre automáticamente qué panel de qué dashboard usa qué dataset
  (requiere input manual opcional en el MVP).
- No soporta Elastic todavía (diseñado para no bloquear esa evolución futura,
  pero no implementado).

## Interfaz (CLI)

```
splunk-spend-auditor quickscan --from-csv <dir>
splunk-spend-auditor audit --from-csv <dir> [--annual-spend N | --cost-per-gb-day N]
                            [--top N] [--redact-hosts] [--redact-names]
                            [--protect-file archivo.txt] [--format html|md|both]
splunk-spend-auditor audit --host <splunk-host> --token <token> [...mismos flags]
```

`quickscan` es la versión gratuita de validación (ver `docs/validation-plan.md`);
`audit` es el flujo completo (equivalente al plan Pro cuando el pricing esté
activo — en el MVP técnico no hay todavía enforcement de licencia, es la
misma build).

## Naming (Tarea 18 — pendiente)

"Log Spend Auditor" es el nombre de trabajo. Requisitos para el nombre final:
fácil de recordar, técnico, serio, relacionado con Splunk/ingest/spend,
usable si en el futuro se agrega Elastic (evitar un nombre que diga
"Splunk" literalmente en la marca, para no atarse ni generar problema de
trademark con Splunk/Cisco). **No se investigó disponibilidad de dominio ni
trademark en esta fase — queda como tarea explícita antes de publicar
públicamente en GitHub con un nombre definitivo.**

## Pricing (Tarea 14 — rango propuesto, decisión final pendiente del usuario)

- Quickscan: gratis.
- Reporte único (pago único): $149–$299.
- Licencia recurrente (informes mensuales + tendencia): $49–$99/mes.
- Licencia "consultor/MSP" (uso en múltiples clientes finales): a definir,
  probablemente un múltiplo del precio individual, no fijado en esta fase.

Razonamiento de anclaje: un contrato mediano de Splunk ronda los
$94,200/año (fuente: Vendr, ver investigación de mercado previa); incluso un
5-10% de reducción son $4,700-$9,400/año, lo que hace que $149-$299 por un
reporte único sea, en la práctica, una fracción mínima del ahorro potencial
— y por eso el brief indica explícitamente no fijar el precio solo mirando
competidores, sino relacionarlo con el ahorro potencial mostrado en el propio
reporte.

## Roadmap post-MVP (no bloqueante para Fase 2/3)

1. Automatizar detección de uso en dashboards (parsing de Studio JSON/XML).
2. Resolver macros/eventtypes de primer nivel (no anidados) para subir de
   `PARTIAL` a `HIGH` una fracción mayor de búsquedas.
3. Módulo Elastic (`_disk_usage` + `_field_usage_stats`, ver investigación de
   mercado previa) como segundo producto sobre el mismo motor de scoring.
4. Licencia recurrente con comparación mes a mes (requiere persistencia local
   simple, ej. SQLite — todavía sin backend remoto).
