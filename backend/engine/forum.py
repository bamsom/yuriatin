"""Forum round: generate (stubbed) persona replies for the week's reviews.

Idempotent by construction: ``forum_posts`` has UNIQUE(thread_id, persona_id),
so re-running a round with INSERT OR IGNORE never doubles a persona's post.
"""

from __future__ import annotations

import sqlite3

from . import canon, generators


def _ensure_thread(conn: sqlite3.Connection, review: sqlite3.Row) -> sqlite3.Row:
    existing = conn.execute(
        "SELECT * FROM forum_threads WHERE review_id = ?", (review["id"],)
    ).fetchone()
    if existing is not None:
        return existing
    slug = f"{review['slug']}-talk"
    conn.execute(
        "INSERT INTO forum_threads (slug, review_id, title, iso_year, iso_week) "
        "VALUES (?, ?, ?, ?, ?)",
        (slug, review["id"], f"Re: {review['title']}", review["iso_year"], review["iso_week"]),
    )
    return conn.execute(
        "SELECT * FROM forum_threads WHERE review_id = ?", (review["id"],)
    ).fetchone()


def run_round(conn: sqlite3.Connection) -> int:
    """Add stub persona replies to every review in the current cursor week.

    Returns the number of new posts written.
    """
    world = canon.get_world(conn)
    reviews = conn.execute(
        "SELECT * FROM reviews WHERE iso_year = ? AND iso_week = ?",
        (world.iso_year, world.iso_week),
    ).fetchall()
    personas = conn.execute("SELECT * FROM forum_personas ORDER BY id").fetchall()

    written = 0
    for review in reviews:
        thread = _ensure_thread(conn, review)
        for reply in generators.generate_forum_replies(review, personas):
            cur = conn.execute(
                "INSERT OR IGNORE INTO forum_posts "
                "(thread_id, persona_id, body, iso_year, iso_week) VALUES (?,?,?,?,?)",
                (thread["id"], reply["persona_id"], reply["body"],
                 world.iso_year, world.iso_week),
            )
            written += cur.rowcount
    return written
