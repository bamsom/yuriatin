"""Frame FEM reward module: welded rigid space frames of circular sticks.

Public surface:
    Stick, Weld, Structure, Material, Params   — model
    build_mesh, Mesh, Member, components       — mesh from sticks+welds
    solve, FEMResult, SolveError               — direct-stiffness solver
    toppling_margin                            — rigid COM-vs-support-polygon check
    viability, Viability, score                — the reward interface

Stability is a CONSTRAINT (positive margins), never a shape objective —
see birdNest.md §3.
"""

from .model import (
    Material,
    Member,
    Mesh,
    Params,
    Stick,
    Structure,
    Weld,
    build_mesh,
    components,
)
from .solver import FEMResult, FloatingStructureError, SolveError, solve
from .stability import support_margin, toppling_margin
from .viability import Viability, score, viability

__all__ = [
    "Material", "Params", "Stick", "Weld", "Structure",
    "Mesh", "Member", "build_mesh", "components",
    "solve", "FEMResult", "SolveError", "FloatingStructureError",
    "support_margin", "toppling_margin",
    "viability", "Viability", "score",
]
