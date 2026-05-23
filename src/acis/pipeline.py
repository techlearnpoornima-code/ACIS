from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from acis.models import (
    ChannelResearchNode,
    HookProfile,
    IngestionPayload,
    OpportunityVector,
    PerformanceScoringMatrix,
    SemanticGraphUpdate,
    StrategicBrief,
    VideoPipelineResult,
)


# ---------------------------------------------------------------------------
# Protocol types — structural typing for all 6 agents
# ---------------------------------------------------------------------------

class ChannelResearcherProtocol(Protocol):
    """Any agent that accepts an IngestionPayload and produces a ChannelResearchNode."""

    def run(self, payload: IngestionPayload) -> ChannelResearchNode: ...


class TopicExtractorProtocol(Protocol):
    """Any agent that accepts a ChannelResearchNode and produces a SemanticGraphUpdate."""

    def run(self, node: ChannelResearchNode) -> SemanticGraphUpdate: ...


class HookAnalyzerProtocol(Protocol):
    """Any agent that accepts a research node + semantic graph and produces a HookProfile."""

    def run(self, node: ChannelResearchNode, graph: SemanticGraphUpdate) -> HookProfile: ...


class PerformanceCorrelatorProtocol(Protocol):
    """Any agent that runs channel-level velocity and correlation for a video set."""

    def run(
        self,
        channel_id: str,
        payloads: list[IngestionPayload],
        results: list[VideoPipelineResult],
    ) -> PerformanceScoringMatrix: ...


class GapDetectorProtocol(Protocol):
    """Any agent that detects white-space opportunities from all-channel results."""

    def run(self, results: list[VideoPipelineResult]) -> OpportunityVector: ...


class SynthesizerProtocol(Protocol):
    """Any agent that synthesises a McKinsey-structured strategic brief."""

    def run(
        self,
        results: list[VideoPipelineResult],
        perf_matrices: dict[str, PerformanceScoringMatrix],
        opportunity_vector: OpportunityVector,
        memory_store: object | None,
    ) -> StrategicBrief: ...


# ---------------------------------------------------------------------------
# Full 6-agent pipeline
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FullPipeline:
    """Full 6-agent pipeline: A1→A2→A3 per video, A4 per channel, A5→A6 cross-channel."""

    channel_researcher: ChannelResearcherProtocol
    topic_extractor: TopicExtractorProtocol
    hook_analyzer: HookAnalyzerProtocol
    performance_correlator: PerformanceCorrelatorProtocol
    gap_detector: GapDetectorProtocol
    synthesizer: SynthesizerProtocol
    memory_store: object | None = field(default=None)

    def run(self, payload: IngestionPayload) -> VideoPipelineResult:
        """Run A1→A2→A3 for a single video. A4-A6 need all-channel context."""
        research = self.channel_researcher.run(payload)
        semantic_graph = self.topic_extractor.run(research)
        hook_profile = self.hook_analyzer.run(research, semantic_graph)
        return VideoPipelineResult(
            channel_research=research,
            semantic_graph=semantic_graph,
            comments=payload.comments,
            hook_profile=hook_profile,
        )

    def run_cross_channel(
        self,
        payloads: list[IngestionPayload],
        results: list[VideoPipelineResult],
    ) -> tuple[dict[str, PerformanceScoringMatrix], OpportunityVector, StrategicBrief]:
        """Run A4 per channel, then A5→A6 across all channels.

        A4 is architecturally concurrent with A3 but is computed here after per-video
        results are available, since it requires channel-corpus median velocity.
        """
        channel_groups: dict[str, list[tuple[IngestionPayload, VideoPipelineResult]]] = {}
        for payload, result in zip(payloads, results):
            ch = payload.metadata.channel_id
            channel_groups.setdefault(ch, []).append((payload, result))

        perf_matrices: dict[str, PerformanceScoringMatrix] = {}
        for ch_id, pairs in channel_groups.items():
            perf_matrices[ch_id] = self.performance_correlator.run(
                ch_id,
                [p for p, _ in pairs],
                [r for _, r in pairs],
            )

        opportunity_vector = self.gap_detector.run(results)
        strategic_brief = self.synthesizer.run(
            results, perf_matrices, opportunity_vector, self.memory_store
        )
        return perf_matrices, opportunity_vector, strategic_brief
