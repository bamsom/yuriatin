"""Connection handling + a tiny forward-only migration runner.

Migrations are plain numbered ``.sql`` files in ``backend/migrations``. A
``schema_migrations`` ledger records which have been applied so re-running is a
no-op. Each file is applied inside its own transaction; a failure rolls back
that file cleanly, leaving the ledger honest.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Resolve paths relative to this file so the CLI works from any cwd.
BACKEND_DIR = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
DEFAULT_DB_PATH = BACKEND_DIR / "canon.db"


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and row access by name."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _ensure_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    _ensure_ledger(conn)
    return {r["filename"] for r in conn.execute("SELECT filename FROM schema_migrations")}


def pending_migrations(conn: sqlite3.Connection) -> list[Path]:
    done = applied_migrations(conn)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.name not in done]


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply every pending migration in filename order. Returns names applied."""
    _ensure_ledger(conn)
    applied: list[str] = []
    for path in pending_migrations(conn):
        sql = path.read_text(encoding="utf-8")
        # `with conn` commits on success / rolls back on any exception, so a
        # broken migration leaves neither orphan tables nor a stale ledger row.
        with conn:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,)
            )
        applied.append(path.name)
    return applied
