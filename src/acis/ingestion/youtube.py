from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from acis.config import ChannelConfig
from acis.ingestion.service import IngestionClient
from acis.models import IngestionPayload, TranscriptSegment, VideoComment, VideoMetadata

# Max videos the YouTube search API returns per request
_YT_MAX_RESULTS = 50
# Top-N comments fetched per video, ordered by relevance
_TOP_COMMENTS_LIMIT = 20
# YouTube Data API v3 daily quota units
_QUOTA_DAILY_LIMIT = 10_000
_QUOTA_HALT_AT = int(_QUOTA_DAILY_LIMIT * 0.80)  # halt at 80 %
_QUOTA_COSTS = {
    "channels.list": 1,
    "search.list": 100,
    "videos.list": 1,
    "commentThreads.list": 1,
}


class QuotaExhaustedError(RuntimeError):
    """Raised when the estimated YouTube API quota reaches the 80 % safety threshold."""


def _parse_iso_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration (PT12M30S) to total seconds."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str or "")
    if not match:
        return 0
    return (
        int(match.group(1) or 0) * 3600
        + int(match.group(2) or 0) * 60
        + int(match.group(3) or 0)
    )


@dataclass(slots=True)
class YouTubeIngestionClient(IngestionClient):
    """Live YouTube ingestion using the Data API v3 and youtube-transcript-api.

    Requires: pip install 'acis[live]'
    """

    api_key: str
    ingested_video_ids: set[str] = field(default_factory=set)
    # Optional Whisper HTTP endpoint (e.g. "http://localhost:9000/asr") for transcript fallback
    whisper_endpoint: str = field(default="")
    # Optional directory to download thumbnail images into
    thumbnail_dir: Path | None = field(default=None)
    # Seconds to wait between transcript requests — keeps rate under YouTube's limit (~1 req/sec)
    transcript_delay: float = field(default=1.5)
    _youtube: object = field(default=None, init=False, repr=False)
    _channel_id_cache: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _skipped_count: int = field(default=0, init=False, repr=False)
    _quota_used: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            from googleapiclient.discovery import build  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "Live YouTube ingestion requires: pip install 'acis[live]'"
            ) from exc
        self._youtube = build("youtube", "v3", developerKey=self.api_key)

    @property
    def skipped_count(self) -> int:
        return self._skipped_count

    @property
    def quota_used(self) -> int:
        return self._quota_used

    def _consume_quota(self, operation: str) -> None:
        """Track API quota usage; raises QuotaExhaustedError at 80 % of the daily limit."""
        self._quota_used += _QUOTA_COSTS.get(operation, 1)
        if self._quota_used >= _QUOTA_HALT_AT:
            raise QuotaExhaustedError(
                f"YouTube API quota at {self._quota_used}/{_QUOTA_DAILY_LIMIT} units "
                f"(80 % threshold) — halting to protect daily allocation"
            )

    def _resolve_yt_channel_id(self, handle: str) -> str:
        clean = handle.lstrip("@")
        if clean in self._channel_id_cache:
            return self._channel_id_cache[clean]
        self._consume_quota("channels.list")
        result = (
            self._youtube.channels()
            .list(part="id", forHandle=clean)
            .execute()
        )
        items = result.get("items", [])
        if not items:
            raise ValueError(f"No YouTube channel found for handle @{clean}")
        yt_id = items[0]["id"]
        self._channel_id_cache[clean] = yt_id
        return yt_id

    def _search_video_ids(self, yt_channel_id: str, limit: int) -> list[str]:
        self._consume_quota("search.list")
        result = (
            self._youtube.search()
            .list(
                part="id",
                channelId=yt_channel_id,
                order="date",
                maxResults=min(limit, _YT_MAX_RESULTS),
                type="video",
            )
            .execute()
        )
        return [item["id"]["videoId"] for item in result.get("items", [])]

    def _fetch_video_details(self, video_ids: list[str]) -> list[dict]:
        self._consume_quota("videos.list")
        result = (
            self._youtube.videos()
            .list(
                part="snippet,statistics,contentDetails",
                id=",".join(video_ids),
            )
            .execute()
        )
        return result.get("items", [])

    def _fetch_top_comments(self, video_id: str) -> tuple[list[VideoComment], str]:
        """Fetch top-N comments; returns (comments, status) where status is 'ok', 'disabled', or 'error'."""
        self._consume_quota("commentThreads.list")
        try:
            result = (
                self._youtube.commentThreads()
                .list(
                    part="snippet",
                    videoId=video_id,
                    order="relevance",
                    maxResults=_TOP_COMMENTS_LIMIT,
                    textFormat="plainText",
                )
                .execute()
            )
            comments = []
            for thread in result.get("items", []):
                top = thread["snippet"]["topLevelComment"]["snippet"]
                comments.append(
                    VideoComment(
                        comment_id=thread["snippet"]["topLevelComment"]["id"],
                        author=top.get("authorDisplayName", ""),
                        text=top.get("textDisplay", "").strip(),
                        like_count=int(top.get("likeCount", 0)),
                        published_at=top.get("publishedAt", ""),
                    )
                )
            return comments, "ok"
        except Exception as exc:
            msg = str(exc).lower()
            if "commentsdisabled" in msg or "disabled comments" in msg or "403" in msg:
                return [], "disabled"
            print(f"  ⚠ {video_id}: comments fetch error — {exc}")
            return [], "error"

    def _fetch_transcript(self, video_id: str) -> tuple[list[TranscriptSegment], str]:
        try:
            from youtube_transcript_api import (  # noqa: PLC0415
                NoTranscriptFound,
                TranscriptsDisabled,
                YouTubeTranscriptApi,
            )
        except ImportError as exc:
            raise ImportError(
                "Transcript fetching requires: pip install 'acis[live]'"
            ) from exc

        # Pace requests to stay under YouTube's rate limit (~1 req/sec sustained)
        if self.transcript_delay > 0:
            time.sleep(self.transcript_delay)

        try:
            fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
            segments = [
                TranscriptSegment(
                    start=int(entry.start),
                    duration=int(entry.duration),
                    text=entry.text.strip(),
                )
                for entry in fetched
            ]
            return segments, "api"
        except (TranscriptsDisabled, NoTranscriptFound):
            pass  # expected: transcript not available for this video
        except Exception as exc:
            print(f"  ⚠ {video_id}: transcript fetch error — {exc}")

        # Whisper fallback when an endpoint is configured
        if self.whisper_endpoint:
            try:
                return self._fetch_transcript_whisper(video_id), "whisper"
            except Exception as exc:
                print(f"  ⚠ {video_id}: Whisper fallback failed — {exc}")

        return [], "unavailable"

    def _fetch_transcript_whisper(self, video_id: str) -> list[TranscriptSegment]:
        """Download audio via yt-dlp and POST to a Whisper HTTP endpoint for transcription."""
        import json as _json  # noqa: PLC0415
        import subprocess  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        import requests  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = f"{tmpdir}/{video_id}.mp3"
            subprocess.run(
                ["yt-dlp", "-x", "--audio-format", "mp3", "-o", audio_path,
                 f"https://www.youtube.com/watch?v={video_id}"],
                check=True,
                capture_output=True,
            )
            with open(audio_path, "rb") as audio_file:
                resp = requests.post(
                    self.whisper_endpoint,
                    files={"audio_file": audio_file},
                    data={"task": "transcribe", "language": "en"},
                    timeout=300,
                )
            resp.raise_for_status()
            data = resp.json()

        raw_segments = data.get("segments", [])
        return [
            TranscriptSegment(
                start=int(seg.get("start", 0)),
                duration=max(int(seg.get("end", 0)) - int(seg.get("start", 0)), 0),
                text=seg.get("text", "").strip(),
            )
            for seg in raw_segments
        ]

    def _download_thumbnail(self, video_id: str, fallback_url: str) -> str:
        """Download thumbnail to thumbnail_dir; returns local path or fallback_url on failure."""
        if not self.thumbnail_dir:
            return fallback_url
        try:
            import requests  # noqa: PLC0415
            self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
            local_path = self.thumbnail_dir / f"{video_id}.jpg"
            if local_path.exists():
                return str(local_path)
            for quality in ("maxresdefault", "hqdefault", "default"):
                url = f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    local_path.write_bytes(resp.content)
                    return str(local_path)
        except Exception as exc:
            print(f"  ⚠ {video_id}: thumbnail download failed — {exc}")
        return fallback_url

    def fetch_latest_videos(self, channel: ChannelConfig, limit: int) -> list[IngestionPayload]:
        print(f"  → {channel.display_name} ({channel.handle}): resolving channel ID…")
        yt_channel_id = self._resolve_yt_channel_id(channel.handle)

        print(f"  → {channel.display_name}: fetching latest {limit} video IDs…")
        video_ids = self._search_video_ids(yt_channel_id, limit)

        new_ids = [vid for vid in video_ids if vid not in self.ingested_video_ids]
        skipped = len(video_ids) - len(new_ids)
        self._skipped_count += skipped
        if skipped:
            print(f"  → {channel.display_name}: skipped {skipped} already-ingested videos")

        if not new_ids:
            print(f"  → {channel.display_name}: no new videos")
            print(f"  → quota used so far: {self._quota_used}/{_QUOTA_DAILY_LIMIT} units")
            return []

        print(f"  → {channel.display_name}: fetching details for {len(new_ids)} videos…")
        details = self._fetch_video_details(new_ids)

        payloads: list[IngestionPayload] = []
        for item in details:
            vid_id = item["id"]
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})

            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = (
                thumbnails.get("maxres", thumbnails.get("high", thumbnails.get("default", {})))
                .get("url", "")
            )

            segments, source = self._fetch_transcript(vid_id)
            comments, comment_status = self._fetch_top_comments(vid_id)
            thumbnail_url = self._download_thumbnail(vid_id, thumbnail_url)
            print(
                f"    ✓ {vid_id}: transcript={source}, segments={len(segments)}, "
                f"comments={len(comments)} ({comment_status})"
            )

            raw_comment_count = stats.get("commentCount")
            metadata = VideoMetadata(
                video_id=vid_id,
                channel_id=channel.channel_id,
                channel_handle=channel.handle,
                channel_display_name=channel.display_name,
                title=snippet.get("title", ""),
                description=snippet.get("description", ""),
                upload_date=date.fromisoformat(snippet["publishedAt"][:10]),
                duration_seconds=_parse_iso_duration(content.get("duration", "")),
                view_count=int(stats.get("viewCount", 0)),
                like_count=int(stats.get("likeCount", 0)),
                comment_count=int(raw_comment_count) if raw_comment_count is not None else None,
                thumbnail_url=thumbnail_url,
                transcript_source=source,
            )
            payloads.append(
                IngestionPayload(metadata=metadata, transcript_segments=segments, comments=comments)
            )

        print(f"  → {channel.display_name}: quota used so far: {self._quota_used}/{_QUOTA_DAILY_LIMIT} units")
        return payloads
