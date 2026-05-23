-- Phase 3 schema additions: topic drift, opportunity vectors, strategic briefs, prediction outcomes

-- Topic salience time-series — one row per (run, channel, topic) for drift tracking (FR-3.3)
CREATE TABLE IF NOT EXISTS topic_salience_series (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID REFERENCES runs(run_id),
    channel_id      VARCHAR(64) REFERENCES channels(channel_id),
    topic           TEXT NOT NULL,
    salience        FLOAT NOT NULL,
    delta           FLOAT,           -- salience delta vs previous run for this (channel, topic)
    velocity_slope  FLOAT,           -- 3-run linear slope; positive = rising
    run_timestamp   TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_topic_salience_ch_topic_ts
    ON topic_salience_series (channel_id, topic, run_timestamp);

-- Opportunity vectors — one row per run, produced by Agent 5
CREATE TABLE IF NOT EXISTS opportunity_vectors (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES runs(run_id),
    opportunities       JSONB NOT NULL DEFAULT '[]',
    channels_analyzed   INTEGER,
    videos_analyzed     INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id)
);

-- Strategic briefs — one row per run, produced by Agent 6
CREATE TABLE IF NOT EXISTS strategic_briefs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES runs(run_id),
    run_date        DATE NOT NULL,
    brief_markdown  TEXT NOT NULL,
    brief_data      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id)
);

-- Prediction outcomes — contrastive memory supplement to MEMORY.md (FR-3.1)
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    belief_statement    TEXT NOT NULL,
    run_id              UUID REFERENCES runs(run_id),
    predicted_at        TIMESTAMPTZ NOT NULL,
    outcome_observed_at TIMESTAMPTZ,
    outcome_type        VARCHAR(32),  -- 'confirmed' | 'refuted' | 'indeterminate'
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_type
    ON prediction_outcomes (outcome_type);
