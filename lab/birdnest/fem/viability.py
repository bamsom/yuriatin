"""The reward interface: viability (constraint) and score (robustness scalar).

Per birdNest.md §3: stability is a CONSTRAINT — a structure is viable when
every margin is positive — never a shape objective. score() is the worst
normalized margin, i.e. a robustness scalar that improvisers may use to pick
among viable placements; shape drives (height, novelty) live in the
improvisers, not here.

Margins (raw units in the dict):
    topple      meters of COM clearance inside the support polygon
    stress      1 - max(combined stress) / sigma_y
    buckling    min Euler factor / buckling_safety - 1  (inf if nothing compressed)
    deflection  1 - max nodal translation / (deflect_limit_frac * mean stick length)

score() normalizes topple by the mean stick length so all margins are
dimensionless, caps each at ±score_cap, and returns the minimum. Fatal
conditions (no ground contact, floating component, mechanism) score
-score_cap with margins set to -inf and a reason string.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .model import Material, Mesh, Params, Structure, build_mesh
from .solver import FEMResult, SolveError, solve
from .stability import toppling_margin


@dataclass
class Viability:
    ok: bool
    margins: dict[str, float]
    score: float
    reason: str | None = None
    mesh: Mesh | None = None
    fem: FEMResult | None = None
    components: list[dict] = field(default_factory=list)


_FATAL_MARGINS = {"topple": -np.inf, "stress": -np.inf,
                  "buckling": -np.inf, "deflection": -np.inf}


def viability(
    structure: Structure,
    material: Material | None = None,
    params: Params | None = None,
    point_loads: dict[int, np.ndarray] | None = None,
) -> Viability:
    material = material or Material()
    params = params or structure.params

    def fatal(reason: str, mesh: Mesh | None = None) -> Viability:
        return Viability(ok=False, margins=dict(_FATAL_MARGINS),
                         score=-params.score_cap, reason=reason, mesh=mesh)

    if not structure.sticks:
        return fatal("empty structure")
    mesh = build_mesh(structure, params)
    if not mesh.supports:
        return fatal("no ground contact", mesh)
    try:
        fem = solve(mesh, material, gravity=params.gravity, point_loads=point_loads,
                    K_buckling=params.K_buckling)
    except SolveError as e:
        return fatal(str(e), mesh)

    topple, comp_detail = toppling_margin(structure, mesh, params)
    char_len = structure.mean_stick_length()
    margins = {
        "topple": topple,
        "stress": 1.0 - fem.max_utilization,
        "buckling": float(np.min(fem.buckling)) / params.buckling_safety - 1.0,
        "deflection": 1.0 - fem.max_translation / (params.deflect_limit_frac * char_len),
    }
    cap = params.score_cap
    normalized = [
        margins["topple"] / char_len,
        margins["stress"],
        margins["buckling"],
        margins["deflection"],
    ]
    scr = float(np.clip(min(min(v, cap) for v in normalized), -cap, cap))
    ok = bool(all(m > 0.0 for m in margins.values()))
    return Viability(ok=ok, margins=margins, score=scr, mesh=mesh, fem=fem,
                     components=comp_detail)


def score(
    structure: Structure,
    material: Material | None = None,
    params: Params | None = None,
    point_loads: dict[int, np.ndarray] | None = None,
) -> float:
    """Convenience: viability(...).score."""
    return viability(structure, material, params, point_loads).score
