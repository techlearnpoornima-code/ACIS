-- Phase 2 schema additions: Agent 3 (hook profiles) and Agent 4 (performance matrices)

-- Hook profiles — one row per video, produced by Agent 3
CREATE TABLE IF NOT EXISTS hook_profiles (
    video_id            VARCHAR(64) PRIMARY KEY REFERENCES videos(video_id) ON DELETE CASCADE,
    run_id              UUID REFERENCES runs(run_id),
    primary_taxonomy    VARCHAR(32) NOT NULL,
    secondary_taxonomy  VARCHAR(32),
    emotional_intensity INTEGER CHECK (emotional_intensity BETWEEN 1 AND 10),
    certainty_ratio     FLOAT CHECK (certainty_ratio BETWEEN 0 AND 1),
    hype_score          FLOAT CHECK (hype_score BETWEEN 0 AND 1),
    income_claims       JSONB NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hook_profiles_taxonomy
    ON hook_profiles (primary_taxonomy);

CREATE INDEX IF NOT EXISTS idx_hook_profiles_hype
    ON hook_profiles (hype_score DESC);

-- Performance correlation matrices — one row per (run, channel), produced by Agent 4
CREATE TABLE IF NOT EXISTS performance_matrices (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                      UUID NOT NULL REFERENCES runs(run_id),
    channel_id                  VARCHAR(64) REFERENCES channels(channel_id),
    channel_median_velocity     FLOAT,
    velocity_multipliers        JSONB NOT NULL DEFAULT '{}',
    correlations                JSONB NOT NULL DEFAULT '[]',
    breakout_videos             JSONB NOT NULL DEFAULT '[]',
    top_performing_attributes   JSONB NOT NULL DEFAULT '[]',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_perf_matrices_channel_run
    ON performance_matrices (channel_id, run_id);
