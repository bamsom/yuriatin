"""Validated access to the canon store.

This module is the *only* place that knows how to read and mutate canon rows,
and it refuses to write anything that would violate a world invariant:

  * every reviewed dancer must already exist  (no inventing people mid-review)
  * a published verdict is immutable canon     (no silent reversals)
  * references must resolve                     (no dangling company/work ids)

The CLI calls these functions; it never writes SQL itself.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

# Verdict vocabulary, ordered worst -> best, with a numeric sign used to detect
# continuity-breaking reversals.
VERDICT_SCALE = {"pan": -2, "cool": -1, "mixed": 0, "admiring": 1, "rave": 2}


class CanonError(Exception):
    """Raised when a requested mutation would violate a canon invariant."""


@dataclass
class WorldState:
    season: str
    iso_year: int
    iso_week: int
    arc_notes: str
    last_tick_at: str | None


# --------------------------------------------------------------------------- #
# Lookups (raise CanonError on miss so callers get a clean refusal message).
# --------------------------------------------------------------------------- #
def get_world(conn: sqlite3.Connection) -> WorldState:
    row = conn.execute("SELECT * FROM world_state WHERE id = 1").fetchone()
    if row is None:
        raise CanonError("world_state is empty — has the seed migration run?")
    return WorldState(
        season=row["season"],
        iso_year=row["iso_year"],
        iso_week=row["iso_week"],
        arc_notes=row["arc_notes"],
        last_tick_at=row["last_tick_at"],
    )


def get_company(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if row is None:
        raise CanonError(f"no company with id={company_id}")
    return row


def get_work(conn: sqlite3.Connection, work_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
    if row is None:
        raise CanonError(f"no work with id={work_id}")
    return row


def get_dancer(conn: sqlite3.Connection, dancer_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM dancers WHERE id = ?", (dancer_id,)).fetchone()
    if row is None:
        raise CanonError(f"no dancer with id={dancer_id}")
    return row


def list_companies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM companies ORDER BY id").fetchall()


def list_dancers(conn: sqlite3.Connection, company_id: int | None = None) -> list[sqlite3.Row]:
    if company_id is None:
        return conn.execute("SELECT * FROM dancers ORDER BY id").fetchall()
    return conn.execute(
        "SELECT * FROM dancers WHERE company_id = ? ORDER BY id", (company_id,)
    ).fetchall()


def list_reviews(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM reviews ORDER BY iso_year DESC, iso_week DESC, id DESC"
    ).fetchall()


def reviews_for(conn: sqlite3.Connection, company_id: int, work_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM reviews WHERE company_id = ? AND work_id = ? "
        "AND published = 1 ORDER BY iso_year, iso_week",
        (company_id, work_id),
    ).fetchall()


def review_dancers(conn: sqlite3.Connection, review_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT d.* FROM dancers d JOIN review_dancers rd ON rd.dancer_id = d.id "
        "WHERE rd.review_id = ? ORDER BY d.id",
        (review_id,),
    ).fetchall()


# --------------------------------------------------------------------------- #
# Week arithmetic (Phase-1 simplification: 52-week years).
# --------------------------------------------------------------------------- #
def next_week(iso_year: int, iso_week: int) -> tuple[int, int]:
    if iso_week >= 52:
        return iso_year + 1, 1
    return iso_year, iso_week + 1


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


# --------------------------------------------------------------------------- #
# Contradiction guard.
# --------------------------------------------------------------------------- #
def verdict_contradicts(prior: str, proposed: str) -> bool:
    """True if proposed reverses a prior published verdict (rave<->pan polarity)."""
    a, b = VERDICT_SCALE[prior], VERDICT_SCALE[proposed]
    return (a >= 1 and b <= -1) or (a <= -1 and b >= 1)


def assert_no_verdict_reversal(
    conn: sqlite3.Connection, company_id: int, work_id: int, proposed_verdict: str
) -> None:
    for prior in reviews_for(conn, company_id, work_id):
        if verdict_contradicts(prior["verdict"], proposed_verdict):
            raise CanonError(
                f"proposed verdict '{proposed_verdict}' reverses published verdict "
                f"'{prior['verdict']}' in review '{prior['slug']}' — published "
                f"canon is immutable; refusing to contradict it."
            )


# --------------------------------------------------------------------------- #
# Mutations. Callers manage the transaction (the CLI wraps these so --dry-run
# can roll back). Each validates references before writing.
# --------------------------------------------------------------------------- #
def adjust_reputation(conn: sqlite3.Connection, dancer_id: int, delta: int) -> int:
    dancer = get_dancer(conn, dancer_id)  # raises if unknown
    new_rep = max(0, min(100, dancer["reputation"] + delta))
    conn.execute("UPDATE dancers SET reputation = ? WHERE id = ?", (new_rep, dancer_id))
    return new_rep


def insert_review(
    conn: sqlite3.Connection,
    *,
    slug: str,
    company_id: int,
    work_id: int,
    title: str,
    verdict: str,
    rating: float,
    iso_year: int,
    iso_week: int,
    body: str,
    dancer_ids: list[int],
) -> int:
    if verdict not in VERDICT_SCALE:
        raise CanonError(f"unknown verdict '{verdict}'")
    get_company(conn, company_id)  # validate FK targets up front
    get_work(conn, work_id)
    for did in dancer_ids:
        get_dancer(conn, did)  # "every reviewed dancer must exist first"
    assert_no_verdict_reversal(conn, company_id, work_id, verdict)

    existing = conn.execute("SELECT id FROM reviews WHERE slug = ?", (slug,)).fetchone()
    if existing is not None:
        # idempotent re-run within the same week: keep the published row as-is.
        return existing["id"]

    cur = conn.execute(
        "INSERT INTO reviews (slug, company_id, work_id, title, verdict, rating, "
        "iso_year, iso_week, body, published) VALUES (?,?,?,?,?,?,?,?,?,1)",
        (slug, company_id, work_id, title, verdict, rating, iso_year, iso_week, body),
    )
    review_id = cur.lastrowid
    for did in dancer_ids:
        conn.execute(
            "INSERT OR IGNORE INTO review_dancers (review_id, dancer_id) VALUES (?, ?)",
            (review_id, did),
        )
    return review_id


# --------------------------------------------------------------------------- #
# Tick ledger helpers (idempotency for the weekly batch).
# --------------------------------------------------------------------------- #
def get_tick(conn: sqlite3.Connection, iso_year: int, iso_week: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM ticks WHERE iso_year = ? AND iso_week = ?", (iso_year, iso_week)
    ).fetchone()


def open_tick(conn: sqlite3.Connection, iso_year: int, iso_week: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO ticks (iso_year, iso_week) VALUES (?, ?)",
        (iso_year, iso_week),
    )


def close_tick(conn: sqlite3.Connection, iso_year: int, iso_week: int) -> None:
    conn.execute(
        "UPDATE ticks SET closed_at = datetime('now') "
        "WHERE iso_year = ? AND iso_week = ? AND closed_at IS NULL",
        (iso_year, iso_week),
    )
