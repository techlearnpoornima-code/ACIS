CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS channels (
    channel_id          VARCHAR(64) PRIMARY KEY,
    handle              VARCHAR(128),
    display_name        VARCHAR(256),
    subscriber_count    INTEGER,
    first_ingested_at   TIMESTAMPTZ,
    last_ingested_at    TIMESTAMPTZ,
    median_velocity_30d FLOAT,
    metadata            JSONB
);

CREATE TABLE IF NOT EXISTS runs (
    run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    status              VARCHAR(32),
    channels_processed  INTEGER,
    videos_processed    INTEGER,
    videos_skipped      INTEGER,
    total_input_tokens  INTEGER,
    total_output_tokens INTEGER,
    config_snapshot     JSONB
);

CREATE TABLE IF NOT EXISTS videos (
    video_id            VARCHAR(64) PRIMARY KEY,
    channel_id          VARCHAR(64) REFERENCES channels(channel_id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    description         TEXT,
    upload_date         DATE NOT NULL,
    duration_seconds    INTEGER,
    view_count          INTEGER,
    like_count          INTEGER,
    comment_count       INTEGER,          -- NULL when comments are disabled on the video
    thumbnail_path      TEXT,
    transcript_status   VARCHAR(32),      -- 'api' | 'whisper' | 'unavailable'
    ingested_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transcripts (
    video_id            VARCHAR(64) PRIMARY KEY REFERENCES videos(video_id) ON DELETE CASCADE,
    full_text           TEXT,
    hook_text           TEXT,
    body_text           TEXT,
    outro_text          TEXT,
    word_count          INTEGER,
    source              VARCHAR(16),
    language            VARCHAR(8)
);

-- Top-N user comments per video, ordered by relevance at ingestion time
CREATE TABLE IF NOT EXISTS video_comments (
    comment_id          VARCHAR(128) PRIMARY KEY,
    video_id            VARCHAR(64) REFERENCES videos(video_id) ON DELETE CASCADE,
    author              TEXT,
    text                TEXT NOT NULL,
    like_count          INTEGER DEFAULT 0,
    published_at        TIMESTAMPTZ,
    ingested_at         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_video_comments_video_id ON video_comments (video_id);

CREATE TABLE IF NOT EXISTS agent_outputs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    video_id            VARCHAR(64) REFERENCES videos(video_id) ON DELETE CASCADE,
    agent_id            VARCHAR(32),
    output_data         JSONB NOT NULL,
    llm_model           VARCHAR(64),
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    latency_ms          INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS topic_salience_series (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID REFERENCES runs(run_id) ON DELETE CASCADE,
    channel_id          VARCHAR(64) REFERENCES channels(channel_id) ON DELETE CASCADE,
    topic               TEXT NOT NULL,
    salience            FLOAT,
    delta               FLOAT,
    velocity_slope      FLOAT,
    run_timestamp       TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topic_salience_series_channel_topic_time
    ON topic_salience_series (channel_id, topic, run_timestamp);

CREATE TABLE IF NOT EXISTS topic_embeddings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            VARCHAR(64) REFERENCES videos(video_id) ON DELETE CASCADE,
    chunk_index         INTEGER,
    chunk_text          TEXT,
    embedding           VECTOR(3072),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_topic_embeddings_embedding
    ON topic_embeddings USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_videos_channel_id ON videos (channel_id);
CREATE INDEX IF NOT EXISTS idx_agent_outputs_run_id ON agent_outputs (run_id);
CREATE INDEX IF NOT EXISTS idx_agent_outputs_video_id ON agent_outputs (video_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs (status);

CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    belief_statement    TEXT,
    run_id              UUID REFERENCES runs(run_id) ON DELETE CASCADE,
    predicted_at        TIMESTAMPTZ,
    outcome_observed_at TIMESTAMPTZ,
    outcome_type        VARCHAR(32),      -- 'confirmed' | 'refuted' | 'indeterminate'
    notes               TEXT
);
