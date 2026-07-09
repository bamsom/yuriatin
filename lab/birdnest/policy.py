"""Linear scoring policies over candidate features.

A policy is a weight vector theta in R^7. Each step the improviser machinery
(improvise.run_episode) samples K candidates and evaluates every one with the
Phase-1 viability(); among the VIABLE candidates the policy places
argmax theta . f(candidate). Features are computed from the already-evaluated
viability plus cheap geometry — no extra FEM calls.

FEATURES (order = FEATURE_NAMES; every length is normalized by the nominal
stick length L so all features are O(1) and one mutation sigma is comparable
across components):
  score     worst normalized margin of the RESULTING structure (fem score) —
            the robustness of the whole frame after this placement
  d_height  change in structure height / L (positive = builds upward)
  d_span    change in horizontal span / L (positive = spreads outward)
  n_welds   number of welds this placement created (how connected the new
            stick is; >=1 by construction since candidates touch the surface)
  mid_z     height of the new stick's midpoint / L (where the mass goes)
  com_dist  horizontal (xy) distance of the new stick's midpoint from the
            PRE-placement center of mass / L (eccentricity of the added mass)
  bias      constant 1.0. Inert under pure argmax (it offsets every candidate
            equally); kept so theta matches the documented 7-feature spec and
            softmax-style policies can reuse the same feature vector later.

theta = 0 makes every candidate tie; exact ties are broken uniformly at
random, so the zero policy degenerates to the random_valid baseline (the
sanity anchor). For generic real theta ties have measure zero and the pick
is deterministic given theta and the candidate list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

FEATURE_NAMES = ("score", "d_height", "d_span", "n_welds", "mid_z", "com_dist", "bias")
N_FEATURES = len(FEATURE_NAMES)


def features(structure, entry, stick_len: float) -> np.ndarray:
    """Feature vector for one viable-candidate entry (s2, idx, v, new_welds)
    as produced inside improvise.run_episode; `structure` is PRE-placement."""
    s2, idx, v, new_welds = entry
    stick = s2.sticks[idx]
    mid = stick.midpoint
    com = structure.com()
    L = stick_len
    return np.array([
        v.score,
        (s2.height() - structure.height()) / L,
        (s2.span() - structure.span()) / L,
        float(len(new_welds)),
        mid[2] / L,
        float(np.hypot(mid[0] - com[0], mid[1] - com[1])) / L,
        1.0,
    ])


def feature_matrix(structure, viable, stick_len: float) -> np.ndarray:
    return np.array([features(structure, e, stick_len) for e in viable])


def pick_index(theta: np.ndarray, F: np.ndarray, rng: np.random.Generator) -> int:
    """argmax theta . f over rows of F; EXACT ties broken uniformly via rng."""
    u = F @ np.asarray(theta, float)
    ties = np.flatnonzero(u == u.max())
    if len(ties) == 1:
        return int(ties[0])
    return int(ties[int(rng.integers(len(ties)))])


@dataclass
class LinearPolicy:
    """Callable improviser: pick(structure, viable, rng) -> chosen entry."""
    theta: np.ndarray
    stick_len: float = 0.30
    name: str = field(default="linear_policy")

    def __post_init__(self):
        self.theta = np.asarray(self.theta, float)
        if self.theta.shape != (N_FEATURES,):
            raise ValueError(f"theta must have shape ({N_FEATURES},), got {self.theta.shape}")

    def __call__(self, structure, viable, rng: np.random.Generator):
        F = feature_matrix(structure, viable, self.stick_len)
        return viable[pick_index(self.theta, F, rng)]
