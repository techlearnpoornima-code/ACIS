-- Gap detections: records every topic flagged as a white-space opportunity per run.
-- Replaces Hermes FTS5 session search with native PostgreSQL full-text search.
CREATE TABLE IF NOT EXISTS gap_detections (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID        REFERENCES runs(run_id) ON DELETE CASCADE,
    topic            TEXT        NOT NULL,
    saturation_score FLOAT,
    confidence       FLOAT,
    detected_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gap_detections_topic_fts
    ON gap_detections USING gin(to_tsvector('english', topic));
CREATE INDEX IF NOT EXISTS idx_gap_detections_run_id
    ON gap_detections (run_id);
