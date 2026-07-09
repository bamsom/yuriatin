"""Sticks, welds, and the FEM mesh built from them.

A Structure is a set of rigid circular-section sticks. Every contact welds
rigidly (birdNest.md §1): add_stick() auto-detects contacts against the
existing sticks (closest segment-segment distance within touching range) and
records a Weld at the closest-approach parameters. The FEM mesh splits each
stick at its weld stations, so a weld braces the stick into shorter members.

Idealizations (documented, deliberate):
- A weld node sits at the MIDPOINT of the two closest centerline points, so
  surface-touching sticks get a small kink (~one radius) at the weld. Fine at
  stick slenderness ~50-100.
- One weld per stick pair (the single closest approach); parallel sticks
  lying along each other still weld at just one point.
- Ground contact is unilateral REST, not a weld: the solver clamps ground
  nodes to compute internal forces, and toppling is checked separately as a
  rigid-body COM-vs-support-polygon margin (stability.py).
"""

from __future__ import annotations

import copy as _copy
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Material:
    """Dry-wood-like twig by default."""

    E: float = 10e9          # Young's modulus, Pa
    G: float = 0.6e9         # shear modulus, Pa (torsion only)
    density: float = 600.0   # kg/m^3
    sigma_y: float = 40e6    # allowable combined stress, Pa


@dataclass(frozen=True)
class Params:
    gravity: float = 9.81
    weld_tol: float = 1e-4          # slack over r_i+r_j for contact detection, m
    ground_tol: float | None = None  # node z <= tol rests on ground; None -> 1.2*max radius
    merge_tol: float = 1e-6         # coincident stations become one node, m
    K_buckling: float = 1.0         # Euler effective-length factor (1.0 = conservative pin-pin)
    buckling_safety: float = 1.0    # required buckling factor; margin = factor/safety - 1
    deflect_limit_frac: float = 0.05  # max nodal translation / mean stick length
    score_cap: float = 10.0         # |normalized margin| cap inside score()


@dataclass
class Stick:
    p0: np.ndarray
    p1: np.ndarray
    radius: float = 0.004

    def __post_init__(self):
        self.p0 = np.asarray(self.p0, dtype=float)
        self.p1 = np.asarray(self.p1, dtype=float)

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.p1 - self.p0))

    @property
    def area(self) -> float:
        return float(np.pi * self.radius**2)

    @property
    def I(self) -> float:  # second moment, circular section (Iy = Iz)
        return float(np.pi * self.radius**4 / 4.0)

    @property
    def J(self) -> float:  # torsion constant
        return float(np.pi * self.radius**4 / 2.0)

    def point(self, t: float) -> np.ndarray:
        return self.p0 + t * (self.p1 - self.p0)

    @property
    def midpoint(self) -> np.ndarray:
        return self.point(0.5)

    def mass(self, density: float) -> float:
        return density * self.area * self.length


@dataclass
class Weld:
    ia: int
    ta: float
    ib: int
    tb: float
    point: np.ndarray  # midpoint of the two closest centerline points


def closest_params(a: Stick, b: Stick, eps: float = 1e-12) -> tuple[float, float, float]:
    """Closest-approach parameters (ta, tb) and distance between two segments."""
    p1, q1, p2, q2 = a.p0, a.p1, b.p0, b.p1
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    aa, ee, ff = float(d1 @ d1), float(d2 @ d2), float(d2 @ r)
    if aa <= eps and ee <= eps:
        s, t = 0.0, 0.0
    elif aa <= eps:
        s, t = 0.0, float(np.clip(ff / ee, 0.0, 1.0))
    else:
        cc = float(d1 @ r)
        if ee <= eps:
            s, t = float(np.clip(-cc / aa, 0.0, 1.0)), 0.0
        else:
            bb = float(d1 @ d2)
            denom = aa * ee - bb * bb
            s = float(np.clip((bb * ff - cc * ee) / denom, 0.0, 1.0)) if denom > eps else 0.0
            t = (bb * s + ff) / ee
            if t < 0.0:
                t, s = 0.0, float(np.clip(-cc / aa, 0.0, 1.0))
            elif t > 1.0:
                t, s = 1.0, float(np.clip((bb - cc) / aa, 0.0, 1.0))
    d = float(np.linalg.norm((p1 + s * d1) - (p2 + t * d2)))
    return s, t, d


class Structure:
    """Sticks + welds. Contacts weld automatically on add_stick()."""

    def __init__(self, params: Params | None = None):
        self.params = params or Params()
        self.sticks: list[Stick] = []
        self.welds: list[Weld] = []

    def add_stick(self, p0, p1, radius: float = 0.004) -> int:
        s = Stick(np.asarray(p0, float), np.asarray(p1, float), radius)
        si = len(self.sticks)
        for j, other in enumerate(self.sticks):
            ta, tb, d = closest_params(s, other)
            if d <= s.radius + other.radius + self.params.weld_tol:
                mid = 0.5 * (s.point(ta) + other.point(tb))
                self.welds.append(Weld(si, ta, j, tb, mid))
        self.sticks.append(s)
        return si

    def add_weld(self, ia: int, ta: float, ib: int, tb: float) -> None:
        mid = 0.5 * (self.sticks[ia].point(ta) + self.sticks[ib].point(tb))
        self.welds.append(Weld(ia, ta, ib, tb, mid))

    def welds_of(self, si: int) -> list[Weld]:
        return [w for w in self.welds if w.ia == si or w.ib == si]

    def copy(self) -> "Structure":
        return _copy.deepcopy(self)

    # -- aggregate geometry ------------------------------------------------
    def com(self) -> np.ndarray:
        masses = np.array([s.length * s.area for s in self.sticks])  # density cancels
        mids = np.array([s.midpoint for s in self.sticks])
        return (masses[:, None] * mids).sum(axis=0) / masses.sum()

    def height(self) -> float:
        return max(max(s.p0[2], s.p1[2]) for s in self.sticks)

    def span(self) -> float:
        pts = np.array([p for s in self.sticks for p in (s.p0, s.p1)])[:, :2]
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        return float(np.linalg.norm(hi - lo))

    def mean_stick_length(self) -> float:
        return float(np.mean([s.length for s in self.sticks]))


