-- 0001_initial.sql — Yuriatin canon schema (normalized, FK-enforced).
-- All mutations flow through the validated CLI; this file only defines shape.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- companies: the rival houses of the fictional ballet world.
-- ---------------------------------------------------------------------------
CREATE TABLE companies (
    id           INTEGER PRIMARY KEY,
    slug         TEXT    NOT NULL UNIQUE,
    name         TEXT    NOT NULL,
    founded_year INTEGER,
    ethos        TEXT,                       -- one-line aesthetic creed
    status       TEXT    NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'grand-faded', 'avant-garde', 'dormant'))
);

-- ---------------------------------------------------------------------------
-- dancers: belong to exactly one company; carry a mutable reputation score.
-- ---------------------------------------------------------------------------
CREATE TABLE dancers (
    id          INTEGER PRIMARY KEY,
    slug        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    rank        TEXT    NOT NULL DEFAULT 'soloist'
                  CHECK (rank IN ('principal', 'soloist', 'corps', 'guest', 'retired')),
    reputation  INTEGER NOT NULL DEFAULT 50 CHECK (reputation BETWEEN 0 AND 100),
    debut_year  INTEGER
);

-- ---------------------------------------------------------------------------
-- works: the choreographic repertoire that gets staged and reviewed.
-- ---------------------------------------------------------------------------
CREATE TABLE works (
    id            INTEGER PRIMARY KEY,
    slug          TEXT    NOT NULL UNIQUE,
    title         TEXT    NOT NULL,
    choreographer TEXT,
    premiere_year INTEGER,
    kind          TEXT    NOT NULL DEFAULT 'ballet'
                    CHECK (kind IN ('ballet', 'mixed-bill', 'gala', 'experimental'))
);

-- ---------------------------------------------------------------------------
-- reviews: the weekly column. FK to the house + the work under review.
-- A published verdict is immutable canon (enforced in CLI + `check`).
-- ---------------------------------------------------------------------------
CREATE TABLE reviews (
    id          INTEGER PRIMARY KEY,
    slug        TEXT    NOT NULL UNIQUE,        -- stable id, also the export filename
    company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    work_id     INTEGER NOT NULL REFERENCES works(id)     ON DELETE RESTRICT,
    title       TEXT    NOT NULL,
    verdict     TEXT    NOT NULL
                  CHECK (verdict IN ('rave', 'admiring', 'mixed', 'cool', 'pan')),
    rating      REAL    NOT NULL CHECK (rating BETWEEN 0 AND 5),  -- stars, .5 steps
    iso_year    INTEGER NOT NULL,
    iso_week    INTEGER NOT NULL CHECK (iso_week BETWEEN 1 AND 53),
    body        TEXT    NOT NULL,               -- the prose (LLM-authored later)
    published   INTEGER NOT NULL DEFAULT 1 CHECK (published IN (0, 1)),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- many-to-many: which dancers a review actually discusses. Each must pre-exist.
CREATE TABLE review_dancers (
    review_id  INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    dancer_id  INTEGER NOT NULL REFERENCES dancers(id) ON DELETE RESTRICT,
    PRIMARY KEY (review_id, dancer_id)
);

-- ---------------------------------------------------------------------------
-- feuds: running antagonisms between dancers and/or houses. Drives arcs.
-- At least one "a_" party and one "b_" party should be set (checked by CLI).
-- ---------------------------------------------------------------------------
CREATE TABLE feuds (
    id              INTEGER PRIMARY KEY,
    slug            TEXT    NOT NULL UNIQUE,
    topic           TEXT    NOT NULL,
    a_dancer_id     INTEGER REFERENCES dancers(id)   ON DELETE SET NULL,
    b_dancer_id     INTEGER REFERENCES dancers(id)   ON DELETE SET NULL,
    a_company_id    INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    b_company_id    INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    intensity       INTEGER NOT NULL DEFAULT 1 CHECK (intensity BETWEEN 1 AND 5),
    status          TEXT    NOT NULL DEFAULT 'simmering'
                      CHECK (status IN ('simmering', 'open', 'cooled', 'resolved')),
    started_iso_year INTEGER NOT NULL,
    started_iso_week INTEGER NOT NULL
);

-- ---------------------------------------------------------------------------
-- forum: reader/persona discussion attached (optionally) to a review.
-- ---------------------------------------------------------------------------
CREATE TABLE forum_personas (
    id     INTEGER PRIMARY KEY,
    slug   TEXT NOT NULL UNIQUE,
    name   TEXT NOT NULL,
    stance TEXT                                -- short character note
);

CREATE TABLE forum_threads (
    id         INTEGER PRIMARY KEY,
    slug       TEXT    NOT NULL UNIQUE,
    review_id  INTEGER REFERENCES reviews(id) ON DELETE CASCADE,
    title      TEXT    NOT NULL,
    iso_year   INTEGER NOT NULL,
    iso_week   INTEGER NOT NULL
);

CREATE TABLE forum_posts (
    id         INTEGER PRIMARY KEY,
    thread_id  INTEGER NOT NULL REFERENCES forum_threads(id) ON DELETE CASCADE,
    persona_id INTEGER NOT NULL REFERENCES forum_personas(id) ON DELETE RESTRICT,
    body       TEXT    NOT NULL,
    iso_year   INTEGER NOT NULL,
    iso_week   INTEGER NOT NULL,
    UNIQUE (thread_id, persona_id)             -- one post per persona per round
);

-- ---------------------------------------------------------------------------
-- ticks: ledger of weekly batches. Drives the idempotency guard.
--   a row with closed_at IS NULL  => week is "open" / in progress
--   a row with closed_at set      => week finalized; advance may move on
-- ---------------------------------------------------------------------------
CREATE TABLE ticks (
    iso_year  INTEGER NOT NULL,
    iso_week  INTEGER NOT NULL,
    opened_at TEXT    NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT,
    PRIMARY KEY (iso_year, iso_week)
);

-- ---------------------------------------------------------------------------
-- world_state: singleton (id is pinned to 1) holding the season arc cursor.
-- ---------------------------------------------------------------------------
CREATE TABLE world_state (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    season       TEXT    NOT NULL,
    iso_year     INTEGER NOT NULL,
    iso_week     INTEGER NOT NULL,
    arc_notes    TEXT    NOT NULL DEFAULT '',
    last_tick_at TEXT
);

CREATE INDEX idx_reviews_company ON reviews(company_id);
CREATE INDEX idx_reviews_work    ON reviews(work_id);
CREATE INDEX idx_reviews_week    ON reviews(iso_year, iso_week);
CREATE INDEX idx_dancers_company ON dancers(company_id);
