-- Transcript cache: raw segments stored independently of the videos table so
-- they survive --force-reprocess runs without hitting the YouTube API again.
CREATE TABLE IF NOT EXISTS transcript_cache (
    video_id        VARCHAR(64) PRIMARY KEY,
    segments_json   JSONB        NOT NULL,   -- [{"start":0,"duration":18,"text":"..."},...]
    source          VARCHAR(16)  NOT NULL,   -- 'api' | 'whisper'
    fetched_at      TIMESTAMPTZ  DEFAULT NOW()
);
