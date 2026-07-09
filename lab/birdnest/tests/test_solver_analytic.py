"""Solver-level checks against closed-form beam/column results.

These pin the direct-stiffness implementation to textbook answers before any
structure-level behavior is trusted.
"""

import numpy as np
import pytest

from birdnest.fem import FloatingStructureError, Material, Member, Mesh, solve

MAT = Material()
R = 0.004
A = np.pi * R**2
I = np.pi * R**4 / 4


def _one_member_mesh(p0, p1, radius=R):
    return Mesh(nodes=np.array([p0, p1], dtype=float),
                members=[Member(0, 1, 0, radius)],
                supports=[0])


def test_cantilever_self_weight_matches_analytic():
    L = 0.4
    mesh = _one_member_mesh([0, 0, 1], [L, 0, 1])
    res = solve(mesh, MAT)
    w = MAT.density * 9.81 * A  # N/m
    tip = w * L**4 / (8 * MAT.E * I)
    assert np.isclose(res.u[1, 2], -tip, rtol=1e-9)
    # root moment wL^2/2, recovered exactly with consistent nodal loads
    assert np.isclose(res.moment[0], w * L**2 / 2, rtol=1e-9)


def test_cantilever_tip_point_load_matches_analytic():
    L, P = 0.4, 2.0
    mesh = _one_member_mesh([0, 0, 1], [L, 0, 1])
    res = solve(mesh, MAT, self_weight=False,
                point_loads={1: np.array([0, 0, -P, 0, 0, 0])})
    assert np.isclose(res.u[1, 2], -P * L**3 / (3 * MAT.E * I), rtol=1e-9)
    assert np.isclose(res.moment[0], P * L, rtol=1e-9)


def test_vertical_column_self_weight_axial():
    L = 0.3
    mesh = _one_member_mesh([0, 0, 0], [0, 0, L])
    res = solve(mesh, MAT)
    W = MAT.density * 9.81 * A * L
    # worst-end axial force is the base: full weight in compression
    assert np.isclose(res.axial[0], -W, rtol=1e-9)
    assert np.isclose(res.axial_stress[0], -MAT.density * 9.81 * L, rtol=1e-9)
    assert res.moment[0] < 1e-12  # pure axial case


@pytest.mark.parametrize("radius,expect_flag", [(0.001, True), (0.005, False)])
def test_euler_buckling_factor(radius, expect_flag):
    L, P = 0.5, 1.0
    mesh = _one_member_mesh([0, 0, 0], [0, 0, L], radius=radius)
    res = solve(mesh, MAT, self_weight=False,
                point_loads={1: np.array([0, 0, -P, 0, 0, 0])})
    I_r = np.pi * radius**4 / 4
    expected = np.pi**2 * MAT.E * I_r / L**2 / P  # K = 1 convention
    assert np.isclose(res.buckling[0], expected, rtol=1e-9)
    assert (res.buckling[0] < 1.0) == expect_flag


def test_tension_member_has_infinite_buckling_factor():
    # hang a weight BELOW the support: member in tension
    L = 0.3
    mesh = _one_member_mesh([0, 0, 0], [0, 0, -L])
    # support must be the ground node; here node 0 (z=0) supports node 1 below it
    res = solve(mesh, MAT, self_weight=False,
                point_loads={1: np.array([0, 0, -1.0, 0, 0, 0])})
    assert np.isinf(res.buckling[0])
    assert res.axial[0] > 0  # tension positive


def test_floating_structure_is_refused():
    # second member not connected to any support
    mesh = Mesh(nodes=np.array([[0, 0, 0], [0, 0, 0.3], [1, 0, 0.5], [1, 0, 0.8]]),
                members=[Member(0, 1, 0, R), Member(2, 3, 1, R)],
                supports=[0])
    with pytest.raises(FloatingStructureError):
        solve(mesh, MAT)
