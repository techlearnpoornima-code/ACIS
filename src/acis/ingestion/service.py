from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from acis.config import AppConfig, ChannelConfig
from acis.models import IngestionPayload
from acis.sample_data import load_sample_payloads


class IngestionClient(ABC):
    """Abstract base for video ingestion; swap implementations without changing the pipeline."""

    @abstractmethod
    def fetch_latest_videos(self, channel: ChannelConfig, limit: int) -> list[IngestionPayload]: ...


@dataclass(slots=True)
class SampleIngestionClient(IngestionClient):
    """Loads pre-recorded payloads from a local JSON file; used for development and tests."""

    sample_path: Path

    def fetch_latest_videos(self, channel: ChannelConfig, limit: int) -> list[IngestionPayload]:
        payloads = load_sample_payloads(self.sample_path)
        return payloads.get(channel.channel_id, [])[:limit]


@dataclass(slots=True)
class IngestionService:
    """Iterates configured channels and collects payloads via the injected client."""

    config: AppConfig
    client: IngestionClient

    def collect(self, limit_override: int | None = None) -> list[IngestionPayload]:
        limit = limit_override if limit_override is not None else self.config.default_video_limit
        payloads: list[IngestionPayload] = []
        for channel in self.config.channels:
            payloads.extend(self.client.fetch_latest_videos(channel, limit))
        return payloads
