"""Re-roll a checkpoint's showcase elites on a DIFFERENT seed accident —
no retraining. The checkpoint manifests store each elite's theta, so the
linear policies can be reconstructed and replayed on any seed:

  python -m birdnest.showcase --run runs/train-<stamp> --gen 60 \\
      --showcase-seed 7 [--cells 12] [--steps 15]

Reads <run>/run.json (training config) + <run>/gen%04d/manifest.json,
generates a NEW seed structure from --showcase-seed via the same
generate_seed path and acceptance band the training run used, re-rolls one
episode per listed cell, and writes <run>/gen%04d-seed<k>/ — episodes plus a
manifest.json in the same format, with "showcase_seed" recorded. The viewer
picks these folders up as a "seed" selector next to the generation slider.

NOTE: cells are indexed by the elites' behavior on the ORIGINAL showcase
seed. On a new seed the same theta may land elsewhere in behavior space —
that drift is part of what this tool is for. The output manifest records the
ACTUAL (height, span, steps, score) achieved on the new seed, while (i, j)
keep naming the archive cell each elite came from. The archive block is
carried over unchanged (it is a property of training, not of the seed).

Deterministic given the flags:
  seed structure  default_rng([config.seed, showcase_seed])   — the training
                  eval-seed path, so --showcase-seed 0/1 rebuild eval seeds 0/1
  episodes        default_rng([config.seed, 777777, showcase_seed, i, j])
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .episode import save_episode
from .fem import Material, Params
from .improvise import run_episode
from .policy import LinearPolicy
from .seeds import generate_seed


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m birdnest.showcase",
                                 description="re-roll checkpoint elites on a new seed")
    ap.add_argument("--run", type=Path, required=True,
                    help="training run dir (contains run.json)")
    ap.add_argument("--gen", type=int, required=True, help="checkpointed generation")
    ap.add_argument("--showcase-seed", type=int, required=True,
                    help="index of the new seed accident")
    ap.add_argument("--cells", type=int, default=12, help="max cells to re-roll")
    ap.add_argument("--steps", type=int, default=None,
                    help="growth steps (default: training config)")
    args = ap.parse_args()

    run_dir = args.run
    if not (run_dir / "run.json").exists():  # allow paths relative to birdnest/
        run_dir = Path(__file__).parent / args.run
    info = json.loads((run_dir / "run.json").read_text())
    cfg = info["config"]
    gen_name = f"gen{args.gen:04d}"
    manifest_in = json.loads((run_dir / gen_name / "manifest.json").read_text())
    cells = manifest_in["cells"][: args.cells]
    steps = args.steps if args.steps is not None else cfg["steps"]

    material, params = Material(), Params()
    structure, v_seed, tries = generate_seed(
        np.random.default_rng([cfg["seed"], args.showcase_seed]),
        n_sticks=cfg["n_seed_sticks"], stick_len=cfg["stick_len"],
        radius=cfg["stick_radius"], dump_radius=cfg["dump_radius"],
        material=material, params=params)
    print(f"showcase seed {args.showcase_seed}: {len(structure.sticks)} sticks, "
          f"{len(structure.welds)} welds, topple {v_seed.margins['topple']:+.4f} m "
          f"(accepted on dump {tries})")
    print(f"re-rolling {len(cells)} elites from {run_dir.name}/{gen_name} "
          f"({steps} steps, K={cfg['k']})")

    out = run_dir / f"{gen_name}-seed{args.showcase_seed}"
    manifest_out = {
        "generation": manifest_in["generation"],
        "coverage": manifest_in["coverage"],
        "showcase_seed": args.showcase_seed,
        "cells": [],
        "archive": manifest_in.get("archive", []),
    }
    for c in cells:
        i, j = c["i"], c["j"]
        theta = np.asarray(c["theta"], float)
        rng = np.random.default_rng([cfg["seed"], 777777, args.showcase_seed, i, j])
        ep = run_episode(
            structure, v_seed, LinearPolicy(theta, stick_len=cfg["stick_len"]),
            rng, steps=steps, k_candidates=cfg["k"], stick_len=cfg["stick_len"],
            radius=cfg["stick_radius"], material=material, params=params,
            verbose=False,
            meta={"seed": cfg["seed"], "env": cfg.get("env", "unknown"),
                  "stub_settled": True, "showcase": True,
                  "showcase_seed": args.showcase_seed, "generation": args.gen,
                  "cell": [i, j], "theta": [round(float(t), 6) for t in theta]})
        r = ep["meta"]["result"]
        fname = f"cell_{i}_{j}.json"
        save_episode(ep, out / fname)
        manifest_out["cells"].append({
            "i": i, "j": j,
            "height": r["final_height"], "span": r["final_span"],
            "steps": r["steps_placed"], "score": r["final_score"],
            "gen_discovered": c.get("gen_discovered"),
            "theta": c["theta"], "episode": fname})
        print(f"  cell ({i:2d},{j:2d}): {r['steps_placed']:2d}/{steps} steps, "
              f"height {r['final_height']:.3f}, span {r['final_span']:.3f}")
    (out / "manifest.json").write_text(json.dumps(manifest_out, indent=1))
    print(f"wrote {len(manifest_out['cells'])} episodes + manifest.json -> {out}")


if __name__ == "__main__":
    main()
