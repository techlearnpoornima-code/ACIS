-- Per-video term frequency for each TOPIC_PATTERNS term.
-- IDF is derived on demand: log(COUNT(*) FROM videos / COUNT(DISTINCT video_id) per topic).
-- Only known vocabulary terms are stored — not every token in the transcript.
CREATE TABLE IF NOT EXISTS topic_tf (
    video_id    VARCHAR(64) NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    topic       TEXT NOT NULL,
    tf          FLOAT NOT NULL,
    PRIMARY KEY (video_id, topic)
);

CREATE INDEX IF NOT EXISTS idx_topic_tf_topic ON topic_tf (topic);

-- Convenience view: TF-IDF score for every (video, topic) pair currently in the table.
CREATE OR REPLACE VIEW topic_tfidf AS
SELECT
    t.video_id,
    t.topic,
    t.tf,
    df.df,
    total.n,
    t.tf * ln(total.n::float / NULLIF(df.df, 0)) AS tfidf
FROM topic_tf t
JOIN (
    SELECT topic, COUNT(DISTINCT video_id) AS df
    FROM topic_tf
    GROUP BY topic
) df USING (topic)
CROSS JOIN (SELECT COUNT(*) AS n FROM videos) total;
