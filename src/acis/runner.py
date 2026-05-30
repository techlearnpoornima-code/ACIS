from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from acis.agents import ChannelResearchAgent, TopicExtractorAgent
from acis.config import AppConfig, load_config
from acis.ingestion import IngestionService, SampleIngestionClient
from acis.models import RunSummary
from acis.pipeline import FullPipeline


@dataclass(slots=True)
class AcisApplication:
    """Top-level application object: wires ingestion → pipeline → optional DB persistence."""

    config: AppConfig
    ingestion_service: IngestionService
    pipeline: FullPipeline
    repository: object | None = field(default=None)  # DatabaseRepository when live

    def run(self, *, limit_override: int | None = None) -> RunSummary:
        started_at = datetime.now(UTC)
        run_id = str(uuid.uuid4())

        if self.repository is not None:
            self.repository.create_run(
                run_id, {"videos_per_channel": self.config.default_video_limit}
            )

        payloads = self.ingestion_service.collect(limit_override=limit_override)
        try:
            results = [self.pipeline.run(payload) for payload in payloads]
        except Exception:
            if self.repository is not None:
                self.repository.fail_run(run_id)
            raise

        completed_at = datetime.now(UTC)
        channel_ids = {payload.metadata.channel_id for payload in payloads}
        skipped = getattr(self.ingestion_service.client, "skipped_count", 0)

        perf_matrices: dict = {}
        opportunity_vector = None
        strategic_brief = None

        if payloads:
            try:
                perf_matrices, opportunity_vector, strategic_brief = (
                    self.pipeline.run_cross_channel(payloads, results)
                )
            except Exception as exc:
                print(f"  ⚠ Phase 2/3 cross-channel analysis failed: {exc}")

        summary = RunSummary(
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            channels_processed=len(channel_ids),
            videos_processed=len(results),
            videos_skipped=skipped,
            results=results,
            performance_matrices=perf_matrices,
            opportunity_vector=opportunity_vector,
            strategic_brief=strategic_brief,
        )

        if self.repository is not None:
            try:
                self.repository.complete_run(summary)
            except Exception:
                self.repository.fail_run(run_id)
                raise

        return summary


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _filter_channels(config: AppConfig, channel_filter: str | None) -> AppConfig:
    """Return a copy of config restricted to the requested channel handle, if specified."""
    if channel_filter is None:
        return config
    handle = channel_filter.lstrip("@").lower()
    matched = [c for c in config.channels if c.handle.lstrip("@").lower() == handle]
    if not matched:
        raise SystemExit(
            f"No channel with handle '{channel_filter}' found in config. "
            f"Available: {[c.handle for c in config.channels]}"
        )
    return AppConfig(default_video_limit=config.default_video_limit, channels=matched)


def build_live_app(
    project_root: Path,
    api_key: str,
    db_url: str | None = None,
    force_reprocess: bool = False,
    channel_filter: str | None = None,
    memory_path: Path | None = None,
    transcript_delay: float = 1.5,
) -> AcisApplication:
    try:
        from acis.ingestion.youtube import YouTubeIngestionClient  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit(
            "Live mode requires: pip install 'acis[live]'\n" + str(exc)
        ) from exc

    config = _filter_channels(
        load_config(project_root / "config" / "channels.yaml"), channel_filter
    )

    repo = None
    ingested_ids: set[str] = set()
    if db_url:
        try:
            from acis.db import DatabaseRepository  # noqa: PLC0415
        except ImportError as exc:
            raise SystemExit(
                "Database support requires: pip install 'acis[live]'\n" + str(exc)
            ) from exc
        repo = DatabaseRepository(db_url=db_url)
        if not force_reprocess:
            ingested_ids = repo.get_ingested_video_ids()
            print(f"Deduplication: {len(ingested_ids)} videos already in DB")
        else:
            print("Force-reprocess: deduplication disabled")

    from acis.agents.gap_detector import GapDetectorAgent  # noqa: PLC0415
    from acis.agents.hook_analyzer import HookAnalyzerAgent  # noqa: PLC0415
    from acis.agents.performance_correlator import PerformanceCorrelatorAgent  # noqa: PLC0415
    from acis.agents.synthesizer import SynthesizerAgent  # noqa: PLC0415

    ingestion_service = IngestionService(
        config=config,
        client=YouTubeIngestionClient(
            api_key=api_key,
            ingested_video_ids=ingested_ids,
            transcript_delay=transcript_delay,
            transcript_repo=repo,
        ),
    )

    memory_store = None
    if memory_path is not None:
        from acis.memory import MemoryStore  # noqa: PLC0415
        memory_store = MemoryStore(memory_path)
        if memory_path.exists():
            memory_store.load()

    pipeline = FullPipeline(
        channel_researcher=ChannelResearchAgent(),
        topic_extractor=TopicExtractorAgent(),
        hook_analyzer=HookAnalyzerAgent(),
        performance_correlator=PerformanceCorrelatorAgent(),
        gap_detector=GapDetectorAgent(),
        synthesizer=SynthesizerAgent(),
        memory_store=memory_store,
    )
    return AcisApplication(
        config=config,
        ingestion_service=ingestion_service,
        pipeline=pipeline,
        repository=repo,
    )


