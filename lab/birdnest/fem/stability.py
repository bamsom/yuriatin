"""Rigid-body toppling: COM projection vs support polygon of ground contacts.

Each welded connected component is one rigid body. Its support region is the
convex hull of its ground-contact points, inflated by the contact radius
(a capsule end on a plane is a point contact; the inflation stands in for the
finite contact patch and makes a perfectly balanced vertical stick read as
marginally stable rather than knife-edge zero).

margin > 0: COM projects inside the inflated support region with that much
clearance (meters). margin < 0: it projects outside by that much — topples.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull, QhullError

from .model import Mesh, Params, Structure, components


def _dist_point_segment(q: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    denom = float(ab @ ab)
    if denom < 1e-18:
        return float(np.linalg.norm(q - a))
    t = float(np.clip((q - a) @ ab / denom, 0.0, 1.0))
    return float(np.linalg.norm(q - (a + t * ab)))


def _signed_inside_distance(pts: np.ndarray, q: np.ndarray) -> float:
    """Clearance of q inside the convex hull of pts (>0 inside, <0 outside)."""
    pts = np.unique(np.round(np.atleast_2d(pts), 12), axis=0)
    if len(pts) == 1:
        return -float(np.linalg.norm(q - pts[0]))
    if len(pts) == 2:
        return -_dist_point_segment(q, pts[0], pts[1])
    try:
        hull = ConvexHull(pts)
    except QhullError:
        # collinear: support is the extreme segment along the principal axis
        centered = pts - pts.mean(axis=0)
        direction = np.linalg.svd(centered, full_matrices=False)[2][0]
        proj = centered @ direction
        e0 = pts[int(np.argmin(proj))]
        e1 = pts[int(np.argmax(proj))]
        return -_dist_point_segment(q, e0, e1)
    # hull.equations rows are [a, b, c] with unit normal (a, b); inside: ax+by+c <= 0
    vals = hull.equations[:, :2] @ q + hull.equations[:, 2]
    if np.all(vals <= 1e-12):
        return float(-np.max(vals))
    verts = pts[hull.vertices]
    return -min(
        _dist_point_segment(q, verts[i], verts[(i + 1) % len(verts)])
        for i in range(len(verts))
    )


def support_margin(contact_xy: np.ndarray, com_xy: np.ndarray, contact_radius: float) -> float:
    """Toppling margin (m) of one rigid body: >0 stable, <0 topples."""
    return contact_radius + _signed_inside_distance(np.asarray(contact_xy, float),
                                                    np.asarray(com_xy, float))


def toppling_margin(
    structure: Structure, mesh: Mesh, params: Params | None = None
) -> tuple[float, list[dict]]:
    """Worst toppling margin over all welded components, plus per-component detail.

    A component with no ground contact gets margin -inf (it is falling; the
    solver independently refuses it as floating).
    """
    detail: list[dict] = []
    worst = np.inf
    for comp in components(mesh):
        sticks = [structure.sticks[i] for i in sorted(comp["sticks"])]
        masses = np.array([s.length * s.area for s in sticks])
        mids = np.array([s.midpoint for s in sticks])
        com = (masses[:, None] * mids).sum(axis=0) / masses.sum()
        if not comp["contacts"]:
            margin = -np.inf
        else:
            contact_xy = mesh.nodes[comp["contacts"]][:, :2]
            contact_radius = min(s.radius for s in sticks)
            margin = support_margin(contact_xy, com[:2], contact_radius)
        detail.append({"sticks": sorted(comp["sticks"]), "com": com, "margin": margin,
                       "contacts": list(comp["contacts"])})
        worst = min(worst, margin)
    return float(worst), detail
