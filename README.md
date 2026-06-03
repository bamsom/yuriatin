# Yuriatin

A fictional-ballet-critic publishing system. A Python backend owns a **canon
store** (SQLite) of an invented ballet world — companies, dancers, works,
reviews, feuds, and a season arc. An Astro renderer turns an **exported content
collection** (Markdown + typed frontmatter) into a static weekly column with an
RSS feed.

Two layers, deliberately decoupled:

1. **Backend (`backend/`)** — Python + Typer. Every state change goes through a
   validated CLI; nothing else touches the DB.
2. **Renderer (`site/`)** — Astro, static-first, no JS islands yet.

> The **only** content that comes from an LLM is creative prose (review text,
> forum replies), and it is **stubbed** in this phase — no Anthropic API is
> wired up yet. Everything else is deterministic, validated code. See
> `CLAUDE.md` for the project contract and canon invariants.

## Quick start (local)

```bash
# 1. Backend: venv + deps
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# 2. Build the canon DB (runs migrations + seed)
( cd backend && .venv/bin/python -m engine init )

# 3. See the world, dry-run a full tick (mutates nothing), then check
( cd backend && .venv/bin/python -m engine world show )
scripts/weekly_tick.sh --dry-run
( cd backend && .venv/bin/python -m engine check )

# 4. Renderer: install + build the static site
( cd site && npm install && npm run build )
# preview at http://localhost:4321/yuriatin
( cd site && npm run preview )
```

Run the whole weekly pipeline locally without git:

```bash
scripts/weekly_tick.sh --no-git
```

## Committed vs. generated boundary

**Commit only source.** The boundary (enforced by `.gitignore`):

| Committed (source) | Generated / excluded |
|---|---|
| `backend/engine/**`, `backend/migrations/**` | `backend/canon.db` and WAL/SHM (the SQLite store) |
| `site/src/**`, `site/package.json`, `package-lock.json` | `site/dist/`, `.astro/`, `node_modules/` |
| `site/src/content/reviews/*.md` (the **published record**) | `__pycache__/`, `backend/.venv/` |
| `persona_bible.md`, `scripts/`, `.github/`, docs | `.env`, `.DS_Store`, logs |

Why the **DB is not committed**: it's a binary, and it's regenerable from
`migrations/` (schema **and** seed). The durable, shareable published artifact is
the **Markdown export**, which *is* committed. On a fresh clone, `engine init`
rebuilds the DB from the seed (including the one example past review, so
continuity is demonstrable); week-to-week DB state lives on the machine that runs
the weekly tick.

> **Phase-1 limitation, documented honestly:** because the DB isn't committed,
> the PR `check` workflow runs against a *freshly seeded* DB — it validates the
> engine + seed canon, while the Astro build validates every committed review's
> frontmatter via the zod schema. Together they guard the committed source. The
> planned upgrade is to also commit a deterministic canon SQL dump so CI `check`
> can validate the *full* live canon, not just the seed.

## The weekly tick

`scripts/weekly_tick.sh` is deterministic (NOT LLM-driven):

```
world advance → review new → forum round → export → check (abort on fail)
  → world close → astro build → git branch (week-YYYY-WW) → commit SOURCE
  → push → gh PR
```

`main` is never committed to directly — the PR is the human review gate. The tick
is idempotent: a double-fire or half-failure is safe to re-run (see `CLAUDE.md`).

## Deploy (GitHub Pages, project site)

- `astro.config.mjs` sets `base: '/yuriatin'` for a project site at
  `https://<user>.github.io/yuriatin/`. **Replace the placeholder `site` host**
  with your GitHub username (CI injects it automatically from the repo owner).
- `.github/workflows/deploy.yml` builds + deploys to Pages on merge to `main`.
- `.github/workflows/check.yml` runs `check` + an Astro build on every PR.
