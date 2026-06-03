"""Export the canon store to the Astro content collection.

Each published review becomes one Markdown file with typed YAML frontmatter at
``site/src/content/reviews/<slug>.md``. Frontmatter is emitted as JSON-per-value
(JSON is valid YAML flow syntax) so titles with colons/apostrophes never break
the parser — no PyYAML dependency required.

This is a pure projection: the DB is authoritative, the Markdown is derived. The
Markdown is what gets committed (see README's committed-vs-generated boundary).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from . import canon, db

CONTENT_DIR = db.BACKEND_DIR.parent / "site" / "src" / "content" / "reviews"


def _week_monday(iso_year: int, iso_week: int) -> dt.date:
    """The Monday of the given ISO week (used as the publish date)."""
    try:
        return dt.date.fromisocalendar(iso_year, iso_week, 1)
    except ValueError:
        return dt.date(iso_year, 1, 1)


def _frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def _render_review_md(conn: sqlite3.Connection, review: sqlite3.Row) -> str:
    company = canon.get_company(conn, review["company_id"])
    work = canon.get_work(conn, review["work_id"])
    dancers = canon.review_dancers(conn, review["id"])
    pub = _week_monday(review["iso_year"], review["iso_week"])

    fm = _frontmatter(
        {
            "title": review["title"],
            "company": company["name"],
            "companySlug": company["slug"],
            "work": work["title"],
            "workSlug": work["slug"],
            "dancers": [d["name"] for d in dancers],
            "verdict": review["verdict"],
            "rating": review["rating"],
            "isoYear": review["iso_year"],
            "isoWeek": review["iso_week"],
            "week": f"{review['iso_year']}-W{review['iso_week']:02d}",
            "pubDate": pub.isoformat(),
            # Binary assets stay behind a single frontmatter URL field so they
            # can later move to external hosting with only a base change.
            "audioUrl": None,
        }
    )

    parts = [fm, "", review["body"].strip(), ""]

    # Append any forum discussion for this review as an in-page section.
    thread = conn.execute(
        "SELECT * FROM forum_threads WHERE review_id = ?", (review["id"],)
    ).fetchone()
    if thread is not None:
        posts = conn.execute(
            "SELECT fp.body, p.name AS persona FROM forum_posts fp "
            "JOIN forum_personas p ON p.id = fp.persona_id "
            "WHERE fp.thread_id = ? ORDER BY fp.id",
            (thread["id"],),
        ).fetchall()
        if posts:
            parts.append("---\n")
            parts.append(f"## From the gallery — *{thread['title']}*\n")
            for post in posts:
                parts.append(post["body"].strip())
                parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def export_all(conn: sqlite3.Connection, out_dir: Path = CONTENT_DIR) -> list[str]:
    """Write every published review to Markdown. Returns the slugs written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for review in canon.list_reviews(conn):
        if not review["published"]:
            continue
        md = _render_review_md(conn, review)
        (out_dir / f"{review['slug']}.md").write_text(md, encoding="utf-8")
        written.append(review["slug"])
    return written
