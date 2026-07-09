"""Build the committed hand-made demo episode: python -m birdnest.make_demo

Poses are hand-chosen (no sampling, no settling); mechanics are the real
Phase-1 FEM. Narrative in three placements over a tripod seed:
  1. a horizontal arm off the apex   -> toppling margin drops, root bending
  2. a brace from arm tip to ground  -> margin recovers, support polygon grows
  3. a rung across two legs          -> stresses redistribute, frame stiffens
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .episode import new_episode, save_episode, step_from_viability
from .fem import Material, Params, Structure, viability

OUT = Path(__file__).parent / "viewer" / "demo_episode.json"


def main() -> None:
    params = Params()
    material = Material()
    s = Structure(params)

    # seed: tripod (hand-made stand-in for a settled dump)
    apex = (0.0, 0.0, 0.25)
    for ang_deg in (90.0, 210.0, 330.0):
        a = np.deg2rad(ang_deg)
        s.add_stick((0.12 * np.cos(a), 0.12 * np.sin(a), 0.0), apex)

    ep = new_episode(
        meta={
            "improviser": "handmade",
            "seed": 0,
            "env": "styleDraw",
            "stub_settled": False,
            "candidate_sampling": "handmade poses (demo episode; nothing sampled)",
            "note": "tripod seed + arm + brace + rung; real FEM numbers",
        },
        material=material, params=params, seed_sticks=list(s.sticks),
    )

    v = viability(s, material, params)
    ep["steps"].append(step_from_viability(v, stick=None,
                                           weld_points=[w.point for w in s.welds]))

    placements = [
        ((0.0, 0.0, 0.25), (0.25, 0.0, 0.25)),      # arm off the apex
        ((0.25, 0.0, 0.25), (0.40, 0.0, 0.0)),      # brace: arm tip -> ground
        ((-0.08, -0.03, 0.125), (0.08, -0.03, 0.125)),  # rung across two legs
    ]
    for p0, p1 in placements:
        n_welds_before = len(s.welds)
        idx = s.add_stick(p0, p1)
        new_welds = [w.point for w in s.welds[n_welds_before:]]
        v = viability(s, material, params)
        ep["steps"].append(step_from_viability(v, stick=s.sticks[idx],
                                               weld_points=new_welds))

    path = save_episode(ep, OUT)
    sizes = [len(st["members"]) for st in ep["steps"]]
    print(f"wrote {path} ({path.stat().st_size} bytes)")
    print(f"steps: {len(ep['steps'])} (incl. seed), members per step: {sizes}")
    for i, st in enumerate(ep["steps"]):
        m = st["margins"]
        print(f"  step {i}: topple={m['topple']:+.4f}  score={st['score']:+.3f}  "
              f"alive={st['alive']}  welds+{len(st['weld_points'])}")


if __name__ == "__main__":
    main()
