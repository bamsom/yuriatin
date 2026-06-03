"""Yuriatin canon CLI — the *only* sanctioned door to canon mutations.

Every subcommand validates references before writing and runs inside a single
transaction that the global ``--dry-run`` flag rolls back. Creative prose comes
from the (currently stubbed) generators; all bookkeeping here is deterministic.

Run as:  python -m engine <command> ...    (from the backend/ dir)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from . import canon, check as check_mod, db, export as export_mod, forum, generators, world

app = typer.Typer(
    add_completion=False,
    help="Yuriatin canon store — validated mutations for the fictional ballet world.",
    no_args_is_help=True,
)
world_app = typer.Typer(no_args_is_help=True, help="Season-arc / world-state.")
review_app = typer.Typer(no_args_is_help=True, help="Reviews (the weekly column).")
rep_app = typer.Typer(no_args_is_help=True, help="Dancer reputations.")
forum_app = typer.Typer(no_args_is_help=True, help="Reader forum.")
app.add_typer(world_app, name="world")
app.add_typer(review_app, name="review")
app.add_typer(rep_app, name="rep")
app.add_typer(forum_app, name="forum")


@dataclass
class State:
    dry_run: bool = False
    db_path: Path = db.DEFAULT_DB_PATH


STATE = State()


@app.callback()
def main(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Generate + print the diff, mutate nothing."
    ),
    db_path: Path = typer.Option(
        db.DEFAULT_DB_PATH, "--db", help="Path to the canon SQLite file."
    ),
) -> None:
    STATE.dry_run = dry_run
    STATE.db_path = db_path


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _conn():
    return db.connect(STATE.db_path)


def _finalize(conn) -> None:
    """Commit, or roll back under --dry-run."""
    if STATE.dry_run:
        conn.rollback()
        typer.secho("  [dry-run] rolled back — no changes written.", fg=typer.colors.YELLOW)
    else:
        conn.commit()


def _fail(msg: str) -> None:
    typer.secho(f"error: {msg}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


# --------------------------------------------------------------------------- #
# init / status
# --------------------------------------------------------------------------- #
@app.command()
def init() -> None:
    """Create the DB and apply all pending migrations (incl. the seed)."""
    conn = _conn()
    applied = db.run_migrations(conn)
    if applied:
        typer.echo("Applied migrations:\n  " + "\n  ".join(applied))
    else:
        typer.echo("No pending migrations — canon schema is up to date.")
    conn.close()


# --------------------------------------------------------------------------- #
# world
# --------------------------------------------------------------------------- #
@world_app.command("show")
def world_show() -> None:
    """Print the current season-arc cursor."""
    conn = _conn()
    w = canon.get_world(conn)
    typer.echo(
        f"{w.season} — {w.iso_year}-W{w.iso_week:02d}\n"
        f"last tick: {w.last_tick_at}\n"
        f"arc notes:\n{w.arc_notes}"
    )
    conn.close()


@world_app.command("cursor")
def world_cursor() -> None:
    """Print just the cursor week as YYYY-Www (for scripts)."""
    conn = _conn()
    w = canon.get_world(conn)
    typer.echo(f"{w.iso_year}-W{w.iso_week:02d}")
    conn.close()


@world_app.command("advance")
def world_advance() -> None:
    """Tick the season/week forward (idempotent + transactional)."""
    conn = _conn()
    try:
        res = world.advance(conn)
    except canon.CanonError as e:
        _fail(str(e))
    typer.secho(f"{res.action}: {res.note}", fg=typer.colors.GREEN)
    _finalize(conn)
    conn.close()


@world_app.command("close")
def world_close() -> None:
    """Finalize the current week so the next advance may move on (idempotent)."""
    conn = _conn()
    y, wk = world.close(conn)
    typer.secho(f"closed week {y}-W{wk:02d}", fg=typer.colors.GREEN)
    _finalize(conn)
    conn.close()


# --------------------------------------------------------------------------- #
# review
# --------------------------------------------------------------------------- #
def _auto_subject(conn) -> tuple[int, int, list[int]]:
    """Deterministically pick a house, work, and its two top dancers for the week."""
    w = canon.get_world(conn)
    companies = canon.list_companies(conn)
    works = conn.execute("SELECT * FROM works ORDER BY id").fetchall()
    company = companies[w.iso_week % len(companies)]
    work = works[w.iso_week % len(works)]
    dancers = sorted(
        canon.list_dancers(conn, company["id"]), key=lambda r: -r["reputation"]
    )
    return company["id"], work["id"], [d["id"] for d in dancers[:2]]


@review_app.command("new")
def review_new(
    company_id: int = typer.Option(None, "--company-id", help="House under review."),
    work_id: int = typer.Option(None, "--work-id", help="Work staged."),
    dancer: list[int] = typer.Option(
        None, "--dancer", help="Dancer id discussed (repeatable). Must exist."
    ),
) -> None:
    """Pull past canon, run the (stubbed) generator, validate, write + export."""
    conn = _conn()
    try:
        if company_id is None or work_id is None:
            company_id, work_id, dancer = _auto_subject(conn)
        dancer = dancer or []

        ctx = generators.build_review_context(
            conn, company_id=company_id, work_id=work_id, dancer_ids=dancer
        )
        draft = generators.generate_review(ctx)  # stub prose + verdict + rating
        w = canon.get_world(conn)
        slug = f"{w.iso_year}-w{w.iso_week:02d}-{ctx.company['slug']}-{ctx.work['slug']}"

        review_id = canon.insert_review(
            conn,
            slug=slug,
            company_id=company_id,
            work_id=work_id,
            title=draft["title"],
            verdict=draft["verdict"],
            rating=draft["rating"],
            iso_year=w.iso_year,
            iso_week=w.iso_week,
            body=draft["body"],
            dancer_ids=dancer,
        )
    except canon.CanonError as e:
        conn.rollback()
        _fail(str(e))

    review_row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    typer.secho(
        f"review '{slug}' — {draft['verdict']} ({draft['rating']}★)",
        fg=typer.colors.GREEN,
    )

    if STATE.dry_run:
        typer.echo("  [dry-run] would export Markdown:\n")
        typer.echo(export_mod._render_review_md(conn, review_row))
    else:
        md = export_mod._render_review_md(conn, review_row)
        path = export_mod.CONTENT_DIR
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{slug}.md").write_text(md, encoding="utf-8")
        typer.echo(f"  exported {path / (slug + '.md')}")

    _finalize(conn)
    conn.close()


# --------------------------------------------------------------------------- #
# rep
# --------------------------------------------------------------------------- #
@rep_app.command("adjust")
def rep_adjust(
    dancer_id: int = typer.Argument(..., help="Dancer id (must exist)."),
    delta: int = typer.Argument(
        ..., help="Signed change, e.g. 5 or -5 (put '--' before a negative)."
    ),
) -> None:
    """Nudge a dancer's reputation. Refuses an unknown dancer id."""
    conn = _conn()
    try:
        new_rep = canon.adjust_reputation(conn, dancer_id, delta)
    except canon.CanonError as e:
        conn.rollback()
        _fail(str(e))
    name = canon.get_dancer(conn, dancer_id)["name"]
    typer.secho(f"{name}: reputation -> {new_rep} ({delta:+d})", fg=typer.colors.GREEN)
    _finalize(conn)
    conn.close()


