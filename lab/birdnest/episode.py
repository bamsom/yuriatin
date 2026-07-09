"""Episode schema (FROZEN as birdnest-episode/1) + tiny validator + I/O.

One JSON per improvisation episode:

{
  "schema": "birdnest-episode/1",
  "meta": {
    "improviser": str,           # greedy_margin | greedy_height | random_valid | handmade
    "seed": int,                 # RNG seed that reproduces this episode exactly
    "env": str,                  # conda env the run used
    "stub_settled": bool,        # true => seed poses from the drop-and-project stub, not dynamics
    "candidate_sampling": str,   # states the aesthetic prior the candidate sampler smuggles in
    ...                          # free-form extras (n_seed_sticks, k_candidates, steps_requested, result)
  },
  "material": {"E", "G", "density", "sigma_y"},
  "params":   { fem.Params fields },
  "seed_sticks": [ {"p0":[x,y,z], "p1":[x,y,z], "radius": r}, ... ],
  "steps":    [ step0, step1, ... ]   # step0 = the frozen seed itself ("stick": null)
}

step = {
  "stick":       {"p0","p1","radius"} | null,   # the placed stick; null ONLY at step 0
  "weld_points": [[x,y,z], ...],                # welds created BY this placement (step 0: all seed welds)
  "members":     [ {"p0","p1","stick","axial_stress","buckling"}, ... ],
                 # FULL frame state after the placement — mesh members (stick
                 # segments between weld nodes), so the viewer can render and
                 # color the frame without re-running any mechanics.
  "margins":     {"topple","stress","buckling","deflection"},   # fem.viability margins
  "score":       float,
  "alive":       bool                            # all margins positive at this step
}

Coordinates are meters, z up, ground at z=0. Infinities are clamped to
+/-1e9 for JSON; floats rounded to 6 significant digits. Member counts are
non-decreasing across steps (sticks are only ever added), and the validator
enforces that.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

SCHEMA = "birdnest-episode/1"
_INF_CLAMP = 1e9
MARGIN_KEYS = ("topple", "stress", "buckling", "deflection")


def _num(x: float) -> float:
    x = float(x)
    if math.isnan(x):
        raise ValueError("NaN is not allowed in an episode")
    if math.isinf(x):
        return _INF_CLAMP if x > 0 else -_INF_CLAMP
    return float(f"{x:.6g}")


def _vec(p) -> list[float]:
    p = np.asarray(p, float)
    if p.shape != (3,):
        raise ValueError(f"expected 3-vector, got shape {p.shape}")
    return [_num(v) for v in p]


def stick_dict(stick) -> dict:
    return {"p0": _vec(stick.p0), "p1": _vec(stick.p1), "radius": _num(stick.radius)}


def step_from_viability(v, stick=None, weld_points=()) -> dict:
    """Build a step record from a fem.Viability (must be non-fatal: mesh+fem set)."""
    if v.mesh is None or v.fem is None:
        raise ValueError(f"cannot record a fatal viability ({v.reason}) as a step")
    members = []
    for i, m in enumerate(v.mesh.members):
        members.append({
            "p0": _vec(v.mesh.nodes[m.n1]),
            "p1": _vec(v.mesh.nodes[m.n2]),
            "stick": int(m.stick),
            "axial_stress": _num(v.fem.axial_stress[i]),
            "buckling": _num(v.fem.buckling[i]),
        })
    return {
        "stick": stick_dict(stick) if stick is not None else None,
        "weld_points": [_vec(p) for p in weld_points],
        "members": members,
        "margins": {k: _num(v.margins[k]) for k in MARGIN_KEYS},
        "score": _num(v.score),
        "alive": bool(v.ok),
    }


def new_episode(meta: dict, material, params, seed_sticks) -> dict:
    from dataclasses import asdict

    required = ("improviser", "seed", "env", "stub_settled", "candidate_sampling")
    missing = [k for k in required if k not in meta]
    if missing:
        raise ValueError(f"meta missing {missing}")
    return {
        "schema": SCHEMA,
        "meta": meta,
        "material": {k: _num(v) for k, v in asdict(material).items()},
        "params": {k: (None if v is None else _num(v)) for k, v in asdict(params).items()},
        "seed_sticks": [stick_dict(s) for s in seed_sticks],
        "steps": [],
    }


# ---------------------------------------------------------------------------
# validator
# ---------------------------------------------------------------------------

def _is_vec3(p) -> bool:
    return (isinstance(p, list) and len(p) == 3
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p))


def _is_stick(s) -> bool:
    return (isinstance(s, dict) and _is_vec3(s.get("p0")) and _is_vec3(s.get("p1"))
            and isinstance(s.get("radius"), (int, float)) and s["radius"] > 0)


def episode_errors(ep: dict) -> list[str]:
    """All schema problems found (empty list = valid)."""
    errs: list[str] = []
    if not isinstance(ep, dict):
        return ["episode is not an object"]
    if ep.get("schema") != SCHEMA:
        errs.append(f"schema is {ep.get('schema')!r}, expected {SCHEMA!r}")
    meta = ep.get("meta")
    if not isinstance(meta, dict):
        errs.append("meta missing")
    else:
        for k, t in (("improviser", str), ("seed", int), ("env", str),
                     ("stub_settled", bool), ("candidate_sampling", str)):
            if not isinstance(meta.get(k), t):
                errs.append(f"meta.{k} missing or not {t.__name__}")
    for k in ("E", "G", "density", "sigma_y"):
        if not isinstance(ep.get("material", {}).get(k), (int, float)):
            errs.append(f"material.{k} missing")
    if not isinstance(ep.get("params"), dict):
        errs.append("params missing")
    seeds = ep.get("seed_sticks")
    if not (isinstance(seeds, list) and seeds and all(_is_stick(s) for s in seeds)):
        errs.append("seed_sticks missing/empty/malformed")
    steps = ep.get("steps")
    if not (isinstance(steps, list) and steps):
        errs.append("steps missing or empty")
        return errs
    prev_members = 0
    for i, st in enumerate(steps):
        where = f"steps[{i}]"
        if not isinstance(st, dict):
            errs.append(f"{where} not an object")
            continue
        if i == 0:
            if st.get("stick") is not None:
                errs.append(f"{where}.stick must be null (step 0 is the seed)")
        elif not _is_stick(st.get("stick")):
            errs.append(f"{where}.stick missing or malformed")
        wp = st.get("weld_points")
        if not (isinstance(wp, list) and all(_is_vec3(p) for p in wp)):
            errs.append(f"{where}.weld_points malformed")
        members = st.get("members")
        if not (isinstance(members, list) and members):
            errs.append(f"{where}.members missing or empty")
        else:
            for j, m in enumerate(members):
                if not (isinstance(m, dict) and _is_vec3(m.get("p0")) and _is_vec3(m.get("p1"))
                        and isinstance(m.get("stick"), int)
                        and isinstance(m.get("axial_stress"), (int, float))
                        and isinstance(m.get("buckling"), (int, float))):
                    errs.append(f"{where}.members[{j}] malformed")
                    break
            if len(members) < prev_members:
                errs.append(f"{where}: member count decreased ({len(members)} < {prev_members})")
            prev_members = len(members)
        margins = st.get("margins")
        if not (isinstance(margins, dict) and set(margins) == set(MARGIN_KEYS)
                and all(isinstance(margins[k], (int, float)) for k in MARGIN_KEYS)):
            errs.append(f"{where}.margins must have exactly keys {MARGIN_KEYS}")
        if not isinstance(st.get("score"), (int, float)):
            errs.append(f"{where}.score missing")
        if not isinstance(st.get("alive"), bool):
            errs.append(f"{where}.alive missing")
    return errs


def validate_episode(ep: dict) -> None:
    """Raise ValueError listing every schema problem."""
    errs = episode_errors(ep)
    if errs:
        raise ValueError("invalid episode:\n  " + "\n  ".join(errs))


def save_episode(ep: dict, path: str | Path) -> Path:
    validate_episode(ep)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ep, indent=1))
    return path


def load_episode(path: str | Path) -> dict:
    ep = json.loads(Path(path).read_text())
    validate_episode(ep)
    return ep
