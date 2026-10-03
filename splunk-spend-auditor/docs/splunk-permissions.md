# Splunk permissions — Log Spend Auditor (REST mode)

Give this document to the Splunk Admin who will provision the token used
by a tester. It reflects exactly what the current code (`collector/
rest_collector.py`, `queries/*.spl`) does — not a hypothetical future
feature set. Every claim below is either **[VERIFIED]** (confirmed against
a real Splunk Enterprise lab in Fase 3A/3B/D015) or **[INFERENCE]**
(reasonable based on Splunk's documented permission model, but not
independently tested by this project). None of it is invented.

**Do not use the `admin` role for a tester token.** Admin makes the test
easy but tells you nothing about what a real customer's restricted token
would actually see — which is the whole point of D015 (see below).

## Required

Strictly necessary for `audit`/`quickscan` in REST mode to run at all.

| Access | Why | Evidence |
|---|---|---|
| Read access to the `_internal` index | `ingest_by_index_sourcetype.spl` reads `license_usage.log`, which lives in `_internal`. This is the **only mandatory** source — if it fails, the CLI aborts with an error instead of producing a report (see `RestCollectionError` in `cli.py`). | [VERIFIED] — `src/splunk_spend_auditor/queries/ingest_by_index_sourcetype.spl` comment: "requiere acceso al índice `_internal` + capacidad `search`. No requiere rol admin." Confirmed against the real lab in Fase 3A. |
| The built-in `search` capability | Needed to run any search, including the ones above. Present by default in Splunk's built-in `user` role. | [VERIFIED] — same source as above. |
| A valid authentication token (Bearer) | The CLI only supports token auth, never username/password (see `docs/splunk-permissions.md#token--authentication` below). | [VERIFIED] — `rest_collector.py`: `headers={"Authorization": f"Bearer {config.token}"}`, the only auth path in the code. |

**Splunk Cloud note [VERIFIED, docs/splunk-data-sources.md]:** access to
`_internal` is not always enabled by default for non-admin roles on
Splunk Cloud; it must be granted explicitly. Log Spend Auditor has not
been validated against Splunk Cloud (Enterprise only, see
`PROJECT_STATUS.md`).

## Recommended

Not required to run the audit, but needed for full-confidence classification.
Without these, the tool does **not** fail or guess — it degrades safely
(see "Failure behavior" below).

| Access | Why |
|---|---|
| Read access to the `_audit` index | Needed for `audit_interactive_searches.spl` — interactive search evidence, the main signal that distinguishes "confirmed unused" from "unknown." |
| Read access to saved searches (`/servicesNS/-/-/saved/searches`) | Needed to see scheduled searches and alerts owned by other users/apps (the collector always queries with the `-/-` wildcard, see D002/`docs/splunk-data-sources.md`). **[INFERENCE]** — `docs/splunk-data-sources.md` marks the exact capability (`list_settings`) as inferred from Splunk's standard permission model, not independently confirmed by this project. We cannot state with certainty that `list_settings` alone is sufficient or necessary in every Splunk version — if your test token can already read `_internal`/`_audit`, saved-search visibility is the next thing to check manually (does `audit --host ... ` show scheduled/alert datasets you know exist?). |

## Optional / currently not evaluated

These exist in the domain model but the REST collector never queries them
today — not a permissions gap, a feature gap. Granting more access here
has no effect on the current audit.

| Signal | Status |
|---|---|
| `dashboards_used` | Manual/CSV-only by design (D002) — REST mode always reports it as "not applicable," never queried. No Splunk permission is relevant yet. |
| `protected_overrides` | Same — manual text file input only, no REST equivalent implemented. |

## Failure behavior — what happens if a permission is missing

This is the part that makes a restricted token *safe* to test with,
not just convenient.

| Missing access | Result |
|---|---|
| `_internal` (mandatory) | `audit`/`quickscan` **abort** with a clear error (`RestCollectionError`) — the tool never produces a report built on a guess about total ingest volume. |
| `_audit`, with a **non-empty** result | N/A — any real row is unambiguous positive evidence, used directly. |
| `_audit`, with an **empty** result | The critical case D015 exists for. Splunk can return HTTP 200 with zero rows for two very different reasons: (a) the dataset genuinely has zero interactive searches, or (b) the token's role silently has no access to `_audit` at all (Splunk applies the index scope without any error). The collector runs a deterministic preflight (`_probe_index_access` in `rest_collector.py`) that reads the token's own effective role permissions (`/services/authorization/roles/...`, including inherited roles) to tell these apart — **before** trusting the empty result. If access truly cannot be confirmed, the signal is marked `UNAVAILABLE` with a specific reason shown to the user (never silently treated as "zero usage"). A dataset that would otherwise reach `POSSIBLE_WASTE` is downgraded to `REVIEW` instead, and is explicitly excluded from the potential-savings calculation (it cannot even carry `REVIEW`'s normal partial weight) — see `DECISIONS.md` D014/D015. **[VERIFIED against the real lab]**: with a restricted role lacking `_audit`, a dataset that is `HIGH_VALUE` with full access classifies as `REVIEW` (never `POSSIBLE_WASTE`) with the restricted token, and the CLI prints the reduced-confidence notice naming `_audit` specifically. |
| Saved searches unreadable/incomplete | Marked `ERROR`/`UNAVAILABLE` (never an empty-but-"confirmed" result); same D014 downgrade path as `_audit` applies — a dataset cannot reach `POSSIBLE_WASTE` on an unconfirmed zero. **Known residual limitation [documented, not fixed]:** unlike `_audit`, there is currently no deterministic preflight for saved-search visibility equivalent to D015's — an empty-but-actually-restricted result here is a theoretical risk of the same shape D015 fixed for `_audit`, not yet closed. Treat saved-search coverage as something to sanity-check manually with your tester, not as fully self-verifying yet. |
| `dashboards_used`/`protected_overrides` | Always "not applicable" in REST mode — never blocks anything, never described as "confirmed absent" in the report (see `DECISIONS.md` D018). |

## Example read-only role (conceptual — verify in your own environment)

Only the pieces below are backed by the evidence above; treat this as a
starting point for your Splunk Admin, not a copy-paste guarantee for
every Splunk version:

```
srchIndexesAllowed = _internal, _audit, <your normal data indexes...>
capabilities        = search
```

Everything else (exact saved-search visibility capability, any
Splunk-Cloud-specific role setting) should be confirmed by your Admin
against your own instance, per the `[INFERENCE]` notes above — this
project does not have verified evidence to state it more precisely today.

## Token / authentication

- Auth is **Bearer token only** — username/password is not supported by
  this CLI.
- Create the token from Splunk (Settings → Tokens), once "token
  authentication" is enabled on the instance, associated with a role that
  matches the table above.
- The CLI reads the token from the `SPLUNK_TOKEN` environment variable, or
  prompts for it interactively (hidden input via `getpass`) if that
  variable is not set and a terminal is available.
- The token is **never** accepted as a CLI argument, to avoid it landing
  in shell history, and is never written to disk or logged (verified: the
  token is referenced exactly once in `rest_collector.py`, only inside the
  `Authorization` header).
