"""MAP-Elites over linear scoring policies — birdNest.md §5 step 4, mocked
with the 7-weight linear scorer (policy.py) instead of a GNN.

python -m birdnest.train_qd --seed 0 --generations 60 --ckpt-every 10

BEHAVIOR DESCRIPTOR: (final_height, final_span) of the grown structure,
normalized by stick length, binned on a --grid x --grid lattice (values past
the range clamp into the edge bins). This is the HAND-STATS choice from
birdNest.md §6 — cheap and legible for the mockup; a learned embedding is
future work. Ranges below were eyeballed from the Phase-2 baseline batch.

FITNESS within a cell: (steps survived, tiebreak final score). Stability
stays a CONSTRAINT — episodes only ever place viable sticks — and fitness
deliberately does NOT reward height/size: diversity comes from the
descriptor, not the objective.

LOOP: init --pop random thetas, evaluate each on --eval-seeds fixed seed
structures (the SAME seeds every generation — paired comparison), insert
into the archive keeping the per-cell champion; each generation sample
elites uniformly, mutate (Gaussian --sigma), evaluate, insert.

DETERMINISM given --seed, regardless of worker scheduling (multiprocessing
only distributes independent episodes; every rng is keyed explicitly):
  seed structures    default_rng([seed, seed_idx])        (same as birdnest.run)
  theta init         default_rng([seed, 111111])
  evolution, gen g   default_rng([seed, 424242, g])       (parent pick + mutation)
  episode eval       default_rng([seed, gen, individual, eval_idx])
  showcase episodes  default_rng([seed, 777777, i, j])    (fixed showcase seed 0,
                     so an UNCHANGED elite re-rolls the IDENTICAL episode)

CHECKPOINTS (the watchable part): at gen 0, every --ckpt-every gens, and the
final gen, up to --ckpt-cells elites spread across the grid (farthest-point
sampling from the best cell, not just the densest corner) each re-roll one
episode with the fixed showcase seed, saved as ordinary schema-valid episode
JSONs under <out>/gen%04d/cell_<i>_<j>.json + manifest.json; <out>/run.json
(rewritten every checkpoint) carries config + coverage curve for the viewer.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .fem import Material, Params
from .improvise import run_episode
from .policy import FEATURE_NAMES, N_FEATURES, LinearPolicy
from .seeds import generate_seed, warn_stub_settle

# descriptor ranges in stick lengths (clamped into edge bins)
DESC_HEIGHT_MAX = 3.0
DESC_SPAN_MAX = 5.0


def cell_of(height: float, span: float, stick_len: float, grid: int) -> tuple[int, int]:
    """(row, col) = (height bin, span bin)."""
    i = int(np.clip(height / stick_len / DESC_HEIGHT_MAX * grid, 0, grid - 1))
    j = int(np.clip(span / stick_len / DESC_SPAN_MAX * grid, 0, grid - 1))
    return i, j


@dataclass
class Elite:
    theta: np.ndarray
    steps: float      # mean steps survived over the eval seeds
    score: float      # mean final score (tiebreak)
    height: float     # mean final height (m)
    span: float       # mean final span (m)
    gen: int
    ind_id: int

    @property
    def fitness(self) -> tuple[float, float]:
        return (self.steps, self.score)


class Archive:
    """MAP-Elites archive: per-cell champion by (steps, score)."""

    def __init__(self, grid: int):
        self.grid = grid
        self.cells: dict[tuple[int, int], Elite] = {}

    def insert(self, cell: tuple[int, int], elite: Elite) -> str | None:
        """Returns "new", "improved", or None (rejected)."""
        old = self.cells.get(cell)
        if old is None:
            self.cells[cell] = elite
            return "new"
        if elite.fitness > old.fitness:
            self.cells[cell] = elite
            return "improved"
        return None

    @property
    def coverage(self) -> float:
        return len(self.cells) / self.grid ** 2


def spread_cells(archive: Archive, k: int) -> list[tuple[int, int]]:
    """Up to k filled cells spread across the grid: start from the
    best-fitness cell, then greedy farthest-point sampling (deterministic,
    ties broken by cell coords)."""
    filled = sorted(archive.cells)
    if len(filled) <= k:
        return filled
    anchor = max(filled, key=lambda c: (archive.cells[c].fitness, c))
    chosen, rest = [anchor], [c for c in filled if c != anchor]
    while len(chosen) < k:
        best = max(rest, key=lambda c: (min((c[0] - d[0]) ** 2 + (c[1] - d[1]) ** 2
                                            for d in chosen), c))
        chosen.append(best)
        rest.remove(best)
    return sorted(chosen)


# ---------------------------------------------------------------------------
# worker side (top-level so spawn can pickle them)
# ---------------------------------------------------------------------------

_W: dict = {}  # per-worker state set by _init_worker


def _init_worker(master_seed: int, cfg: dict) -> None:
    import birdnest.seeds as seeds_mod
    seeds_mod._warned = True  # parent already printed the stub warning once
    material, params = Material(), Params()
    fixed = []
    for si in range(cfg["eval_seeds"]):
        rng = np.random.default_rng([master_seed, si])
        s, v, _ = generate_seed(
            rng, n_sticks=cfg["n_seed_sticks"], stick_len=cfg["stick_len"],
            radius=cfg["stick_radius"], dump_radius=cfg["dump_radius"],
            material=material, params=params)
        fixed.append((s, v))
    _W.update(master_seed=master_seed, cfg=cfg, seeds=fixed,
              material=material, params=params)


def _run_policy_episode(theta, rng, seed_idx: int, extra_meta: dict) -> dict:
    cfg = _W["cfg"]
    s, v = _W["seeds"][seed_idx]
    pol = LinearPolicy(np.asarray(theta), stick_len=cfg["stick_len"])
    return run_episode(
        s, v, pol, rng, steps=cfg["steps"], k_candidates=cfg["k"],
        stick_len=cfg["stick_len"], radius=cfg["stick_radius"],
        material=_W["material"], params=_W["params"], verbose=False,
        meta={"seed": _W["master_seed"], "env": cfg["env"], "stub_settled": True,
              "seed_index": seed_idx, "theta": [round(t, 6) for t in np.asarray(theta)],
              "feature_names": list(FEATURE_NAMES), **extra_meta})


def _eval_episode(job) -> tuple:
    gen, ind_id, eval_idx, theta = job
    rng = np.random.default_rng([_W["master_seed"], gen, ind_id, eval_idx])
    ep = _run_policy_episode(theta, rng, eval_idx, {"generation": gen, "individual": ind_id})
    r = ep["meta"]["result"]
    return (ind_id, eval_idx, r["steps_placed"], r["final_height"],
            r["final_span"], r["final_score"])


def _showcase_episode(job) -> tuple:
    gen, i, j, theta = job
    rng = np.random.default_rng([_W["master_seed"], 777777, i, j])
    ep = _run_policy_episode(theta, rng, _W["cfg"]["showcase_seed_idx"],
                             {"generation": gen, "cell": [i, j], "showcase": True})
    return (i, j, ep)


# ---------------------------------------------------------------------------
# parent side
# ---------------------------------------------------------------------------

def _evaluate(pool, gen: int, thetas: list, first_id: int, cfg: dict,
              archive: Archive) -> tuple[int, int]:
    """Evaluate a batch of thetas on all eval seeds; insert into archive.
    Returns (new_cells, improved_cells)."""
    jobs = [(gen, first_id + t, ei, theta.tolist())
            for t, theta in enumerate(thetas) for ei in range(cfg["eval_seeds"])]
    results = pool.map(_eval_episode, jobs)
    by_ind: dict[int, list] = {}
    for r in results:
        by_ind.setdefault(r[0], []).append(r)
    new = improved = 0
    for t, theta in enumerate(thetas):
        rs = by_ind[first_id + t]
        steps, height, span, score = (float(np.mean([r[c] for r in rs]))
                                      for c in (2, 3, 4, 5))
        elite = Elite(theta=theta, steps=steps, score=score, height=height,
                      span=span, gen=gen, ind_id=first_id + t)
        status = archive.insert(cell_of(height, span, cfg["stick_len"], archive.grid), elite)
        new += status == "new"
        improved += status == "improved"
    return new, improved


def _checkpoint(pool, archive: Archive, gen: int, out: Path, cfg: dict,
                curve: list, ckpt_gens: list) -> None:
    from .episode import save_episode

    cells = spread_cells(archive, cfg["ckpt_cells"])
    jobs = [(gen, i, j, archive.cells[(i, j)].theta.tolist()) for i, j in cells]
    episodes = pool.map(_showcase_episode, jobs)
    gen_dir = out / f"gen{gen:04d}"
    manifest = {
        "generation": gen,
        "coverage": round(archive.coverage, 4),
        "cells": [],
        # full archive state (no episodes) so the viewer can shade every cell
        "archive": [{"i": i, "j": j, "steps": round(e.steps, 2),
                     "score": round(e.score, 4), "height": round(e.height, 4),
                     "span": round(e.span, 4), "gen_discovered": e.gen}
                    for (i, j), e in sorted(archive.cells.items())],
    }
    for i, j, ep in episodes:
        fname = f"cell_{i}_{j}.json"
        save_episode(ep, gen_dir / fname)
        e = archive.cells[(i, j)]
        manifest["cells"].append({
            "i": i, "j": j, "height": round(e.height, 4), "span": round(e.span, 4),
            "steps": round(e.steps, 2), "score": round(e.score, 4),
            "gen_discovered": e.gen,
            "theta": [round(t, 4) for t in e.theta], "episode": fname})
    (gen_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))

    ckpt_gens.append(gen)
    run_info = {
        "schema": "birdnest-train/1",
        "config": dict(cfg),
        "feature_names": list(FEATURE_NAMES),
        "desc_ranges": {"height": DESC_HEIGHT_MAX, "span": DESC_SPAN_MAX},
        "generations": ckpt_gens,
        "coverage_curve": curve,
    }
    (out / "run.json").write_text(json.dumps(run_info, indent=1))
    print(f"  ckpt gen {gen}: {len(cells)} showcase episodes -> {gen_dir.name}/")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m birdnest.train_qd",
                                 description="MAP-Elites over linear scoring policies")
    ap.add_argument("--generations", type=int, default=60)
    ap.add_argument("--pop", type=int, default=32, help="initial random thetas (gen 0)")
    ap.add_argument("--batch", type=int, default=16, help="mutants per generation")
    ap.add_argument("--sigma", type=float, default=0.3, help="mutation stddev on theta")
    ap.add_argument("--grid", type=int, default=12)
    ap.add_argument("--eval-seeds", type=int, default=2,
                    help="fixed seed structures every individual is scored on")
    ap.add_argument("--steps", type=int, default=15,
                    help="growth steps (5 seed sticks + 15 = 20-stick budget)")
    ap.add_argument("--k", type=int, default=16, help="candidates per step")
    ap.add_argument("--n-seed-sticks", type=int, default=5)
    ap.add_argument("--stick-len", type=float, default=0.30)
    ap.add_argument("--stick-radius", type=float, default=0.004)
    ap.add_argument("--dump-radius", type=float, default=0.15)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--ckpt-every", type=int, default=10)
    ap.add_argument("--ckpt-cells", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None,
                    help="run dir (default runs/train-<stamp>)")
    args = ap.parse_args()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = args.out or Path(__file__).parent / "runs" / f"train-{stamp}"
    cfg = {
        "seed": args.seed, "generations": args.generations, "pop": args.pop,
        "batch": args.batch, "sigma": args.sigma, "grid": args.grid,
        "eval_seeds": args.eval_seeds, "steps": args.steps, "k": args.k,
        "n_seed_sticks": args.n_seed_sticks, "stick_len": args.stick_len,
        "stick_radius": args.stick_radius, "dump_radius": args.dump_radius,
        "ckpt_cells": args.ckpt_cells, "showcase_seed_idx": 0,
        "env": os.environ.get("CONDA_DEFAULT_ENV", "unknown"),
    }

    warn_stub_settle()
    n_ep = args.pop * args.eval_seeds + args.generations * args.batch * args.eval_seeds
    print(f"MAP-Elites: {args.grid}x{args.grid} grid over (height, span)/L, "
          f"fitness = (steps survived, final score)")
    print(f"plan: gen0 pop {args.pop} + {args.generations} gens x batch {args.batch}, "
          f"{args.eval_seeds} eval seeds -> {n_ep} eval episodes "
          f"({args.workers} workers); out: {out}")
    for si in range(args.eval_seeds):
        s, v, tries = generate_seed(
            np.random.default_rng([args.seed, si]), n_sticks=args.n_seed_sticks,
            stick_len=args.stick_len, radius=args.stick_radius,
            dump_radius=args.dump_radius)
        tag = " (showcase)" if si == cfg["showcase_seed_idx"] else ""
        print(f"eval seed {si}: {len(s.sticks)} sticks, {len(s.welds)} welds, "
              f"topple {v.margins['topple']:+.4f} m (dump {tries}){tag}")

    archive = Archive(args.grid)
    curve: list[dict] = []
    ckpt_gens: list[int] = []
    ind_counter = 0
    rng_init = np.random.default_rng([args.seed, 111111])
    t_run = time.perf_counter()

    with mp.Pool(args.workers, initializer=_init_worker,
                 initargs=(args.seed, cfg)) as pool:
        for gen in range(args.generations + 1):
            t0 = time.perf_counter()
            if gen == 0:
                thetas = [rng_init.normal(size=N_FEATURES) for _ in range(args.pop)]
            else:
                rng_evo = np.random.default_rng([args.seed, 424242, gen])
                elites = [archive.cells[c] for c in sorted(archive.cells)]
                thetas = [elites[int(rng_evo.integers(len(elites)))].theta
                          + rng_evo.normal(0.0, args.sigma, N_FEATURES)
                          for _ in range(args.batch)]

            new, improved = _evaluate(pool, gen, thetas, ind_counter, cfg, archive)
            ind_counter += len(thetas)
            dt = time.perf_counter() - t0
            best = max(e.fitness for e in archive.cells.values())
            curve.append({"gen": gen, "coverage": round(archive.coverage, 4),
                          "new_cells": new, "improved": improved,
                          "best_steps": round(best[0], 2), "sec": round(dt, 1)})
            print(f"gen {gen:3d}: coverage {archive.coverage:6.1%} "
                  f"({len(archive.cells)}/{args.grid ** 2}), +{new} new cells, "
                  f"{improved} improved, best steps {best[0]:.1f}, {dt:.1f}s")

            if gen == 0:
                per_ep = dt / (args.pop * args.eval_seeds)
                proj = per_ep * n_ep + 5.0 * (args.generations // args.ckpt_every + 2)
                print(f"  projected total ~{proj / 60:.1f} min "
                      f"({per_ep * 1e3:.0f} ms/episode incl. parallelism)")

            if gen % args.ckpt_every == 0 or gen == args.generations:
                _checkpoint(pool, archive, gen, out, cfg, curve, ckpt_gens)

    total = time.perf_counter() - t_run
    print(f"done in {total / 60:.1f} min: coverage {archive.coverage:.1%} "
          f"({len(archive.cells)}/{args.grid ** 2} cells), "
          f"{len(ckpt_gens)} checkpoints in {out}")


if __name__ == "__main__":
    main()
