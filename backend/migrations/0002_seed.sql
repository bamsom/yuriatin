-- 0002_seed.sql — a small, believable starting world.
-- Idempotent-ish: uses fixed ids so a re-applied migration is a no-op via the
-- migration ledger. The seeded week (2026-W21) is recorded as a CLOSED tick so
-- the very first `world advance` opens the *next* week (W22).

PRAGMA foreign_keys = ON;

-- --- companies ---------------------------------------------------------------
INSERT INTO companies (id, slug, name, founded_year, ethos, status) VALUES
  (1, 'vesper-ballet',       'Vesper Ballet',        1898,
     'Tradition is not nostalgia; it is discipline.', 'grand-faded'),
  (2, 'theatre-des-ombres',  'Théâtre des Ombres',   2009,
     'Light lies; we dance the shadow.',              'avant-garde'),
  (3, 'meridian-civic',      'Meridian Civic Ballet',1974,
     'Ballet for the whole city.',                    'active');

-- --- dancers -----------------------------------------------------------------
INSERT INTO dancers (id, slug, name, company_id, rank, reputation, debut_year) VALUES
  (1, 'odile-varga',    'Odile Varga',     1, 'principal', 78, 2007),
  (2, 'mathis-roux',    'Mathis Roux',     1, 'principal', 71, 2011),
  (3, 'lena-sorokin',   'Lena Sorokin',    1, 'soloist',   60, 2016),
  (4, 'cassiel-mor',    'Cassiel Mör',     2, 'principal', 66, 2013),
  (5, 'ivo-banek',      'Ivo Banek',       2, 'soloist',   52, 2018),
  (6, 'prima-okonkwo',  'Prima Okonkwo',   3, 'principal', 69, 2010),
  (7, 'jun-pal',        'Jun Pal',         3, 'corps',     45, 2021);

-- --- works -------------------------------------------------------------------
INSERT INTO works (id, slug, title, choreographer, premiere_year, kind) VALUES
  (1, 'the-winter-pavilion', 'The Winter Pavilion', 'Anton Vesper',        1931, 'ballet'),
  (2, 'glasswing',           'Glasswing',           'Cassiel Mör',         2019, 'experimental'),
  (3, 'giselle',             'Giselle',             'Coralli / Perrot',    1841, 'ballet'),
  (4, 'city-of-doors',       'City of Doors',       'Prima Okonkwo',       2022, 'mixed-bill');

-- --- feuds -------------------------------------------------------------------
INSERT INTO feuds (id, slug, topic, a_dancer_id, b_dancer_id,
                   a_company_id, b_company_id, intensity, status,
                   started_iso_year, started_iso_week) VALUES
  (1, 'the-shadow-doctrine',
      'Whether the classical line is obsolete in a post-Glasswing age',
      1, 4, 1, 2, 3, 'open', 2026, 12);

-- --- forum personas ----------------------------------------------------------
INSERT INTO forum_personas (id, slug, name, stance) VALUES
  (1, 'balcony-standee', 'Balcony Standee', 'Decades-long subscriber; mourns the gold-leaf era.'),
  (2, 'the-ergonomist',  'The Ergonomist',  'Dance-science pedant; argues in turnout and load curves.'),
  (3, 'gods-gallery',    'Gods Gallery',    'Cheap-seat firebrand; lives for the avant-garde.');

-- --- the one example PAST review (continuity anchor) -------------------------
INSERT INTO reviews (id, slug, company_id, work_id, title, verdict, rating,
                     iso_year, iso_week, body, published, created_at) VALUES
  (1, '2026-w21-vesper-ballet-giselle', 1, 3,
      'Vesper''s Giselle: A Mausoleum Still Breathing',
      'admiring', 3.5, 2026, 21,
      'There is a particular courage in mounting Giselle when half the house has '
      || 'seen you do it forty times. Vesper Ballet does not flinch. Odile Varga''s '
      || 'Act II is all restraint — a wilis who remembers being warm — and Lena '
      || 'Sorokin, in her first season of real responsibility, dances the peasant '
      || 'pas as though the floor might forgive her. It is not new. It does not try '
      || 'to be. But a mausoleum, kept this well, still breathes.',
      1, '2026-05-25 19:30:00');

INSERT INTO review_dancers (review_id, dancer_id) VALUES
  (1, 1),   -- Odile Varga
  (1, 3);   -- Lena Sorokin

-- a seeded discussion thread for that review (posts are added by `forum round`)
INSERT INTO forum_threads (id, slug, review_id, title, iso_year, iso_week) VALUES
  (1, '2026-w21-giselle-talk', 1,
      'Re: Vesper''s Giselle — is "still breathing" damning with faint praise?',
      2026, 21);

-- --- the season-arc cursor + a CLOSED seeded tick ----------------------------
INSERT INTO world_state (id, season, iso_year, iso_week, arc_notes, last_tick_at) VALUES
  (1, 'Spring', 2026, 21,
   '[2026-W21] Season opens under the long shadow of the Shadow Doctrine feud. '
   || 'Vesper leans on heritage; Ombres dares the city to outgrow it.',
   '2026-05-25 20:00:00');

INSERT INTO ticks (iso_year, iso_week, opened_at, closed_at) VALUES
  (2026, 21, '2026-05-25 08:00:00', '2026-05-25 20:00:00');
