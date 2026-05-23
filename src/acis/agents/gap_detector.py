from __future__ import annotations

import statistics
from dataclasses import dataclass

from acis.hermes_bridge import search_hermes_sessions
from acis.models import OpportunityItem, OpportunityVector, VideoPipelineResult
from acis.tools import TOPIC_PATTERNS

# White-space saturation threshold from FR-2.6
_SATURATION_THRESHOLD = 0.25
# Minimum salience to consider a topic adjacent-rising
_ADJACENT_SALIENCE_MIN = 0.15
# Minimum confidence to include an opportunity in the output
_MIN_CONFIDENCE = 0.35


def _all_topics_per_channel(
    results: list[VideoPipelineResult],
) -> dict[str, dict[str, list[float]]]:
    """Return {channel_id: {topic: [salience_scores]}} from all video results."""
    channel_topics: dict[str, dict[str, list[float]]] = {}
    for result in results:
        ch = result.channel_research.channel_id
        if ch not in channel_topics:
            channel_topics[ch] = {}
        graph = result.semantic_graph
        all_topics = (
            graph.technical_tools
            + graph.architectures
            + graph.use_cases
            + graph.business_models
            + graph.emergent_topics
        )
        for topic in all_topics:
            salience = graph.salience_scores.get(topic, 0.0)
            channel_topics[ch].setdefault(topic, []).append(salience)
    return channel_topics


def _compute_saturation(
    topic: str, channel_topics: dict[str, dict[str, list[float]]]
) -> float:
    """Fraction of channels that covered this topic at least once."""
    covering = sum(1 for topics in channel_topics.values() if topic in topics)
    return covering / max(len(channel_topics), 1)


def _mean_salience_across_channels(
    topic: str, channel_topics: dict[str, dict[str, list[float]]]
) -> float:
    """Average of per-channel maximum salience scores for this topic."""
    channel_maxes: list[float] = []
    for ch_topics in channel_topics.values():
        if topic in ch_topics:
            channel_maxes.append(max(ch_topics[topic]))
    return statistics.mean(channel_maxes) if channel_maxes else 0.0


def _find_adjacent_rising(
    topic: str,
    channel_topics: dict[str, dict[str, list[float]]],
    peers: list[str],
) -> list[str]:
    """Peer topics in the same category with above-threshold mean salience."""
    adjacent: list[str] = []
    for other in peers:
        if other == topic:
            continue
        if _mean_salience_across_channels(other, channel_topics) >= _ADJACENT_SALIENCE_MIN:
            adjacent.append(other)
    return adjacent[:5]


def _compute_confidence(
    saturation: float,
    adjacent_count: int,
    salience_mean: float,
    channel_count: int,
    video_count: int,
) -> float:
    """Heuristic confidence for an opportunity: lower saturation + more adjacency = higher confidence."""
    corpus_factor = min(video_count / 20.0, 1.0)
    adjacency_factor = min(adjacent_count / 3.0, 1.0)
    salience_factor = min(salience_mean * 10, 1.0)
    gap_factor = 1.0 - saturation
    confidence = (
        0.35 * gap_factor
        + 0.25 * adjacency_factor
        + 0.25 * corpus_factor
        + 0.15 * salience_factor
    )
    return round(min(confidence, 1.0), 4)


def _build_evidence_chain(
    topic: str,
    saturation: float,
    covering_channels: list[str],
    total_channels: int,
    adjacent: list[str],
    channel_topics: dict[str, dict[str, list[float]]],
    hermes_hits: list[dict] | None = None,
) -> list[str]:
    """Produce a 2–4-item evidence list for an opportunity."""
    evidence: list[str] = []
    n_covering = len(covering_channels)
    if n_covering == 0:
        evidence.append(f"No channel covered '{topic}' in this run window")
    else:
        evidence.append(
            f"Only {n_covering} of {total_channels} channels covered '{topic}' "
            f"(saturation {saturation:.2f})"
        )
    if adjacent:
        evidence.append(f"Adjacent topics with rising salience: {', '.join(adjacent[:3])}")
    mean_sal = _mean_salience_across_channels(topic, channel_topics)
    if mean_sal > 0:
        evidence.append(f"Mean salience across covering channels: {mean_sal:.4f}")
    if hermes_hits:
        evidence.append(
            f"Recurring gap: confirmed in {len(hermes_hits)} prior ACIS run(s) via Hermes FTS5"
        )
    else:
        evidence.append("First-time detection — no prior ACIS session confirms this gap")
    return evidence


# ---------------------------------------------------------------------------
# Agent 5 public class
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class GapDetectorAgent:
    """Agent 5: cross-channel saturation scorer and white-space opportunity detector."""

    agent_id: str = "agent_5_gap_detector"
    saturation_threshold: float = _SATURATION_THRESHOLD
    max_opportunities: int = 5

    def run(self, results: list[VideoPipelineResult]) -> OpportunityVector:
        if not results:
            return OpportunityVector(opportunities=[], channels_analyzed=0, videos_analyzed=0)

        channel_topics = _all_topics_per_channel(results)
        total_channels = len(channel_topics)
        total_videos = len(results)

        # Candidate topics = full known taxonomy (not just topics detected this run).
        # Topics never covered by any channel have saturation 0.0 — the true white space.
        category_map: dict[str, str] = {
            topic: category
            for category, topics in TOPIC_PATTERNS.items()
            for topic in topics
        }
        # Also include any topics detected this run that aren't in the static taxonomy
        for result in results:
            g = result.semantic_graph
            for t in g.technical_tools:
                category_map.setdefault(t, "technical_tools")
            for t in g.architectures:
                category_map.setdefault(t, "architectures")
            for t in g.use_cases:
                category_map.setdefault(t, "use_cases")
            for t in g.business_models:
                category_map.setdefault(t, "business_models")
            for t in g.emergent_topics:
                category_map.setdefault(t, "emerging")

        category_members: dict[str, list[str]] = {}
        for topic, cat in category_map.items():
            category_members.setdefault(cat, []).append(topic)

        candidates: list[OpportunityItem] = []

        for topic, category in category_map.items():
            saturation = _compute_saturation(topic, channel_topics)
            if saturation >= self.saturation_threshold:
                continue

            covering_channels = [
                ch for ch, topics in channel_topics.items() if topic in topics
            ]
            adjacent = _find_adjacent_rising(
                topic, channel_topics, category_members.get(category, [])
            )
            mean_sal = _mean_salience_across_channels(topic, channel_topics)
            confidence = _compute_confidence(
                saturation, len(adjacent), mean_sal, total_channels, total_videos
            )
            if confidence < _MIN_CONFIDENCE:
                continue

            hermes_hits = search_hermes_sessions(f"gap opportunity {topic}")
            evidence = _build_evidence_chain(
                topic, saturation, covering_channels,
                total_channels, adjacent, channel_topics,
                hermes_hits=hermes_hits,
            )
            candidates.append(OpportunityItem(
                topic=topic,
                saturation_score=round(saturation, 4),
                confidence=confidence,
                evidence=evidence,
                adjacent_rising_topics=adjacent,
            ))

        # Rank by confidence descending; use saturation as ascending tiebreak
        candidates.sort(key=lambda o: (-o.confidence, o.saturation_score))
        top = candidates[: self.max_opportunities]

        return OpportunityVector(
            opportunities=top,
            channels_analyzed=total_channels,
            videos_analyzed=total_videos,
        )
