"""Canon integrity pass.

Returns a list of human-readable problems. The CLI exits non-zero when the list
is non-empty, so CI can gate a PR on a clean canon. Checks:

  * dangling foreign keys (PRAGMA foreign_key_check)
  * contradicted verdicts (a published rave vs pan on the same house+work)
  * reviewed dancers that don't exist (belt-and-suspenders over the FK)
  * broken arc state (missing/!=1 world_state, week out of range, no open or
    closed tick for the cursor week, reviews dated ahead of the cursor)
  * feuds with no parties on either side
"""

from __future__ import annotations

import sqlite3

from . import canon


def run_checks(conn: sqlite3.Connection) -> list[str]:
    problems: list[str] = []

    # --- dangling FKs --------------------------------------------------------
    for row in conn.execute("PRAGMA foreign_key_check").fetchall():
        problems.append(
            f"dangling FK: table '{row[0]}' rowid {row[1]} -> missing '{row[2]}'"
        )

    # --- world_state singleton ----------------------------------------------
    rows = conn.execute("SELECT * FROM world_state").fetchall()
    if len(rows) != 1 or rows[0]["id"] != 1:
        problems.append("world_state must hold exactly one row with id=1")
        return problems  # nothing else is meaningful without a world cursor
    world = canon.get_world(conn)
    if not (1 <= world.iso_week <= 53):
        problems.append(f"world_state iso_week {world.iso_week} out of range")

    # --- the cursor week must have a tick row -------------------------------
    if canon.get_tick(conn, world.iso_year, world.iso_week) is None:
        problems.append(
            f"broken arc: no tick ledger row for cursor week "
            f"{world.iso_year}-W{world.iso_week:02d}"
        )

    # --- reviews dated ahead of the cursor ----------------------------------
    for r in conn.execute("SELECT slug, iso_year, iso_week FROM reviews"):
        if (r["iso_year"], r["iso_week"]) > (world.iso_year, world.iso_week):
            problems.append(
                f"review '{r['slug']}' is dated {r['iso_year']}-W{r['iso_week']:02d}, "
                f"ahead of the world cursor"
            )

    # --- reviewed dancers exist ---------------------------------------------
    orphan_dancers = conn.execute(
        "SELECT rd.review_id, rd.dancer_id FROM review_dancers rd "
        "LEFT JOIN dancers d ON d.id = rd.dancer_id WHERE d.id IS NULL"
    ).fetchall()
    for o in orphan_dancers:
        problems.append(
            f"review id {o['review_id']} cites non-existent dancer id {o['dancer_id']}"
        )

    # --- contradicted verdicts ----------------------------------------------
    pairs = conn.execute(
        "SELECT DISTINCT company_id, work_id FROM reviews WHERE published = 1"
    ).fetchall()
    for pair in pairs:
        reviews = canon.reviews_for(conn, pair["company_id"], pair["work_id"])
        for i in range(len(reviews)):
            for j in range(i + 1, len(reviews)):
                if canon.verdict_contradicts(reviews[i]["verdict"], reviews[j]["verdict"]):
                    problems.append(
                        f"contradicted verdict: '{reviews[i]['slug']}' "
                        f"({reviews[i]['verdict']}) vs '{reviews[j]['slug']}' "
                        f"({reviews[j]['verdict']})"
                    )

    # --- feuds need at least one party on each side -------------------------
    for f in conn.execute("SELECT * FROM feuds"):
        side_a = f["a_dancer_id"] or f["a_company_id"]
        side_b = f["b_dancer_id"] or f["b_company_id"]
        if not side_a or not side_b:
            problems.append(f"feud '{f['slug']}' is missing a party on one side")

    return problems
