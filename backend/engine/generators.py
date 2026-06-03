"""STUBBED creative generation.

In a later phase these functions call the Anthropic API to write the only
LLM-authored content in the system: review prose and forum replies. For now
they return deterministic placeholder text so the whole pipeline (validation,
DB writes, frontmatter, git) can be exercised without any network or API key.

The signatures already take the *canon context* the real prompts will need, so
wiring the model in later is a body swap, not a plumbing change. Keep ALL
bookkeeping out of here — these functions return strings, nothing else.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import canon

STUB_BANNER = "<!-- STUB PROSE — no LLM wired yet (Phase 1). -->"


@dataclass
class ReviewContext:
    """Everything the (future) prompt needs to write a review in-continuity."""

    company: sqlite3.Row
    work: sqlite3.Row
    dancers: list[sqlite3.Row]
    iso_year: int
    iso_week: int
    season: str
    prior_reviews: list[sqlite3.Row] = field(default_factory=list)
    arc_notes: str = ""


def build_review_context(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    work_id: int,
    dancer_ids: list[int],
) -> ReviewContext:
    """Pull the relevant past canon a review must stay consistent with."""
    world = canon.get_world(conn)
    return ReviewContext(
        company=canon.get_company(conn, company_id),
        work=canon.get_work(conn, work_id),
        dancers=[canon.get_dancer(conn, d) for d in dancer_ids],
        iso_year=world.iso_year,
        iso_week=world.iso_week,
        season=world.season,
        prior_reviews=canon.reviews_for(conn, company_id, work_id),
        arc_notes=world.arc_notes,
    )


def generate_review(ctx: ReviewContext) -> dict:
    """STUB: return a review dict (title, verdict, rating, body).

    Deterministic so tests/dry-runs are reproducible. References real canon so
    the placeholder still reads as continuity-aware.
    """
    dancer_names = ", ".join(d["name"] for d in ctx.dancers) or "the company"
    continuity = ""
    if ctx.prior_reviews:
        last = ctx.prior_reviews[-1]
        continuity = (
            f" Last time this column met {ctx.company['name']}'s {ctx.work['title']} "
            f"(week {last['iso_week']}), the verdict was '{last['verdict']}'."
        )

    body = (
        f"{STUB_BANNER}\n\n"
        f"On the {ctx.season} bill, {ctx.company['name']} returns to "
        f"*{ctx.work['title']}*. Tonight the eye goes to {dancer_names}."
        f"{continuity}\n\n"
        f"[Placeholder body for {ctx.iso_year}-W{ctx.iso_week:02d}. The real "
        f"prose is the one thing that will come from the model in a later phase; "
        f"everything around it — the verdict, the rating, the canon links — is "
        f"deterministic bookkeeping.]"
    )
    return {
        "title": f"{ctx.company['name']}'s {ctx.work['title']}: A Provisional Notice",
        "verdict": "mixed",      # safe default: never reverses prior canon
        "rating": 3.0,
        "body": body,
    }


def generate_forum_replies(
    review: sqlite3.Row, personas: list[sqlite3.Row]
) -> list[dict]:
    """STUB: one placeholder reply per persona, in voice-stub form."""
    replies = []
    for p in personas:
        replies.append(
            {
                "persona_id": p["id"],
                "body": (
                    f"{STUB_BANNER}\n\n**{p['name']}** ({p['stance']}): "
                    f"[Placeholder reply to \"{review['title']}\". The real reply "
                    f"is LLM-authored later; this stub just proves the thread, the "
                    f"persona link, and the one-post-per-round rule all hold.]"
                ),
            }
        )
    return replies
