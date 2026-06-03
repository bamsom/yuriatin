"""Season-arc progression — rule-based, deterministic (NOT LLM-driven).

The weekly "tick" is the unit of progress. Idempotency is enforced through the
``ticks`` ledger:

  * A week with an OPEN tick (closed_at IS NULL) is "in progress". Calling
    ``advance`` again just reports it — a double-fire or a half-failed re-run is
    therefore safe: it lands back on the same open week, and the downstream
    steps (review/forum/export) are themselves upsert-idempotent.
  * Only once a week is CLOSED does ``advance`` move the cursor forward and open
    the next week. The weekly script closes the week after `check` passes.

All writes happen in one transaction managed by the caller (the CLI), so a
crash mid-advance rolls back whole.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import canon


@dataclass
class AdvanceResult:
    action: str          # "opened-current" | "already-open" | "advanced"
    iso_year: int
    iso_week: int
    season: str
    note: str


def season_for_week(week: int) -> str:
    if week <= 9 or week >= 49:
        return "Winter"
    if week <= 22:
        return "Spring"
    if week <= 35:
        return "Summer"
    return "Autumn"


def _arc_line(conn: sqlite3.Connection, iso_year: int, iso_week: int, season: str) -> str:
    """A deterministic, canon-aware arc note (stub for richer logic later)."""
    open_feuds = conn.execute(
        "SELECT COUNT(*) AS n FROM feuds WHERE status IN ('open', 'simmering')"
    ).fetchone()["n"]
    return (
        f"[{iso_year}-W{iso_week:02d}] {season} continues. "
        f"{open_feuds} feud(s) still live; the column presses on."
    )


def advance(conn: sqlite3.Connection) -> AdvanceResult:
    world = canon.get_world(conn)
    cur = canon.get_tick(conn, world.iso_year, world.iso_week)

    # Current week has no ledger row yet → open it without moving the cursor.
    if cur is None:
        canon.open_tick(conn, world.iso_year, world.iso_week)
        conn.execute(
            "UPDATE world_state SET last_tick_at = datetime('now') WHERE id = 1"
        )
        return AdvanceResult(
            "opened-current", world.iso_year, world.iso_week, world.season,
            f"Opened current week {world.iso_year}-W{world.iso_week:02d}.",
        )

    # Current week still open → idempotent no-op (the double-fire / re-run case).
    if cur["closed_at"] is None:
        return AdvanceResult(
            "already-open", world.iso_year, world.iso_week, world.season,
            f"Week {world.iso_year}-W{world.iso_week:02d} is already open; "
            f"re-running downstream steps is safe.",
        )

    # Current week closed → advance the cursor and open the next week.
    ny, nw = canon.next_week(world.iso_year, world.iso_week)
    season = season_for_week(nw)
    canon.open_tick(conn, ny, nw)
    arc_line = _arc_line(conn, ny, nw, season)
    new_notes = (world.arc_notes + "\n" + arc_line).strip()
    conn.execute(
        "UPDATE world_state SET season = ?, iso_year = ?, iso_week = ?, "
        "arc_notes = ?, last_tick_at = datetime('now') WHERE id = 1",
        (season, ny, nw, new_notes),
    )
    return AdvanceResult("advanced", ny, nw, season, arc_line)


def close(conn: sqlite3.Connection) -> tuple[int, int]:
    """Finalize the current week so the next advance may move on. Idempotent."""
    world = canon.get_world(conn)
    canon.close_tick(conn, world.iso_year, world.iso_week)
    return world.iso_year, world.iso_week
