-- Bayesian belief store: persists ACIS strategic beliefs across runs.
-- Replaces output/memory.md as the authoritative store when DATABASE_URL is set.
CREATE TABLE IF NOT EXISTS beliefs (
    belief_id       VARCHAR(64)  PRIMARY KEY,
    statement       TEXT         NOT NULL,
    confidence      FLOAT        NOT NULL DEFAULT 0.5,
    evidence_count  INTEGER      NOT NULL DEFAULT 0,
    last_confirmed  DATE         NOT NULL,
    half_life_days  INTEGER      NOT NULL DEFAULT 60,
    tags            TEXT[]       NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);