# --------------------------------------------------------------------------
# FEM mesh
# --------------------------------------------------------------------------

@dataclass
class Member:
    n1: int
    n2: int
    stick: int
    radius: float


@dataclass
class Mesh:
    nodes: np.ndarray        # (n, 3)
    members: list[Member]
    supports: list[int]      # node indices resting on the ground


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        self.parent[self.find(i)] = self.find(j)


def build_mesh(structure: Structure, params: Params | None = None) -> Mesh:
    params = params or structure.params
    sticks = structure.sticks
    if not sticks:
        raise ValueError("empty structure")

    # 1. stations per stick: endpoints + weld parameters, clustered so that
    #    stations closer than ~half a radius along the stick share a node
    #    (avoids degenerate near-zero members at multi-weld joints).
    station_ts: list[list[float]] = [[0.0, 1.0] for _ in sticks]
    for w in structure.welds:
        station_ts[w.ia].append(w.ta)
        station_ts[w.ib].append(w.tb)

    clusters: list[list[float]] = []  # per stick: cluster-representative ts
    for si, ts in enumerate(station_ts):
        ts = sorted(ts)
        min_seg = max(params.merge_tol, 0.5 * sticks[si].radius)
        L = max(sticks[si].length, 1e-12)
        groups: list[list[float]] = [[ts[0]]]
        for t in ts[1:]:
            if (t - groups[-1][-1]) * L < min_seg:
                groups[-1].append(t)
            else:
                groups.append([t])
        clusters.append([float(np.mean(g)) for g in groups])

    # 2. global station list + union-find
    gid: dict[tuple[int, int], int] = {}
    pts: list[np.ndarray] = []
    for si, reps in enumerate(clusters):
        for k, t in enumerate(reps):
            gid[(si, k)] = len(pts)
            pts.append(sticks[si].point(t))
    uf = _UnionFind(len(pts))

    def cluster_index(si: int, t: float) -> int:
        return int(np.argmin([abs(t - r) for r in clusters[si]]))

    for w in structure.welds:
        uf.union(gid[(w.ia, cluster_index(w.ia, w.ta))],
                 gid[(w.ib, cluster_index(w.ib, w.tb))])
    # coincident stations (hand-built exact intersections) also merge
    pts_arr = np.array(pts)
    diff = pts_arr[:, None, :] - pts_arr[None, :, :]
    close = np.linalg.norm(diff, axis=2) < params.merge_tol
    for i, j in zip(*np.nonzero(np.triu(close, k=1))):
        uf.union(int(i), int(j))

    # 3. nodes = group means
    groups_by_root: dict[int, list[int]] = {}
    for i in range(len(pts)):
        groups_by_root.setdefault(uf.find(i), []).append(i)
    node_of: dict[int, int] = {}
    nodes: list[np.ndarray] = []
    for root, group in groups_by_root.items():
        node_of[root] = len(nodes)
        nodes.append(np.mean([pts[i] for i in group], axis=0))
    nodes_arr = np.array(nodes)

    # 4. members = consecutive stations along each stick
    members: list[Member] = []
    for si, reps in enumerate(clusters):
        for k in range(len(reps) - 1):
            a = node_of[uf.find(gid[(si, k)])]
            b = node_of[uf.find(gid[(si, k + 1)])]
            if a == b or np.linalg.norm(nodes_arr[a] - nodes_arr[b]) < 1e-9:
                continue
            members.append(Member(a, b, si, sticks[si].radius))

    # 5. supports: a straight stick's lowest point is an endpoint, so station
    #    nodes are the only possible ground contacts.
    tol = params.ground_tol
    if tol is None:
        tol = 1.2 * max(s.radius for s in sticks)
    supports = [i for i, p in enumerate(nodes_arr) if p[2] <= tol]

    return Mesh(nodes=nodes_arr, members=members, supports=supports)


def components(mesh: Mesh) -> list[dict]:
    """Connected components of the welded frame.

    Each is one rigid body for the toppling check:
    {"nodes": [...], "sticks": {...}, "contacts": [...support node ids...]}.
    """
    uf = _UnionFind(len(mesh.nodes))
    for m in mesh.members:
        uf.union(m.n1, m.n2)
    comp_of_root: dict[int, dict] = {}
    for i in range(len(mesh.nodes)):
        comp_of_root.setdefault(uf.find(i), {"nodes": [], "sticks": set(), "contacts": []})
        comp_of_root[uf.find(i)]["nodes"].append(i)
    for m in mesh.members:
        comp_of_root[uf.find(m.n1)]["sticks"].add(m.stick)
    support_set = set(mesh.supports)
    for comp in comp_of_root.values():
        comp["contacts"] = [i for i in comp["nodes"] if i in support_set]
    return list(comp_of_root.values())
