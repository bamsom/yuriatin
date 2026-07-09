"""Seed generator: dump N sticks with random poses, settle, weld all contacts,
freeze (birdNest.md §1: the seed is an accident nobody designed).

SETTLING IS A STUB — pybullet is not present in the styleDraw env. The stub:
drop each stick along -z to its first contact (ground or an already-settled
stick), then one gravity pivot about that contact until a second contact or
horizontal rest. No sliding, no bouncing, no multi-body re-settling. Every
run that uses it prints a warning and stamps meta.stub_settled = true.

Difficulty knobs: n_sticks, and an accept band on the seed's toppling margin
(narrow band near zero = "barely stands").
"""

from __future__ import annotations

import sys
from importlib.util import find_spec

import numpy as np

from .fem import Material, Params, Stick, Structure, viability
from .fem.model import closest_params

STUB_WARNING = ("WARNING: seeds are stub-settled (pybullet not found): "
                "drop along -z to first contact + one gravity pivot, no dynamics.")

_warned = False


def warn_stub_settle() -> None:
    global _warned
    if _warned:
        return
    _warned = True
    if find_spec("pybullet") is not None:
        print("NOTE: pybullet detected, but dynamic settling is not wired into "
              "this mockup; using the labeled stub anyway.", file=sys.stderr)
    else:
        print(STUB_WARNING, file=sys.stderr)


def _unit(rng: np.random.Generator) -> np.ndarray:
    while True:
        v = rng.normal(size=3)
        n = np.linalg.norm(v)
        if n > 1e-9:
            return v / n


def _rot(axis: np.ndarray, th: float) -> np.ndarray:
    a = axis / np.linalg.norm(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * (K @ K)


def _min_gap(p0, p1, r, placed: list[Stick], pivot_idx: int | None = None):
    """Smallest surface gap to any placed stick; pivot stick needs to sink
    a bit past its standing contact to count as a NEW hit."""
    best, best_j = np.inf, None
    probe = Stick(p0, p1, r)
    for j, s in enumerate(placed):
        _, _, d = closest_params(probe, s)
        g = d - (r + s.radius)
        if j == pivot_idx:
            g += 1e-5
        if g < best:
            best, best_j = g, j
    return best, best_j


def _first_drop_contact(p0, p1, r, placed, dz_max: float):
    """First dz in [0, dz_max] where the dropping stick touches a placed stick;
    (dz_max, None) means it reaches the ground untouched."""
    if not placed or dz_max <= 0:
        return dz_max, None
    n = max(2, int(dz_max / 0.002) + 2)
    prev = 0.0
    for dz in np.linspace(0.0, dz_max, n)[1:]:
        g, j = _min_gap(p0 - [0, 0, dz], p1 - [0, 0, dz], r, placed)
        if g <= 0:
            lo, hi, hit = prev, dz, j
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                gm, jm = _min_gap(p0 - [0, 0, mid], p1 - [0, 0, mid], r, placed)
                if gm <= 0:
                    hi, hit = mid, jm
                else:
                    lo = mid
            return hi, hit
        prev = dz
    return dz_max, None


def _pivot_to_rest(rng, p0, p1, r, placed, pivot_stick: int | None, pivot_t: float):
    """One gravity pivot about the first contact until a second contact or
    horizontal rest. pivot_stick None => pivot is a ground-touching endpoint."""
    L = float(np.linalg.norm(p1 - p0))
    u = (p1 - p0) / L
    elev = float(np.arcsin(np.clip(abs(u[2]), 0, 1)))
    if elev < np.deg2rad(3.0):
        return p0, p1  # already essentially flat
    q = p0 + pivot_t * (p1 - p0)

    w = np.cross([0.0, 0.0, 1.0], u)
    if np.linalg.norm(w) < 1e-6:  # vertical stick: pick a fall azimuth
        a = rng.uniform(0, 2 * np.pi)
        w = np.array([np.cos(a), np.sin(a), 0.0])
    w /= np.linalg.norm(w)
    m = 0.5 * (p0 + p1) - q  # COM relative to pivot; fall lowers it
    if float(np.cross(w, m)[2]) > 0:
        w = -w

    def posed(th):
        R = _rot(w, th)
        return q + R @ (p0 - q), q + R @ (p1 - q)

    def hits(th) -> bool:
        a, b = posed(th)
        ends = [a, b]
        if pivot_stick is None:  # the grounded endpoint itself always touches
            ends = [b] if pivot_t < 0.5 else [a]
        if min(e[2] for e in ends) - r <= 1e-9:
            return True
        g, _ = _min_gap(a, b, r, placed, pivot_idx=pivot_stick)
        return g <= 0

    theta_max = elev
    prev = 0.0
    for th in np.linspace(0.0, theta_max, 61)[1:]:
        if hits(th):
            lo, hi = prev, th
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                if hits(mid):
                    hi = mid
                else:
                    lo = mid
            return posed(hi)
        prev = th
    return posed(theta_max)  # no obstacle: comes to rest horizontal


def make_seed_sticks(rng, n_sticks: int, stick_len: float, radius: float,
                     dump_radius: float) -> list[Stick]:
    """Stub-settled poses for one dump (no acceptance filtering)."""
    placed: list[Stick] = []
    for _ in range(n_sticks):
        u = _unit(rng)
        rd = dump_radius * np.sqrt(rng.uniform())
        ang = rng.uniform(0, 2 * np.pi)
        z_top = max([max(s.p0[2], s.p1[2]) for s in placed], default=0.0)
        c = np.array([rd * np.cos(ang), rd * np.sin(ang), z_top + stick_len])
        p0, p1 = c - 0.5 * stick_len * u, c + 0.5 * stick_len * u

        dz_max = min(p0[2], p1[2]) - radius  # drop until lowest end reaches ground
        dz, jhit = _first_drop_contact(p0, p1, radius, placed, dz_max)
        p0, p1 = p0 - [0, 0, dz], p1 - [0, 0, dz]
        if jhit is None:
            pivot_t = 0.0 if p0[2] < p1[2] else 1.0
            p0, p1 = _pivot_to_rest(rng, p0, p1, radius, placed, None, pivot_t)
        else:
            t_new, _, _ = closest_params(Stick(p0, p1, radius), placed[jhit])
            p0, p1 = _pivot_to_rest(rng, p0, p1, radius, placed, jhit, t_new)
        placed.append(Stick(p0, p1, radius))
    return placed


def generate_seed(
    rng: np.random.Generator,
    n_sticks: int = 5,
    stick_len: float = 0.30,
    radius: float = 0.004,
    dump_radius: float = 0.15,
    margin_band: tuple[float, float] = (0.0, np.inf),
    material: Material | None = None,
    params: Params | None = None,
    max_tries: int = 60,
):
    """Dump-settle-weld until a seed lands in the toppling-margin accept band.

    Returns (structure, viability, tries). Deterministic given the rng state.
    """
    warn_stub_settle()
    material = material or Material()
    params = params or Params()
    lo, hi = margin_band
    for attempt in range(1, max_tries + 1):
        sticks = make_seed_sticks(rng, n_sticks, stick_len, radius, dump_radius)
        s = Structure(params)
        for st in sticks:
            s.add_stick(st.p0, st.p1, st.radius)
        v = viability(s, material, params)
        if v.fem is not None and v.ok and lo <= v.margins["topple"] <= hi:
            return s, v, attempt
    raise RuntimeError(
        f"no acceptable seed after {max_tries} dumps "
        f"(n_sticks={n_sticks}, toppling band [{lo}, {hi}])"
    )
