"""Batch runner: python -m birdnest.run --improviser greedy_margin --n-seeds 3
--steps 40 --seed 0 --out runs/batch0 [--dry-run]

Deterministic given --seed: seed structures come from rng [seed, seed_idx]
(so every improviser grows the SAME seeds — comparable), improviser choices
from rng [seed, seed_idx, improviser_id].
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np

from .episode import save_episode
from .fem import Material, Params
from .improvise import IMPROVISERS, run_episode
from .seeds import generate_seed


def summarize(paths: list[Path]) -> None:
    from .episode import load_episode

    header = (f"{'episode':<28} {'steps':>5} {'height':>7} {'span':>7} "
              f"{'score':>7}  {'terminated':<20} top rejection")
    print("\n" + header)
    print("-" * len(header))
    for p in sorted(paths):
        ep = load_episode(p)
        r = ep["meta"].get("result", {})
        rej = r.get("rejections", {})
        top = max(rej, key=rej.get) + f" x{max(rej.values())}" if rej else "-"
        print(f"{p.stem:<28} {r.get('steps_placed', '?'):>5} "
              f"{r.get('final_height', float('nan')):>7.3f} "
              f"{r.get('final_span', float('nan')):>7.3f} "
              f"{r.get('final_score', float('nan')):>7.3f}  "
              f"{r.get('terminated', '?'):<20} {top}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m birdnest.run",
                                 description="scripted improviser baselines")
    ap.add_argument("--improviser", default="all", choices=[*IMPROVISERS, "all"])
    ap.add_argument("--n-seeds", type=int, default=3, help="episodes per improviser")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--k-candidates", type=int, default=24)
    ap.add_argument("--n-seed-sticks", type=int, default=5)
    ap.add_argument("--stick-len", type=float, default=0.30)
    ap.add_argument("--stick-radius", type=float, default=0.004)
    ap.add_argument("--dump-radius", type=float, default=0.15)
    ap.add_argument("--margin-lo", type=float, default=0.0,
                    help="seed accept band: min toppling margin (m)")
    ap.add_argument("--margin-hi", type=float, default=np.inf,
                    help="seed accept band: max toppling margin (m)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None,
                    help="output dir (default runs/batch-s<seed>)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan, write nothing")
    args = ap.parse_args()

    improvisers = list(IMPROVISERS) if args.improviser == "all" else [args.improviser]
    out = args.out or Path(__file__).parent / "runs" / f"batch-s{args.seed}"
    plan = [(imp, si, out / f"{imp}_s{si}.json")
            for si in range(args.n_seeds) for imp in improvisers]

    print(f"plan: {len(plan)} episodes = {len(improvisers)} improviser(s) x "
          f"{args.n_seeds} seed(s); T={args.steps}, K={args.k_candidates}, "
          f"N={args.n_seed_sticks} seed sticks, "
          f"toppling band [{args.margin_lo}, {args.margin_hi}]")
    for imp, si, path in plan:
        print(f"  {imp:<15} seed_idx {si} -> {path}")
    if args.dry_run:
        print("dry run: nothing written.")
        return

    material, params = Material(), Params()
    env = os.environ.get("CONDA_DEFAULT_ENV", "unknown")
    written: list[Path] = []
    for si in range(args.n_seeds):
        rng_seed = np.random.default_rng([args.seed, si])
        structure, v_seed, tries = generate_seed(
            rng_seed, n_sticks=args.n_seed_sticks, stick_len=args.stick_len,
            radius=args.stick_radius, dump_radius=args.dump_radius,
            margin_band=(args.margin_lo, args.margin_hi),
            material=material, params=params)
        print(f"seed {si}: {len(structure.sticks)} sticks, "
              f"{len(structure.welds)} welds, topple {v_seed.margins['topple']:+.4f} m "
              f"(accepted on dump {tries})")
        for imp in improvisers:
            imp_id = IMPROVISERS.index(imp)
            rng_imp = np.random.default_rng([args.seed, si, imp_id])
            print(f"  {imp} (seed_idx {si}):")
            ep = run_episode(
                structure, v_seed, imp, rng_imp,
                steps=args.steps, k_candidates=args.k_candidates,
                stick_len=args.stick_len, radius=args.stick_radius,
                material=material, params=params,
                meta={"seed": args.seed, "seed_index": si, "env": env,
                      "stub_settled": True,
                      "n_seed_sticks": args.n_seed_sticks})
            path = save_episode(ep, out / f"{imp}_s{si}.json")
            written.append(path)
            r = ep["meta"]["result"]
            print(f"    -> {path.name}: {r['steps_placed']}/{args.steps} steps, "
                  f"height {r['final_height']:.3f}, {r['terminated']}")

    summarize(written)


if __name__ == "__main__":
    main()
