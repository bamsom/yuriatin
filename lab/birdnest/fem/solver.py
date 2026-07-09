"""Direct-stiffness solver for 3D frames of circular-section members.

Euler-Bernoulli frame elements (axial + torsion + biaxial bending), rigid
welded joints, ground nodes fully clamped. Self-weight enters as consistent
(work-equivalent) nodal loads, so nodal displacements and recovered end
forces for uniform loads are exact for prismatic members — the analytic
tests in tests/test_solver_analytic.py rely on this.

Per-member outputs: worst-end axial force (tension positive), worst-end
resultant bending moment, combined stress |N|/A + M*r/I, and the Euler
buckling factor P_cr / P_compression (inf when not in compression).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import Material, Member, Mesh


class SolveError(RuntimeError):
    """Stiffness system could not be solved (mechanism / singular)."""


class FloatingStructureError(SolveError):
    """Some connected component has no ground support."""


@dataclass
class FEMResult:
    u: np.ndarray             # (n, 6) nodal displacements + rotations
    axial: np.ndarray         # (m,) worst-end axial force, tension +
    moment: np.ndarray        # (m,) worst-end resultant bending moment
    sigma: np.ndarray         # (m,) combined stress |N|/A + M*r/I, worst end
    axial_stress: np.ndarray  # (m,) signed axial stress N/A (viewer colormap)
    buckling: np.ndarray      # (m,) Euler factor P_cr / P_comp; inf if no compression
    max_translation: float

    @property
    def max_utilization(self):  # filled by solve() with sigma / sigma_y
        return self._max_util

    def __post_init__(self):
        self._max_util = None


def _local_axes(p1: np.ndarray, p2: np.ndarray) -> tuple[np.ndarray, float]:
    dx = p2 - p1
    L = float(np.linalg.norm(dx))
    x = dx / L
    ref = np.array([0.0, 0.0, 1.0]) if abs(x[2]) < 0.999 else np.array([0.0, 1.0, 0.0])
    y = np.cross(ref, x)
    y /= np.linalg.norm(y)
    z = np.cross(x, y)
    return np.vstack([x, y, z]), L  # rows = local axes in global coords


def _local_stiffness(E: float, G: float, A: float, I: float, J: float, L: float) -> np.ndarray:
    k = np.zeros((12, 12))
    ea, gj = E * A / L, G * J / L
    k[0, 0] = k[6, 6] = ea
    k[0, 6] = k[6, 0] = -ea
    k[3, 3] = k[9, 9] = gj
    k[3, 9] = k[9, 3] = -gj
    a, b, c, d = 12 * E * I / L**3, 6 * E * I / L**2, 4 * E * I / L, 2 * E * I / L
    # bending in local x-y plane (dofs: uy1=1, thz1=5, uy2=7, thz2=11)
    for i, j, v in [(1, 1, a), (1, 5, b), (1, 7, -a), (1, 11, b),
                    (5, 5, c), (5, 7, -b), (5, 11, d),
                    (7, 7, a), (7, 11, -b), (11, 11, c)]:
        k[i, j] = k[j, i] = v
    # bending in local x-z plane (dofs: uz1=2, thy1=4, uz2=8, thy2=10) — mirrored signs
    for i, j, v in [(2, 2, a), (2, 4, -b), (2, 8, -a), (2, 10, -b),
                    (4, 4, c), (4, 8, b), (4, 10, d),
                    (8, 8, a), (8, 10, b), (10, 10, c)]:
        k[i, j] = k[j, i] = v
    return k


def _eq_nodal_loads(q_local: np.ndarray, L: float) -> np.ndarray:
    """Consistent nodal loads for a uniform line load q_local (N/m, local frame)."""
    qx, qy, qz = q_local
    f = np.zeros(12)
    f[0] = f[6] = qx * L / 2
    f[1] = f[7] = qy * L / 2
    f[5], f[11] = qy * L**2 / 12, -qy * L**2 / 12
    f[2] = f[8] = qz * L / 2
    f[4], f[10] = -qz * L**2 / 12, qz * L**2 / 12
    return f


def check_grounded(mesh: Mesh) -> None:
    """Raise FloatingStructureError if any component lacks a ground support."""
    from .model import components

    for comp in components(mesh):
        if not comp["contacts"]:
            raise FloatingStructureError(
                f"component with sticks {sorted(comp['sticks'])} has no ground contact"
            )


def solve(
    mesh: Mesh,
    material: Material,
    gravity: float = 9.81,
    point_loads: dict[int, np.ndarray] | None = None,
    self_weight: bool = True,
    K_buckling: float = 1.0,
) -> FEMResult:
    """Solve the clamped-support frame; point_loads keyed by mesh node index."""
    if not mesh.supports:
        raise FloatingStructureError("no ground contact at all")
    check_grounded(mesh)

    n = len(mesh.nodes)
    ndof = 6 * n
    K = np.zeros((ndof, ndof))
    F = np.zeros(ndof)

    elem: list[dict] = []
    for m in mesh.members:
        p1, p2 = mesh.nodes[m.n1], mesh.nodes[m.n2]
        R, L = _local_axes(p1, p2)
        A = np.pi * m.radius**2
        I = np.pi * m.radius**4 / 4.0
        J = 2.0 * I
        k_loc = _local_stiffness(material.E, material.G, A, I, J, L)
        T = np.kron(np.eye(4), R)
        dofs = np.r_[6 * m.n1: 6 * m.n1 + 6, 6 * m.n2: 6 * m.n2 + 6]
        K[np.ix_(dofs, dofs)] += T.T @ k_loc @ T
        f_eq = np.zeros(12)
        if self_weight:
            q_local = R @ np.array([0.0, 0.0, -material.density * gravity * A])
            f_eq = _eq_nodal_loads(q_local, L)
            F[dofs] += T.T @ f_eq
        elem.append(dict(k=k_loc, T=T, dofs=dofs, f_eq=f_eq, A=A, I=I, L=L, r=m.radius))

    if point_loads:
        for ni, load in point_loads.items():
            F[6 * ni: 6 * ni + 6] += np.asarray(load, float)

    fixed = np.array([d for s in mesh.supports for d in range(6 * s, 6 * s + 6)])
    free = np.setdiff1d(np.arange(ndof), fixed)
    u = np.zeros(ndof)
    if free.size:
        K_ff = K[np.ix_(free, free)]
        F_f = F[free]
        try:
            u_f = np.linalg.solve(K_ff, F_f)
        except np.linalg.LinAlgError as e:
            raise SolveError(f"singular stiffness matrix: {e}") from e
        resid = np.linalg.norm(K_ff @ u_f - F_f) / max(1.0, np.linalg.norm(F_f))
        if not np.isfinite(u_f).all() or resid > 1e-6:
            raise SolveError(f"ill-conditioned stiffness system (residual {resid:.2e})")
        u[free] = u_f

    # member end-force recovery: f_local = k u_local - f_eq
    m_count = len(mesh.members)
    axial = np.zeros(m_count)
    moment = np.zeros(m_count)
    sigma = np.zeros(m_count)
    axial_stress = np.zeros(m_count)
    buckling = np.full(m_count, np.inf)
    for i, e in enumerate(elem):
        f_loc = e["k"] @ (e["T"] @ u[e["dofs"]]) - e["f_eq"]
        N1, N2 = -f_loc[0], f_loc[6]  # tension positive
        M1 = float(np.hypot(f_loc[4], f_loc[5]))
        M2 = float(np.hypot(f_loc[10], f_loc[11]))
        A, I, r, L = e["A"], e["I"], e["r"], e["L"]
        s1 = abs(N1) / A + M1 * r / I
        s2 = abs(N2) / A + M2 * r / I
        sigma[i] = max(s1, s2)
        moment[i] = max(M1, M2)
        axial[i] = N1 if abs(N1) >= abs(N2) else N2
        axial_stress[i] = axial[i] / A
        comp = max(0.0, -N1, -N2)
        if comp > 0.0:
            P_cr = np.pi**2 * material.E * I / (K_buckling * L) ** 2
            buckling[i] = P_cr / comp

    res = FEMResult(
        u=u.reshape(n, 6),
        axial=axial,
        moment=moment,
        sigma=sigma,
        axial_stress=axial_stress,
        buckling=buckling,
        max_translation=float(np.max(np.linalg.norm(u.reshape(n, 6)[:, :3], axis=1))),
    )
    res._max_util = float(np.max(sigma) / material.sigma_y) if m_count else 0.0
    return res
