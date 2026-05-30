from __future__ import annotations

import json
from dataclasses import dataclass, field

from acis.models import RunSummary, VideoComment, VideoPipelineResult


@dataclass(slots=True)
class DatabaseRepository:
    """Synchronous PostgreSQL repository for persisting ACIS run results.

    Requires: pip install 'acis[live]'
    """

    db_url: str
    _engine: object = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            from sqlalchemy import create_engine  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "Database support requires: pip install 'acis[live]'"
            ) from exc
        self._engine = create_engine(self.db_url)

    def get_cached_transcript(self, video_id: str) -> tuple[list, str] | None:
        """Return (segments, source) from transcript_cache or transcripts table, or None.

        Checks transcript_cache first (raw segments). Falls back to the transcripts table
        and reconstructs pseudo-segments from stored hook/body/outro text so videos
        processed before transcript_cache existed don't trigger a YouTube API call.
        """
        from sqlalchemy import text  # noqa: PLC0415
        from acis.models import TranscriptSegment  # noqa: PLC0415

        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT segments_json, source FROM transcript_cache WHERE video_id = :vid"),
                {"vid": video_id},
            ).fetchone()
            if row is not None:
                segments = [TranscriptSegment(**s) for s in row[0]]
                return segments, row[1]

            row2 = conn.execute(
                text(
                    "SELECT hook_text, body_text, outro_text, source "
                    "FROM transcripts WHERE video_id = :vid"
                ),
                {"vid": video_id},
            ).fetchone()

        if row2 is None or not any([row2[0], row2[1], row2[2]]):
            return None

        # Reconstruct three segments matching the hook/body/outro split
        segments = [
            TranscriptSegment(start=0,   duration=60,  text=row2[0] or ""),
            TranscriptSegment(start=60,  duration=300, text=row2[1] or ""),
            TranscriptSegment(start=360, duration=60,  text=row2[2] or ""),
        ]
        print(f"    ↩ {video_id}: transcript from transcripts table (legacy cache)")
        return segments, row2[3] or "api"

    def save_beliefs(self, beliefs: list) -> None:
        """Upsert all beliefs to the beliefs table — DB is the authoritative store."""
        from sqlalchemy import text  # noqa: PLC0415
        if not beliefs:
            return
        with self._engine.begin() as conn:
            for b in beliefs:
                conn.execute(
                    text(
                        "INSERT INTO beliefs "
                        "(belief_id, statement, confidence, evidence_count, "
                        " last_confirmed, half_life_days, tags, updated_at) "
                        "VALUES (:bid, :stmt, :conf, :ec, :lc, :hl, :tags, NOW()) "
                        "ON CONFLICT (belief_id) DO UPDATE SET "
                        "statement = EXCLUDED.statement, "
                        "confidence = EXCLUDED.confidence, "
                        "evidence_count = EXCLUDED.evidence_count, "
                        "last_confirmed = EXCLUDED.last_confirmed, "
                        "half_life_days = EXCLUDED.half_life_days, "
                        "tags = EXCLUDED.tags, "
                        "updated_at = NOW()"
                    ),
                    {
                        "bid": b.belief_id,
                        "stmt": b.statement,
                        "conf": b.confidence,
                        "ec": b.evidence_count,
                        "lc": b.last_confirmed,
                        "hl": b.half_life_days,
                        "tags": b.tags,
                    },
                )

    def load_beliefs(self) -> list:
        """Load all beliefs from the DB to seed a MemoryStore on startup."""
        from sqlalchemy import text  # noqa: PLC0415
        from acis.memory import Belief  # noqa: PLC0415
        from datetime import date  # noqa: PLC0415
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT belief_id, statement, confidence, evidence_count, "
                    "last_confirmed, half_life_days, tags FROM beliefs"
                )
            ).fetchall()
        return [
            Belief(
                belief_id=r[0],
                statement=r[1],
                confidence=r[2],
                evidence_count=r[3],
                last_confirmed=r[4] if isinstance(r[4], date) else date.fromisoformat(str(r[4])),
                half_life_days=r[5],
                tags=list(r[6]) if r[6] else [],
            )
            for r in rows
        ]

    def search_past_gaps(self, topic: str) -> list[dict]:
        """FTS search for previous runs where this topic was identified as a gap opportunity."""
        from sqlalchemy import text  # noqa: PLC0415
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT topic, saturation_score, confidence, detected_at "
                    "FROM gap_detections "
                    "WHERE to_tsvector('english', topic) @@ plainto_tsquery('english', :q) "
                    "   OR topic ILIKE :pat "
                    "ORDER BY detected_at DESC LIMIT 5"
                ),
                {"q": topic, "pat": f"%{topic}%"},
            ).fetchall()
        return [
            {"topic": r[0], "saturation_score": r[1], "confidence": r[2], "detected_at": str(r[3])}
            for r in rows
        ]

    def save_gap_detections(self, run_id: str, opportunity_vector: object) -> None:
        """Persist gap opportunity topics for future FTS lookup."""
        from sqlalchemy import text  # noqa: PLC0415
        opps = getattr(opportunity_vector, "opportunities", [])
        if not opps:
            return
        with self._engine.begin() as conn:
            for opp in opps:
                conn.execute(
                    text(
                        "INSERT INTO gap_detections (run_id, topic, saturation_score, confidence) "
                        "VALUES (:run_id, :topic, :sat, :conf)"
                    ),
                    {
                        "run_id": run_id,
                        "topic": opp.topic,
                        "sat": opp.saturation_score,
                        "conf": opp.confidence,
                    },
                )

    def save_transcript_cache(self, video_id: str, segments: list, source: str) -> None:
        """Persist raw transcript segments so future runs skip the YouTube API call."""
        from sqlalchemy import text  # noqa: PLC0415
        segs_json = json.dumps(
            [{"start": s.start, "duration": s.duration, "text": s.text} for s in segments]
        )
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO transcript_cache (video_id, segments_json, source) "
                    "VALUES (:vid, :segs::jsonb, :src) "
                    "ON CONFLICT (video_id) DO UPDATE SET "
                    "segments_json = EXCLUDED.segments_json, source = EXCLUDED.source, "
                    "fetched_at = NOW()"
                ),
                {"vid": video_id, "segs": segs_json, "src": source},
            )

    def get_ingested_video_ids(self) -> set[str]:
        from sqlalchemy import text  # noqa: PLC0415
        with self._engine.connect() as conn:
            rows = conn.execute(text("SELECT video_id FROM videos")).fetchall()
        return {row[0] for row in rows}

    def create_run(self, run_id: str, config_snapshot: dict) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO runs (run_id, started_at, status, config_snapshot) "
                    "VALUES (:run_id, NOW(), 'running', :config)"
                ),
                {"run_id": run_id, "config": json.dumps(config_snapshot)},
            )

    def fail_run(self, run_id: str) -> None:
        """Mark a run as failed — called when the pipeline raises an unhandled exception."""
        from sqlalchemy import text  # noqa: PLC0415
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE runs SET completed_at = NOW(), status = 'failed' "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )

    def complete_run(self, summary: RunSummary) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        with self._engine.begin() as conn:
            for result in summary.results:
                self._upsert_channel(conn, result)
                self._insert_video(conn, result)
                if result.channel_research.transcript_source != "unavailable":
                    self._insert_transcript(conn, result)
                if result.comments:
                    self._insert_comments(conn, result.channel_research.video_id, result.comments)
                if result.semantic_graph.tf_scores:
                    self._insert_topic_tf(conn, result.channel_research.video_id, result.semantic_graph.tf_scores)
                self._insert_agent_output(conn, summary.run_id, result)

            conn.execute(
                text(
                    "UPDATE runs SET completed_at = NOW(), status = 'completed', "
                    "channels_processed = :ch, videos_processed = :vp, videos_skipped = :vs "
                    "WHERE run_id = :run_id"
                ),
                {
                    "run_id": summary.run_id,
                    "ch": summary.channels_processed,
                    "vp": summary.videos_processed,
                    "vs": summary.videos_skipped,
                },
            )

        if summary.opportunity_vector is not None:
            self.save_gap_detections(summary.run_id, summary.opportunity_vector)

    def _upsert_channel(self, conn, result: VideoPipelineResult) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        r = result.channel_research
        conn.execute(
            text(
                "INSERT INTO channels (channel_id, handle, display_name, first_ingested_at, last_ingested_at) "
                "VALUES (:id, :handle, :name, NOW(), NOW()) "
                "ON CONFLICT (channel_id) DO UPDATE SET last_ingested_at = NOW(), "
                "handle = EXCLUDED.handle, display_name = EXCLUDED.display_name"
            ),
            {
                "id": r.channel_id,
                "handle": r.metadata.get("channel_handle", ""),
                "name": r.metadata.get("channel_display_name", ""),
            },
        )

    def _insert_video(self, conn, result: VideoPipelineResult) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        r = result.channel_research
        m = r.metadata
        conn.execute(
            text(
                "INSERT INTO videos "
                "(video_id, channel_id, title, description, upload_date, duration_seconds, "
                " view_count, like_count, comment_count, thumbnail_path, transcript_status, ingested_at) "
                "VALUES (:vid, :ch, :title, :desc, :udate, :dur, :views, :likes, :comments, :thumb, :tsrc, NOW()) "
                "ON CONFLICT (video_id) DO NOTHING"
            ),
            {
                "vid": r.video_id,
                "ch": r.channel_id,
                "title": r.title,
                "desc": m.get("description", ""),
                "udate": m.get("upload_date"),
                "dur": m.get("duration_seconds"),
                "views": m.get("view_count"),
                "likes": m.get("like_count"),
                "comments": m.get("comment_count"),
                "thumb": m.get("thumbnail_url"),
                "tsrc": r.transcript_source,
            },
        )

    def _insert_transcript(self, conn, result: VideoPipelineResult) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        r = result.channel_research
        segs = r.segments
        full = " ".join(
            [segs["hook"].text, segs["body"].text, segs["outro"].text]
        ).strip()
        conn.execute(
            text(
                "INSERT INTO transcripts "
                "(video_id, full_text, hook_text, body_text, outro_text, word_count, source, language) "
                "VALUES (:vid, :full, :hook, :body, :outro, :wc, :src, :lang) "
                "ON CONFLICT (video_id) DO NOTHING"
            ),
            {
                "vid": r.video_id,
                "full": full,
                "hook": segs["hook"].text,
                "body": segs["body"].text,
                "outro": segs["outro"].text,
                "wc": r.word_count,
                "src": r.transcript_source,
                "lang": r.language,
            },
        )

    def _insert_comments(self, conn, video_id: str, comments: list[VideoComment]) -> None:
        """Insert top-N user comments; skips duplicates via ON CONFLICT DO NOTHING."""
        from sqlalchemy import text  # noqa: PLC0415
        for c in comments:
            conn.execute(
                text(
                    "INSERT INTO video_comments "
                    "(comment_id, video_id, author, text, like_count, published_at) "
                    "VALUES (:cid, :vid, :author, :text, :likes, :pub_at) "
                    "ON CONFLICT (comment_id) DO NOTHING"
                ),
                {
                    "cid": c.comment_id,
                    "vid": video_id,
                    "author": c.author,
                    "text": c.text,
                    "likes": c.like_count,
                    "pub_at": c.published_at if c.published_at else None,
                },
            )

    def _insert_topic_tf(self, conn, video_id: str, tf_scores: dict[str, float]) -> None:
        """Upsert one row per detected topic; enables IDF via COUNT(DISTINCT video_id) per topic."""
        from sqlalchemy import text  # noqa: PLC0415
        sql = text(
            "INSERT INTO topic_tf (video_id, topic, tf) VALUES (:vid, :topic, :tf) "
            "ON CONFLICT (video_id, topic) DO UPDATE SET tf = EXCLUDED.tf"
        )
        for topic, tf in tf_scores.items():
            if tf > 0.0:
                conn.execute(sql, {"vid": video_id, "topic": topic, "tf": tf})

    def _insert_agent_output(self, conn, run_id: str, result: VideoPipelineResult) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        sql = text(
            "INSERT INTO agent_outputs (run_id, video_id, agent_id, output_data) "
            "VALUES (:run_id, :vid, :agent, :data)"
        )
        vid = result.channel_research.video_id
        conn.execute(sql, {
            "run_id": run_id,
            "vid": vid,
            "agent": "agent_1_channel_researcher",
            "data": json.dumps(result.channel_research.to_dict()),
        })
        conn.execute(sql, {
            "run_id": run_id,
            "vid": vid,
            "agent": "agent_2_topic_extractor",
            "data": json.dumps(result.semantic_graph.to_dict()),
        })
