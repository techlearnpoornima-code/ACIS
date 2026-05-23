from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(slots=True)
class TranscriptSegment:
    """A single caption segment with start offset (seconds), duration, and text."""

    start: int
    duration: int
    text: str


@dataclass(slots=True)
class VideoMetadata:
    """Raw metadata fetched from the YouTube API for a single video."""

    video_id: str
    channel_id: str
    channel_handle: str
    channel_display_name: str
    title: str
    description: str
    upload_date: date
    duration_seconds: int
    view_count: int
    like_count: int
    comment_count: int | None  # None when comments are disabled on the video
    thumbnail_url: str
    transcript_source: str  # 'api' | 'whisper' | 'unavailable'


@dataclass(slots=True)
class VideoComment:
    """A single top-level YouTube comment; used to gauge audience engagement and recurring questions."""

    comment_id: str
    author: str
    text: str
    like_count: int
    published_at: str  # ISO 8601 datetime string from YouTube API


@dataclass(slots=True)
class IngestionPayload:
    """Raw ingestion bundle for one video: metadata, transcript segments, and top comments."""

    metadata: VideoMetadata
    transcript_segments: list[TranscriptSegment]
    comments: list[VideoComment] = field(default_factory=list)  # top-N comments by relevance

    @property
    def full_text(self) -> str:
        return " ".join(segment.text for segment in self.transcript_segments).strip()


@dataclass(slots=True)
class TextWindow:
    """A contiguous slice of transcript text with its total duration."""

    text: str
    duration_seconds: int


@dataclass(slots=True)
class ChannelResearchNode:
    """Normalised output of Agent 1: segmented transcript + quality metrics for one video."""

    video_id: str
    channel_id: str
    title: str
    transcript_completeness: float  # 0–1; fraction of video duration covered by transcript
    transcript_source: str
    language: str
    word_count: int
    words_per_minute: int
    segments: dict[str, TextWindow]  # keys: 'hook', 'body', 'outro'
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["segments"] = {key: asdict(value) for key, value in self.segments.items()}
        return data


@dataclass(slots=True)
class SemanticGraphUpdate:
    """Output of Agent 2: extracted topics, salience scores, and monetisation signals for one video."""

    video_id: str
    technical_tools: list[str] = field(default_factory=list)
    architectures: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    business_models: list[str] = field(default_factory=list)
    monetisation_refs: list[dict[str, Any]] = field(default_factory=list)
    salience_scores: dict[str, float] = field(default_factory=dict)
    # Raw per-video TF per known topic; stored in topic_tf for cross-corpus IDF computation
    tf_scores: dict[str, float] = field(default_factory=dict)
    topic_pairs: list[tuple[str, str]] = field(default_factory=list)
    emergent_topics: list[str] = field(default_factory=list)  # auto-detected tool-like terms not in taxonomy

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Phase 2 models — Agent 3 (Hook Analyzer) and Agent 4 (Performance Correlator)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class IncomeClaim:
    """A single income or revenue claim detected in a video hook."""

    exact_quote: str
    figure: float | None  # None when the claim is vague (no specific number)
    claim_type: str       # 'self_verified' | 'client_attributed' | 'hypothetical' | 'vague'
    context: str


@dataclass(slots=True)
class HookProfile:
    """Output of Agent 3: hook taxonomy classification and persuasion metrics for one video."""

    video_id: str
    primary_taxonomy: str   # MONEY | STATUS | ANTI_CORPORATE | CURIOSITY_GAP |
                            # TRANSFORMATION | TECHNICAL_AUTHORITY | URGENCY
    secondary_taxonomy: str | None
    emotional_intensity: int   # 1–10 composite score
    certainty_ratio: float     # 0–1; certainty markers / (certainty + hedges)
    income_claims: list[IncomeClaim]
    hype_score: float          # 0–1 composite per FR-5.1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CorrelationResult:
    """One correlation row in Agent 4's matrix: attribute vs mean velocity multiplier."""

    attribute: str
    mean_multiplier: float
    p_value: float
    significant: bool  # p < 0.05


