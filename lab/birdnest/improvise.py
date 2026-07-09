"""Scripted improviser baselines: greedy-by-margin, greedy-by-height,
random-valid. No learning anywhere.

Each step samples K candidate next-stick poses TOUCHING the current
structure, evaluates every candidate with the Phase-1 viability(), places one
per its rule, and records the full frame state. Runs T steps or stops when no
sampled candidate is viable.

CANDIDATE SAMPLING PRIOR (stated honestly, stamped into meta): candidates are
uniform over the reachable surface — anchor stick ~ U(sticks), position along
it ~ U(0,1), contact azimuth ~ U(circle), new-stick direction ~ U(sphere),
contact parameter along the new stick ~ U(0,1); candidates dipping below the
ground plane are rejected. Uniformity is itself an aesthetic prior (it never
proposes ground-touching props, for one), so the resulting forms are
BASELINES, not "emergent" shapes.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from .episode import new_episode, step_from_viability
from .fem import Material, Params, Structure, Viability, viability

IMPROVISERS = ("greedy_margin", "greedy_height", "random_valid")

CANDIDATE_SAMPLING_NOTE = (
    "uniform over reachable surface: anchor stick ~ U(sticks), t ~ U(0,1), "
    "contact azimuth ~ U(circle), direction ~ U(sphere), contact param ~ U(0,1); "
    "below-ground candidates rejected. This sampler is an aesthetic prior - "
    "forms are baselines, not emergent."
)


def sample_candidate(rng: np.random.Generator, structure: Structure,
                     stick_len: float, radius: float):
    """One candidate pose touching a random point on the structure's surface,
    or None if it would dip below the ground plane."""
    anchor = structure.sticks[int(rng.integers(len(structure.sticks)))]
    t = rng.uniform()
    axis = (anchor.p1 - anchor.p0) / anchor.length
    ref = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.99 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(ref, axis)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis, e1)
    phi = rng.uniform(0, 2 * np.pi)
    n = np.cos(phi) * e1 + np.sin(phi) * e2
    q = anchor.point(t) + n * (anchor.radius + radius)  # point on combined surface

    while True:
        d = rng.normal(size=3)
        dn = np.linalg.norm(d)
        if dn > 1e-9:
            d /= dn
            break
    t_new = rng.uniform()
    p0 = q - t_new * stick_len * d
    p1 = p0 + stick_len * d
    if min(p0[2], p1[2]) < -1e-9:
        return None
    return p0, p1


def _rejection_key(v: Viability, char_len: float) -> str:
    if v.fem is None:
        return "fatal:" + (v.reason or "unknown")
    normalized = {
        "topple": v.margins["topple"] / char_len,
        "stress": v.margins["stress"],
        "buckling": v.margins["buckling"],
        "deflection": v.margins["deflection"],
    }
    return min(normalized, key=normalized.get)


def run_episode(
    seed_structure: Structure,
    seed_viability: Viability,
    improviser: str,
    rng: np.random.Generator,
    steps: int = 40,
    k_candidates: int = 24,
    stick_len: float = 0.30,
    radius: float = 0.004,
    material: Material | None = None,
    params: Params | None = None,
    meta: dict | None = None,
    verbose: bool = True,
) -> dict:
    """Grow from a frozen seed; returns a schema-valid episode dict.

    `improviser` is either a name from IMPROVISERS or a callable
    pick(structure, viable, rng) -> chosen viable entry (e.g. a
    policy.LinearPolicy), where `structure` is the PRE-placement structure
    and `viable` the list of (s2, idx, viability, new_weld_points) tuples.
    """
    if callable(improviser):
        imp_name = getattr(improviser, "name", improviser.__class__.__name__)
    elif improviser in IMPROVISERS:
        imp_name = improviser
    else:
        raise ValueError(f"unknown improviser {improviser!r}; choose from {IMPROVISERS}")
    material = material or Material()
    params = params or seed_structure.params

    ep = new_episode(
        meta={
            "improviser": imp_name,
            "candidate_sampling": CANDIDATE_SAMPLING_NOTE,
            "k_candidates": k_candidates,
            "steps_requested": steps,
            **(meta or {}),
        },
        material=material, params=params, seed_sticks=list(seed_structure.sticks),
    )
    ep["steps"].append(step_from_viability(
        seed_viability, stick=None,
        weld_points=[w.point for w in seed_structure.welds]))

    structure = seed_structure.copy()
    rejections: Counter[str] = Counter()
    terminated = "steps_exhausted"
    last_v = seed_viability

    for step_i in range(1, steps + 1):
        viable: list[tuple[Structure, int, Viability, list]] = []
        char_len = structure.mean_stick_length()
        # K counts candidates that reach FEM evaluation; purely geometric
        # rejects (below ground) cost only a draw, capped to stay finite
        evaluated, draws = 0, 0
        while evaluated < k_candidates and draws < 25 * k_candidates:
            draws += 1
            cand = sample_candidate(rng, structure, stick_len, radius)
            if cand is None:
                rejections["below_ground"] += 1
                continue
            evaluated += 1
            p0, p1 = cand
            s2 = structure.copy()
            n_welds_before = len(s2.welds)
            idx = s2.add_stick(p0, p1, radius)
            v = viability(s2, material, params)
            if v.ok:
                viable.append((s2, idx, v, [w.point for w in s2.welds[n_welds_before:]]))
            else:
                rejections[_rejection_key(v, char_len)] += 1

        if not viable:
            terminated = "no_viable_candidate"
            if verbose:
                print(f"    step {step_i}: STUCK — all {k_candidates} candidates rejected")
            break

        if callable(improviser):
            pick = improviser(structure, viable, rng)
        elif improviser == "greedy_margin":
            pick = max(viable, key=lambda c: c[2].score)
        elif improviser == "greedy_height":
            pick = max(viable, key=lambda c: (c[0].height(), c[2].score))
        else:  # random_valid
            pick = viable[int(rng.integers(len(viable)))]

        structure, idx, last_v, new_welds = pick
        ep["steps"].append(step_from_viability(last_v, stick=structure.sticks[idx],
                                               weld_points=new_welds))
        if verbose and (step_i % 10 == 0 or step_i == steps):
            print(f"    step {step_i}: {len(viable)}/{k_candidates} viable, "
                  f"score {last_v.score:+.3f}, height {structure.height():.3f}")

    ep["meta"]["result"] = {
        "terminated": terminated,
        "steps_placed": len(ep["steps"]) - 1,
        "final_height": round(structure.height(), 4),
        "final_span": round(structure.span(), 4),
        "final_score": round(last_v.score, 4),
        "rejections": dict(rejections.most_common()),
    }
    return ep
