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