@dataclass(slots=True)
class PerformanceScoringMatrix:
    """Output of Agent 4: channel-level velocity and hook-performance correlations."""

    channel_id: str
    channel_median_velocity: float  # views/day baseline for the channel in this run window
    velocity_multipliers: dict[str, float]    # video_id → multiplier vs channel median
    correlations: list[CorrelationResult]
    breakout_videos: list[str]            # video_ids with velocity > channel_mean + 2σ
    top_performing_attributes: list[str]  # ordered by mean_multiplier descending

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Phase 3 models — Agent 5 (Gap Detector) and Agent 6 (Synthesizer)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class OpportunityItem:
    """A single white-space content opportunity identified by Agent 5."""

    topic: str
    saturation_score: float    # 0–1; fraction of channels covering this topic
    confidence: float           # 0–1; model confidence in the opportunity signal
    evidence: list[str]
    adjacent_rising_topics: list[str]


@dataclass(slots=True)
class OpportunityVector:
    """Output of Agent 5: ranked cross-channel white-space opportunity list."""

    opportunities: list[OpportunityItem]
    channels_analyzed: int
    videos_analyzed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StrategicBrief:
    """Output of Agent 6: McKinsey-structured competitive brief with belief graph deltas."""

    run_date: str
    situation: str
    complication: str
    resolution: str
    recommendations: str
    evidence: str
    risks_and_falsification: str
    belief_graph_deltas: str

    def to_markdown(self) -> str:
        return (
            f"# ACIS Strategic Brief — {self.run_date}\n\n"
            f"## Situation\n{self.situation}\n\n"
            f"## Complication\n{self.complication}\n\n"
            f"## Resolution\n{self.resolution}\n\n"
            f"## Recommendations\n{self.recommendations}\n\n"
            f"## Evidence\n{self.evidence}\n\n"
            f"## Risks & Falsification\n{self.risks_and_falsification}\n\n"
            f"## Belief Graph Deltas\n{self.belief_graph_deltas}\n"
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Pipeline result containers
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class VideoPipelineResult:
    """Paired Agent 1–3 outputs for a single video; passed downstream and persisted."""

    channel_research: ChannelResearchNode
    semantic_graph: SemanticGraphUpdate
    comments: list[VideoComment] = field(default_factory=list)
    hook_profile: HookProfile | None = field(default=None)  # None in Phase-1-only runs

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_research": self.channel_research.to_dict(),
            "semantic_graph": self.semantic_graph.to_dict(),
            "comments": [asdict(c) for c in self.comments],
            "hook_profile": self.hook_profile.to_dict() if self.hook_profile else None,
        }


@dataclass(slots=True)
class RunSummary:
    """Top-level run record: stats + per-video results + optional cross-channel analysis."""

    run_id: str
    started_at: datetime
    completed_at: datetime
    channels_processed: int
    videos_processed: int
    videos_skipped: int  # deduplicated videos already present in DB
    results: list[VideoPipelineResult]
    # Agent 4 output keyed by channel_id; empty dict in Phase-1-only runs
    performance_matrices: dict[str, PerformanceScoringMatrix] = field(default_factory=dict)
    # Agent 5 output; None in Phase-1-only runs
    opportunity_vector: OpportunityVector | None = field(default=None)
    # Agent 6 output; None in Phase-1-only runs
    strategic_brief: StrategicBrief | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "channels_processed": self.channels_processed,
            "videos_processed": self.videos_processed,
            "videos_skipped": self.videos_skipped,
            "results": [result.to_dict() for result in self.results],
            "performance_matrices": {
                ch_id: matrix.to_dict() for ch_id, matrix in self.performance_matrices.items()
            },
            "opportunity_vector": (
                self.opportunity_vector.to_dict() if self.opportunity_vector else None
            ),
            "strategic_brief": (
                self.strategic_brief.to_dict() if self.strategic_brief else None
            ),
        }
