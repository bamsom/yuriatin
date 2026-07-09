"""Hand-built benchmark structures, shared by the unit tests and sanity table.

These encode the EXPECTED behavior of the reward module on cases a human can
verify by inspection (birdNest.md §3: validate reward on hand-made cases
before anything learns from it).
"""

from __future__ import annotations

import numpy as np

from .fem import Structure, build_mesh

R_STICK = 0.004   # default stick radius, m
L_STICK = 0.30    # default stick length, m


def vertical_stick() -> Structure:
    """One stick balanced upright on its end: barely but genuinely stable."""
    s = Structure()
    s.add_stick((0, 0, 0), (0, 0, L_STICK), R_STICK)
    return s


def leaning_stick() -> Structure:
    """One stick leaning ~30 deg with a single ground contact: topples."""
    s = Structure()
    s.add_stick((0, 0, 0), (0.15, 0, 0.26), R_STICK)
    return s


def tripod(apex_h: float = 0.25, foot_r: float = 0.12) -> Structure:
    """Three legs meeting at an apex: stable, symmetric member stresses."""
    s = Structure()
    apex = (0.0, 0.0, apex_h)
    for ang_deg in (90.0, 210.0, 330.0):
        a = np.deg2rad(ang_deg)
        s.add_stick((foot_r * np.cos(a), foot_r * np.sin(a), 0.0), apex, R_STICK)
    return s


def tripod_cantilever(arm_len: float = 0.25) -> Structure:
    """Tripod plus a horizontal arm welded at the apex: viable, but the arm
    root carries high bending and the COM shift eats toppling margin."""
    s = tripod()
    apex = np.array([0.0, 0.0, 0.25])
    s.add_stick(apex, apex + np.array([arm_len, 0.0, 0.0]), R_STICK)
    return s


def _strut(radius: float, length: float = 0.5, payload: float = 1.0):
    """Vertical strut with a downward point load on its top node."""
    s = Structure()
    s.add_stick((0, 0, 0), (0, 0, length), radius)
    mesh = build_mesh(s)
    top = int(np.argmax(mesh.nodes[:, 2]))
    return s, {top: np.array([0.0, 0.0, -payload, 0.0, 0.0, 0.0])}


def slender_strut():
    """r=1mm, L=0.5m, 1N payload: Euler load ~0.31N -> must flag buckling."""
    return _strut(radius=0.001)


def stocky_strut():
    """r=5mm, same load: Euler load ~194N -> must NOT flag buckling."""
    return _strut(radius=0.005)


def all_cases() -> dict[str, tuple[Structure, dict | None]]:
    """name -> (structure, point_loads or None), in presentation order."""
    sl, sl_loads = slender_strut()
    st, st_loads = stocky_strut()
    return {
        "vertical_stick": (vertical_stick(), None),
        "leaning_stick": (leaning_stick(), None),
        "tripod": (tripod(), None),
        "tripod_cantilever": (tripod_cantilever(), None),
        "slender_strut_1N": (sl, sl_loads),
        "stocky_strut_1N": (st, st_loads),
    }
