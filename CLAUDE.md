# CLAUDE.md — Yuriatin project conventions

A fictional-ballet-critic publishing system. A Python backend owns a canon store
(SQLite) of an invented ballet world; an Astro renderer turns an exported
content collection into a static weekly column. This file is the contract for
anyone (human or model) working in this repo.

## The one hard rule

**Only creative prose comes from an LLM. Everything else is deterministic,
validated code.** Review bodies and forum replies are model-authored (stubbed
for now in `backend/engine/generators.py`). DB writes, frontmatter, slugs, git,
arc progression — all deterministic. Never move bookkeeping into a generator,
and never let a generator touch the DB.

## Canon invariants (enforced in code, re-checked by `check`)

1. **Never contradict a published verdict.** A published review's verdict is
   immutable canon. `review new` refuses a verdict that reverses a prior
   published verdict for the same house + work (rave/admiring ↔ cool/pan).
   `check` flags any contradiction that slips in.
2. **Every reviewed dancer must exist first.** You cannot cite a dancer that
   isn't already in the `dancers` table. `insert_review` validates each id.
3. **References must resolve.** No dangling company/work/dancer ids. FKs are ON;
   `check` runs `PRAGMA foreign_key_check`.
4. **The world cursor is singleton + monotonic.** Exactly one `world_state` row
   (id=1). `world advance` moves it forward one week, never back, and is
   idempotent (see below).
5. **A feud has a party on each side.** Checked on write and by `check`.

## Architecture

```
backend/                 Python, owns the canon
  engine/                the package (db, canon, world, generators, forum,
                         export, check, cli) — `python -m engine <cmd>`
  migrations/            numbered .sql + ledger-based runner
  canon.db               the SQLite store  (GENERATED — gitignored)
site/                    Astro static renderer (no JS islands yet)
  src/content/reviews/   exported Markdown  (COMMITTED — the published record)
scripts/weekly_tick.sh   the deterministic weekly run
.github/workflows/       check on PR, deploy to Pages on merge
persona_bible.md         the only creative-authority doc (future system prompts)
```

## CLI surface (all mutations; nothing else writes the DB)

| Command | What it does |
|---|---|
| `init` | apply migrations (incl. seed); build the DB |
| `world advance` | tick season/week forward (idempotent, transactional) |
| `world close` | finalize the current week (lets the next advance move on) |
| `world cursor` / `world show` | print the cursor (machine / human) |
| `review new` | pull past canon → stubbed generator → validate → write + export |
| `forum round` | stubbed persona replies for the week's reviews |
| `rep adjust ID N` | nudge a dancer's reputation; refuses an unknown id |
| `export` | project canon → Astro Markdown collection |
| `check` | integrity pass; **exits non-zero on failure** |

Global `--dry-run` generates + prints the diff and rolls back — mutates nothing.

## Idempotency of the weekly tick

The `ticks` ledger makes a double-fire or half-failure safe to re-run:
- a week with an **open** tick (`closed_at IS NULL`) is in progress; `world
  advance` just reports it instead of advancing again;
- only a **closed** week lets `advance` move the cursor forward;
- `review new` / `forum round` upsert by natural key, so re-running never dupes.

## Conventions

- Shell scripts target **bash** (`#!/usr/bin/env bash`, `set -euo pipefail`).
- Prefer **relative paths**; the CLI resolves DB/migration paths from the
  package location so it works from any cwd.
- Migrations are **forward-only**, numbered `NNNN_name.sql`, applied in order
  and recorded in `schema_migrations`. To change the schema, add a new file.
- Slugs are the stable id everywhere: review files are `<slug>.md`.
- See `README.md` for the committed-vs-generated boundary.
