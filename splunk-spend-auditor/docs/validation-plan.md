# Plan de validación de mercado — Log Spend Auditor

Basado en la Tarea 19 del brief y en el experimento ya propuesto en la
investigación de mercado previa. Este documento es el plan operativo concreto
para la Fase 3 (no ejecutado todavía).

## Concepto: "Splunk License Waste Quickscan"

Versión gratuita, sin registro, sin necesidad de credenciales de Splunk vivas:
el usuario exporta manualmente los resultados de 2-3 queries SPL (provistas
como `.spl` copiables) a CSV, y corre:

```
splunk-spend-auditor quickscan --from-csv ./mis-exports/
```

Salida en terminal (no HTML todavía, para máxima fricción-cero):

```
Total ingest: 243.0 GB/day
Top 5 consumers by GB/day:
  1. windows:eventlog     35.2 GB/day
  2. proxy_debug          22.1 GB/day
  ...

Review candidates (possible waste): 2 datasets, 41.3 GB/day (17.0% of total)

Generate Full Spend Audit → https://<landing-page>
```

## Landing page / mensaje / CTA

- **Mensaje central:** "¿Qué datos estás pagando por ingerir en Splunk pero
  casi nunca usas? Corre un escaneo gratuito y de solo lectura en 10 minutos,
  sin enviar tus datos a ningún servidor."
- **CTA principal:** botón/link para el reporte HTML completo (Pro) —
  preventa a un precio único (ver `docs/product-spec.md` Tarea 14) mientras el
  motor Pro se termina de construir, o entrega inmediata si ya está listo.
- **CTA secundario:** lista de espera por email para quienes solo quieren
  ser notificados cuando salga la versión Elastic o la capa recurrente.
- **Prueba social diferida:** no se usan testimonios inventados; la página
  empieza sin testimonios y se actualiza cuando existan reales.

## Free vs. Paid (resumen de negocio, detalle técnico en report-design.md)

- **Free:** Quickscan CLI (terminal) — top 5, candidatos top 3, sin reporte
  HTML descargable.
- **Paid:** reporte completo HTML/Markdown/CSV con todos los datasets,
  desglose de ahorro, tendencias.

## Métricas de validación y umbrales propuestos

(Umbrales tomados de la investigación de mercado previa; son un punto de
partida razonable, no una certeza — se ajustan con lo que se observe.)

| Métrica | Umbral (ventana de 4 semanas) | Qué significa si se cumple |
|---|---|---|
| Estrellas/clones en GitHub del Quickscan | ≥ 100 | Hay interés en probarlo |
| Emails capturados en landing | ≥ 30 | Hay interés en el resultado completo |
| Preventas del reporte Pro | ≥ 3 | Hay disposición real a pagar sin reunión |

**Decisión de negocio pendiente (no técnica):** si hay preventas → construir
el motor Pro completo. Si hay estrellas/emails pero cero preventas → probar un
precio distinto o un ángulo distinto (ej. licencia para consultoras/MSP en vez
de venta directa a admins individuales) antes de invertir más tiempo de
desarrollo.

## Canales de distribución sugeridos (sin reuniones, sin ventas directas)

- Splunk Community / Splunk Answers (en hilos existentes sobre uso de
  licencia por sourcetype — hay varios hilos reales citados en
  `docs/splunk-data-sources.md` con esta pregunta exacta).
- r/Splunk.
- Splunk User Groups (Slack/foros), si existe uno accesible sin trato
  comercial directo.
- Un post técnico explicando el punto ciego de `_audit`/squashing (contenido
  técnico genuino, no solo promoción).

## Qué este plan NO valida todavía

- Si el precio final ($49-$299, ver `docs/product-spec.md`) es el óptimo —
  eso requiere iteración posterior a las primeras preventas.
- Si el modo REST en vivo (vs. CSV manual) es un requisito real para que
  alguien pague, o si el CSV manual es suficiente fricción-aceptable — se
  puede inferir de si la gente pide automatización en el feedback.
