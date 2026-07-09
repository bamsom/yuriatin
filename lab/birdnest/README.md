# birdnest — lab mockup

Improvisational structure growth over a welded-frame FEM. Design note:
[birdNest.md](birdNest.md). This is a **lab experiment attached to the yuriatin
blog project** — it is NOT part of the publishing pipeline. Nothing here may
import from or write into `backend/` or `site/`, and the Astro build never
sees this directory (the site build is rooted entirely in `site/`; CI runs
with `working-directory: site` and publishes `site/dist`).

Scope of the mockup: build-path steps 1–3 of the design note plus a web
viewer, and a **step-4-lite QD loop**: MAP-Elites over linear scoring
policies (no torch, no GNN — the policy is a 7-weight linear scorer over
hand features; see below).

## What is real vs stubbed

| Piece | Status |
|---|---|
| Frame FEM (direct stiffness, 3D Euler-Bernoulli members, welded joints) | **real**, validated against closed-form beam/column results |
| Toppling margin (COM vs support polygon, per welded component) | **real** (rigid-body, quasi-static) |
| Euler buckling check | **real** but per-member with effective-length factor K=1 (conservative convention, not a global eigenvalue analysis) |
| Seed settling (Phase 2) | **stub** unless pybullet is present — drop along −z, project to first contact, jitter; runs print a warning when seeds are stub-settled |

Documented idealizations (see module docstrings): weld nodes sit at the
midpoint between touching centerlines (small kink ≤ one radius); one weld per
stick pair; ground contact is unilateral rest — clamped in the FEM, with
toppling checked separately as a rigid-body margin.

## Environment

Reuses the existing conda env **`styleDraw`** (python 3.11, numpy, scipy,
pytest — nothing new installed). No pybullet in any env on this machine, so
Phase 2 seeds are stub-settled.

```bash
conda activate styleDraw    # or prefix commands with: conda run -n styleDraw
```

## Run

From `lab/` (one level above this directory):

```bash
# unit tests
conda run -n styleDraw python -m pytest birdnest/tests -q

# numeric sanity table for the hand-built cases
conda run -n styleDraw python -m birdnest.sanity

# regenerate the committed demo episode
conda run -n styleDraw python -m birdnest.make_demo

# improviser baselines (deterministic given --seed); --dry-run prints the plan
conda run -n styleDraw python -m birdnest.run --improviser all \
  --n-seeds 3 --steps 40 --seed 0 --out birdnest/runs/batch-s0

# MAP-Elites training run (deterministic given --seed; multiprocessing)
conda run -n styleDraw python -m birdnest.train_qd \
  --seed 0 --generations 60 --ckpt-every 10

# re-roll a checkpoint's elites on a DIFFERENT seed accident (no retraining)
conda run -n styleDraw python -m birdnest.showcase \
  --run birdnest/runs/train-<stamp> --gen 60 --showcase-seed 7

# viewer: MUST be served from lab/birdnest (so runs/ is reachable) — then open
#   http://127.0.0.1:8765/viewer/viewer.html
birdnest/serve.sh            # = cd birdnest && python3 -m http.server 8765
```

The viewer auto-opens the **latest training run at its latest generation**
and replays one showcase elite immediately; the 3-step demo loads only when
no runs are served (with a visible hint saying to serve from lab/birdnest),
and any episode JSON — demo included — can be loaded via the file picker
(top right). Space = play/pause, arrows = step; the HUD shows a stick
counter (`sticks N/M`, ending at 20/20 for a full-budget episode). In the
training panel: pick a run, scrub the generation slider, and the archive is
drawn as a grid (height ↑, span →, cells shaded by steps survived). Outlined
cells have a checkpointed showcase episode — click to replay it with the
usual playback and stress colors. If `birdnest.showcase` re-rolls exist
(`gen%04d-seed<k>/` folders), a **seed** dropdown appears — switching seeds
replays the same elites on a different starting accident.

## Episode schema

`birdnest-episode/1`, defined + validated in `episode.py`. Step 0 is the
frozen seed; each later step records the placed stick, the welds it created,
the full member list with per-member axial stress + buckling factor (the
viewer re-runs no mechanics), the four margins, score, and `alive`.
`meta.candidate_sampling` states the sampler prior in every file: candidates
are uniform over the reachable surface, which is itself an aesthetic prior —
baseline forms, not "emergent" ones.

## Seeds and improvisers

Seeds: dump N sticks, stub-settle (see table above), weld all contacts,
freeze, then accept/reject on the seed's toppling margin band
(`--margin-lo/--margin-hi`; narrow band near zero = "barely stands").
Improvisers are scripted rules over the same K evaluated candidates per step:
`greedy_margin` (max worst-margin score), `greedy_height` (max height among
viable), `random_valid` (uniform among viable). An episode ends after
`--steps` placements or when no sampled candidate is viable.

## QD training loop (`train_qd.py` + `policy.py`)

A policy is a weight vector θ ∈ R⁷ over per-candidate features (resulting
score, Δheight, Δspan, new welds, new-stick midpoint height, horizontal
distance of the added mass from the COM, bias — documented in `policy.py`;
lengths normalized by stick length). Among the K viable candidates it places
argmax θ·f. θ = 0 degenerates to `random_valid` (exact ties break uniformly
at random) — the sanity anchor.

MAP-Elites (`train_qd.py` docstring has the full determinism scheme):
behavior descriptor = (final height, final span)/stick length on a 12×12
grid — the hand-stats choice; a learned embedding is future work
(birdNest.md §6). Fitness within a cell = steps survived, tiebreak final
score; stability stays a **constraint** and fitness deliberately does not
reward height/size — diversity comes from the descriptor. Budget: 5 seed
sticks + 15 growth steps = 20 sticks, K=16. Episodes fan out over a
`multiprocessing.Pool`; every rng is keyed explicitly, so runs are
deterministic given `--seed` regardless of worker scheduling.

Checkpoints (the watchable part): at gen 0, every `--ckpt-every`, and the
final gen, up to `--ckpt-cells` elites spread across the grid each re-roll
one episode on a fixed showcase seed with a fixed rng — ordinary
schema-valid episode JSONs under `runs/train-<stamp>/gen%04d/` plus
`manifest.json` (showcase cells + full archive) and a run-level `run.json`
(config + coverage curve). An UNCHANGED elite re-rolls the identical
episode, so differences between checkpoints are real policy changes.

## Layout

```
birdnest/
  birdNest.md      the design note (decisions of record)
  fem/             Phase 1: model, solver, stability, viability/score
  cases.py         hand-built benchmark structures (tests + sanity share these)
  tests/           pytest suite pinning solver to analytic results + expected
                   orderings (tripod > cantilever > toppler) + QD-layer gates
  sanity.py        python -m birdnest.sanity — margin table
  policy.py        linear scorer over candidate features (theta in R^7)
  train_qd.py      MAP-Elites loop + checkpoints (python -m birdnest.train_qd)
  showcase.py      re-roll checkpoint elites on a new seed (python -m birdnest.showcase)
  serve.sh         one-liner: serve viewer + runs on 127.0.0.1:8765
  runs/            episode + training-run outputs (gitignored)
  viewer/          standalone Three.js episode viewer + training-run browser
```

## Reward semantics (birdNest.md §3)

`viability(structure) -> Viability(ok, margins, score, ...)` — stability is a
**constraint**: `ok` means every margin is positive (`topple`, `stress`,
`buckling`, `deflection`). `score` is the worst normalized margin, a
robustness scalar for choosing among viable placements. There are **no
canonical shape targets** anywhere in the reward; shape preferences (e.g.
greedy-by-height) live only in the scripted improvisers.
