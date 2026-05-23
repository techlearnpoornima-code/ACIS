from __future__ import annotations

from dataclasses import dataclass

from acis.models import ChannelResearchNode, IngestionPayload
from acis.tools import (
    detect_language,
    normalise_metadata,
    segment_transcript,
    validate_transcript_completeness,
    word_count,
    words_per_minute,
)


@dataclass(slots=True)
class ChannelResearchAgent:
    """Agent 1: normalises metadata and segments the transcript into hook / body / outro windows."""

    agent_id: str = "agent_1_channel_researcher"

    def run(self, payload: IngestionPayload) -> ChannelResearchNode:
        metadata = normalise_metadata(payload)
        segments = segment_transcript(payload.transcript_segments, payload.metadata.duration_seconds)
        full_text = payload.full_text
        words = word_count(full_text)
        completeness = validate_transcript_completeness(
            payload.transcript_segments, payload.metadata.duration_seconds
        )
        if completeness < 0.6:
            print(
                f"  ⚠ {payload.metadata.video_id}: low transcript coverage "
                f"({completeness:.0%}) — topic extraction may be incomplete"
            )
        return ChannelResearchNode(
            video_id=payload.metadata.video_id,
            channel_id=payload.metadata.channel_id,
            title=payload.metadata.title,
            transcript_completeness=completeness,
            transcript_source=payload.metadata.transcript_source,
            language=detect_language(full_text),
            word_count=words,
            words_per_minute=words_per_minute(words, payload.metadata.duration_seconds),
            segments=segments,
            metadata=metadata,
        )
