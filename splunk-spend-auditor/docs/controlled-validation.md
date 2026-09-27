# Log Spend Auditor — Controlled Validation Guide

Thanks for helping test this. This is a practical guide, not marketing —
if something below is unclear or wrong once you actually run it, that
itself is useful feedback (see "What we want back").

## What Log Spend Auditor does

It reads your Splunk ingest volume (`license_usage.log`) and cross-references
it with real usage signals (interactive searches, scheduled searches,
alerts) to flag `(index, sourcetype)` datasets that ingest a lot of data
but show little or no observed usage — candidates worth a human review.

## What it does NOT do

- It does **not** delete, disable, or modify anything in Splunk.
- It does **not** guarantee savings — every number it produces is labeled
  as a *potential* estimate, never a promise.
- It does **not** send any data to a SaaS backend or external service.
- It does **not** use AI/ML to decide classifications — every rule is a
  plain, auditable threshold (see `docs/scoring.md`), never a black box.

## Privacy / local-first

Confirmed directly against the current code (not just claimed):

- The only network connections it makes are to the Splunk host/port *you*
  configure — nothing else. There is no telemetry, analytics, or
  "phone home" of any kind anywhere in the codebase.
- Your Splunk token is never written to disk and never logged — it's read
  from an environment variable or typed interactively (hidden), and used
  only in the request header.
- Everything the tool produces (`report.html`, `report.md`) is written
  only to the local output folder you choose. Nothing else is written to
  disk.
- The report shows aggregated counts (e.g. number of unique users), never
  raw search text or usernames, and never host/source values from your
  events.
- **One thing the report *does* show:** the hostname/port of the Splunk
  instance you pointed it at (e.g. "Splunk REST — splunk.company.internal:8089"),
  in the "Current Environment" section — so avoid sharing the report
  outside your team if that hostname itself is sensitive.

## Installation

```bash
git clone <repo> && cd splunk-spend-auditor
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Requires Python 3.10+. Validated on Linux; expected to work on macOS
(pure Python, no OS-specific code), not independently tested there or on
Windows.

Confirm it installed correctly:

```bash
splunk-spend-auditor --help
```

## Authentication / permissions

REST mode needs a Splunk token and a role with a specific, limited set of
permissions — **do not use an `admin` token for this test**. Ask your
Splunk Admin to read `docs/splunk-permissions.md` (Required/Recommended
tables) and provision a token accordingly. If you'd rather not touch
credentials at all, CSV mode (see `README.md`, "Modo CSV") needs no
Splunk access — you export a few queries manually instead.

## Quickscan (fast, terminal-only, no files written)

```bash
export SPLUNK_TOKEN=<your token>
splunk-spend-auditor quickscan --host <your-splunk-host> --port 8089
```

Add `--no-verify-ssl` only if your Splunk instance uses a self-signed or
otherwise untrusted certificate (a lab/internal instance, for example) —
TLS verification is on by default and should stay on against anything
else.

## Full audit (generates the HTML/Markdown report)

```bash
splunk-spend-auditor audit --host <your-splunk-host> --port 8089 \
    --output-dir ./output
```

## Optional annual spend

By default, the report only shows a **percentage** of ingest flagged as
optimization candidates — no dollar figure, because the tool has no idea
what you actually pay. If you want a dollar estimate, add:

```bash
splunk-spend-auditor audit --host <your-splunk-host> --port 8089 \
    --output-dir ./output --annual-spend <your real annual Splunk spend>
```

The report will clearly label that dollar figure as something *you*
provided, not something the tool measured or inferred.

## Outputs

`./output/report.html` and `./output/report.md` — open either one, they
contain the same information in different formats.

## Cleanup

`rm -rf ./output` (or whatever `--output-dir` you chose). That is the
*only* place this tool writes anything — there is no other local state,
cache, or config file to clean up.

## What we want back

- Could you install and run this **without asking us anything**? If not,
  where did you get stuck?
- Roughly how long did the whole thing take, start to finish?
- Any errors you hit (please paste them as they appeared).
- Did the Executive Summary make sense on its own, without more context
  from us?
- Do the classifications look reasonable for your environment, or does
  anything look clearly wrong?
- Is there a usage signal you wish it had checked but didn't?
- Which flagged candidate would you personally investigate first, and why?
- What information would you need to see before you'd actually act on one
  of these candidates?

We're not asking about pricing yet — just whether the tool is correct and
useful.