def build_agentscope_app(
    project_root: Path,
    model_name: str = "claude-sonnet-4-6",
    db_url: str | None = None,
    force_reprocess: bool = False,
    channel_filter: str | None = None,
    memory_path: Path | None = None,
    transcript_delay: float = 1.5,
) -> AcisApplication:
    """Build AcisApplication using AgentScope ReActAgents for Agent 1 and Agent 2.

    Requires: pip install 'acis[agents]' and ANTHROPIC_API_KEY env var.
    Falls back to deterministic agents per-video if the LLM loop fails.
    """
    try:
        from acis.agents.agentscope import (  # noqa: PLC0415
            SingleShotTopicExtractorAgent,
            init_agentscope,
        )
    except ImportError as exc:
        raise SystemExit(
            "AgentScope mode requires: pip install 'acis[agents]'\n" + str(exc)
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY environment variable is required for --agentscope mode."
        )

    model_config = init_agentscope(model_name=model_name, api_key=api_key)
    config = _filter_channels(
        load_config(project_root / "config" / "channels.yaml"), channel_filter
    )

    repo = None
    ingested_ids: set[str] = set()
    if db_url:
        try:
            from acis.db import DatabaseRepository  # noqa: PLC0415
        except ImportError as exc:
            raise SystemExit(
                "Database support requires: pip install 'acis[live]'\n" + str(exc)
            ) from exc
        repo = DatabaseRepository(db_url=db_url)
        if not force_reprocess:
            ingested_ids = repo.get_ingested_video_ids()
            print(f"Deduplication: {len(ingested_ids)} videos already in DB")
        else:
            print("Force-reprocess: deduplication disabled")

    yt_key = os.environ.get("YOUTUBE_API_KEY")
    try:
        from acis.ingestion.youtube import YouTubeIngestionClient  # noqa: PLC0415
        if yt_key:
            client = YouTubeIngestionClient(
                api_key=yt_key,
                ingested_video_ids=ingested_ids,
                transcript_delay=transcript_delay,
                transcript_repo=repo,
            )
        else:
            client = SampleIngestionClient(project_root / "data" / "sample_channels.json")
    except ImportError:
        client = SampleIngestionClient(project_root / "data" / "sample_channels.json")

    from acis.agents.gap_detector import GapDetectorAgent  # noqa: PLC0415
    from acis.agents.hook_analyzer import HookAnalyzerAgent  # noqa: PLC0415
    from acis.agents.performance_correlator import PerformanceCorrelatorAgent  # noqa: PLC0415
    from acis.agents.synthesizer import SynthesizerAgent  # noqa: PLC0415

    ingestion_service = IngestionService(config=config, client=client)

    memory_store = None
    if memory_path is not None:
        from acis.memory import MemoryStore  # noqa: PLC0415
        memory_store = MemoryStore(memory_path)
        if memory_path.exists():
            memory_store.load()

    pipeline = FullPipeline(
        channel_researcher=ChannelResearchAgent(),
        topic_extractor=SingleShotTopicExtractorAgent(**model_config),
        hook_analyzer=HookAnalyzerAgent(),
        performance_correlator=PerformanceCorrelatorAgent(),
        gap_detector=GapDetectorAgent(),
        synthesizer=SynthesizerAgent(),
        memory_store=memory_store,
    )
    return AcisApplication(
        config=config,
        ingestion_service=ingestion_service,
        pipeline=pipeline,
        repository=repo,
    )


# ---------------------------------------------------------------------------
# Sample-data builder — deterministic, zero external dependencies
# ---------------------------------------------------------------------------

def build_full_sample_app(
    project_root: Path,
    channel_filter: str | None = None,
    memory_path: Path | None = None,
) -> AcisApplication:
    """Build AcisApplication with all 6 deterministic agents (no LLM required).

    When memory_path is provided the MEMORY.md belief store is loaded on startup
    and updated at the end of each run by Agent 6.
    """
    from acis.agents.gap_detector import GapDetectorAgent  # noqa: PLC0415
    from acis.agents.hook_analyzer import HookAnalyzerAgent  # noqa: PLC0415
    from acis.agents.performance_correlator import PerformanceCorrelatorAgent  # noqa: PLC0415
    from acis.agents.synthesizer import SynthesizerAgent  # noqa: PLC0415

    config = _filter_channels(
        load_config(project_root / "config" / "channels.yaml"), channel_filter
    )
    ingestion_service = IngestionService(
        config=config,
        client=SampleIngestionClient(project_root / "data" / "sample_channels.json"),
    )

    memory_store = None
    if memory_path is not None:
        from acis.memory import MemoryStore  # noqa: PLC0415
        memory_store = MemoryStore(memory_path)
        if memory_path.exists():
            memory_store.load()

    pipeline = FullPipeline(
        channel_researcher=ChannelResearchAgent(),
        topic_extractor=TopicExtractorAgent(),
        hook_analyzer=HookAnalyzerAgent(),
        performance_correlator=PerformanceCorrelatorAgent(),
        gap_detector=GapDetectorAgent(),
        synthesizer=SynthesizerAgent(),
        memory_store=memory_store,
    )
    return AcisApplication(config=config, ingestion_service=ingestion_service, pipeline=pipeline)


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

def write_summary(summary: RunSummary, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