# --------------------------------------------------------------------------- #
# forum
# --------------------------------------------------------------------------- #
@forum_app.command("round")
def forum_round() -> None:
    """Generate (stubbed) persona replies for this week's reviews."""
    conn = _conn()
    written = forum.run_round(conn)
    typer.secho(f"forum round: {written} new post(s)", fg=typer.colors.GREEN)
    _finalize(conn)
    conn.close()


# --------------------------------------------------------------------------- #
# export / check
# --------------------------------------------------------------------------- #
@app.command()
def export() -> None:
    """Project the canon store to the Astro content collection (Markdown)."""
    conn = _conn()
    if STATE.dry_run:
        slugs = [r["slug"] for r in canon.list_reviews(conn) if r["published"]]
        typer.echo("[dry-run] would export:\n  " + "\n  ".join(slugs))
    else:
        written = export_mod.export_all(conn)
        typer.secho(f"exported {len(written)} review(s) to {export_mod.CONTENT_DIR}",
                    fg=typer.colors.GREEN)
    conn.close()


@app.command()
def check() -> None:
    """Integrity pass. Exits non-zero if the canon is broken."""
    conn = _conn()
    problems = check_mod.run_checks(conn)
    conn.close()
    if problems:
        typer.secho(f"check FAILED — {len(problems)} problem(s):", fg=typer.colors.RED, err=True)
        for p in problems:
            typer.secho(f"  - {p}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho("check OK — canon is consistent.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
