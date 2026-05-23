from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from acis.models import IngestionPayload, TranscriptSegment, VideoMetadata


def load_sample_payloads(path: Path) -> dict[str, list[IngestionPayload]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    payloads: dict[str, list[IngestionPayload]] = {}
    for channel in raw["channels"]:
        channel_payloads: list[IngestionPayload] = []
        for video in channel["videos"]:
            metadata = VideoMetadata(
                video_id=video["video_id"],
                channel_id=channel["channel_id"],
                channel_handle=channel["handle"],
                channel_display_name=channel["display_name"],
                title=video["title"],
                description=video["description"],
                upload_date=date.fromisoformat(video["upload_date"]),
                duration_seconds=video["duration_seconds"],
                view_count=video["view_count"],
                like_count=video["like_count"],
                comment_count=video["comment_count"],
                thumbnail_url=video["thumbnail_url"],
                transcript_source=video["transcript_source"],
            )
            segments = [
                TranscriptSegment(
                    start=segment["start"],
                    duration=segment["duration"],
                    text=segment["text"],
                )
                for segment in video["transcript_segments"]
            ]
            channel_payloads.append(IngestionPayload(metadata=metadata, transcript_segments=segments))
        payloads[channel["channel_id"]] = channel_payloads
    return payloads
