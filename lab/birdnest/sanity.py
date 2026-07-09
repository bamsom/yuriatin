"""Numeric sanity table for the hand-built cases: python -m birdnest.sanity"""

from __future__ import annotations

import numpy as np

from . import cases
from .fem import viability


def main() -> None:
    header = f"{'case':<20} {'ok':<5} {'topple(m)':>10} {'stress':>8} {'buckling':>9} {'deflect':>8} {'score':>8}  reason"
    print(header)
    print("-" * len(header))
    for name, (structure, loads) in cases.all_cases().items():
        v = viability(structure, point_loads=loads)
        m = v.margins

        def fmt(x, w=8, p=3):
            if np.isinf(x):
                return f"{'inf':>{w}}"
            return f"{x:>{w}.{p}f}"

        print(f"{name:<20} {str(v.ok):<5} {fmt(m['topple'], 10, 4)} {fmt(m['stress'])} "
              f"{fmt(m['buckling'], 9)} {fmt(m['deflection'])} {fmt(v.score)}  {v.reason or ''}")


if __name__ == "__main__":
    main()
