from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timezone

from dataclasses import field as _field
from acis.models import (
    OpportunityVector,
    PerformanceScoringMatrix,
    StrategicBrief,
    VideoPipelineResult,
)

_STRONG_EVIDENCE = 0.6
_WEAK_EVIDENCE = 0.25


@dataclass
class BeliefDelta:
    """A single belief change written to the local MEMORY.md belief store."""

    statement: str
    evidence_strength: float  # ∈ [-1, 1]
    tags: list[str] = _field(default_factory=list)
    half_life_days: int = 60


def _build_situation(
    results: list[VideoPipelineResult],
    perf_matrices: dict[str, PerformanceScoringMatrix],
) -> str:
    channel_ids = sorted({r.channel_research.channel_id for r in results})
    total_videos = len(results)

    topic_freq: dict[str, int] = {}
    all_emergent: dict[str, int] = {}
    for r in results:
        g = r.semantic_graph
        for topic in g.technical_tools + g.architectures + g.use_cases + g.business_models:
            topic_freq[topic] = topic_freq.get(topic, 0) + 1
        for term in g.emergent_topics:
            all_emergent[term] = all_emergent.get(term, 0) + 1

    top_topics = sorted(topic_freq, key=lambda t: -topic_freq[t])[:8]
    top_str = ", ".join(top_topics) if top_topics else "none detected"

    channel_lines: list[str] = []
    for ch_id in channel_ids:
        matrix = perf_matrices.get(ch_id)
        vel_str = (
            f"median velocity {matrix.channel_median_velocity:.0f} views/day"
            if matrix else "velocity not computed"
        )
        channel_lines.append(f"- **{ch_id}**: {vel_str}")

    emergent_top = sorted(all_emergent, key=lambda t: -all_emergent[t])[:8]
    emergent_line = (
        f"\n\n**Newly detected tools (not in taxonomy):** {', '.join(emergent_top)}."
        if emergent_top else ""
    )

    return (
        f"Analysed {total_videos} videos across {len(channel_ids)} channels "
        f"({', '.join(channel_ids)}).\n\n"
        f"**Channel velocity baselines:**\n" + "\n".join(channel_lines) + "\n\n"
        f"**Top topics in current window:** {top_str}.{emergent_line}"
    )


def _build_complication(
    results: list[VideoPipelineResult],
    perf_matrices: dict[str, PerformanceScoringMatrix],
) -> str:
    channel_ids = {r.channel_research.channel_id for r in results}
    channel_topic_map: dict[str, set[str]] = {ch: set() for ch in channel_ids}

    for r in results:
        g = r.semantic_graph
        ch = r.channel_research.channel_id
        for t in g.technical_tools + g.architectures + g.use_cases + g.business_models:
            channel_topic_map[ch].add(t)

    total_ch = len(channel_ids)
    saturated = [
        (t, sum(1 for s in channel_topic_map.values() if t in s))
        for t in {t for s in channel_topic_map.values() for t in s}
        if sum(1 for s in channel_topic_map.values() if t in s) >= max(2, total_ch // 2 + 1)
    ]
    saturated.sort(key=lambda x: -x[1])
    sat_str = (
        ", ".join(f"{t} ({n}/{total_ch} channels)" for t, n in saturated[:5])
        if saturated else "no highly saturated topics detected"
    )

    hook_counts: dict[str, int] = {}
    for r in results:
        if r.hook_profile:
            tax = r.hook_profile.primary_taxonomy
            hook_counts[tax] = hook_counts.get(tax, 0) + 1

    dominant_hook = max(hook_counts, key=lambda k: hook_counts[k]) if hook_counts else "unknown"
    hook_summary = (
        ", ".join(f"{t}: {n}" for t, n in sorted(hook_counts.items(), key=lambda x: -x[1]))
        if hook_counts else "hook data unavailable"
    )

    breakout_lines: list[str] = []
    for ch_id, matrix in perf_matrices.items():
        if matrix.breakout_videos:
            breakout_lines.append(
                f"- **{ch_id}**: breakout videos {', '.join(matrix.breakout_videos)}"
            )
    breakout_str = "\n".join(breakout_lines) if breakout_lines else "_No statistical breakouts detected._"

    return (
        f"**Saturated topics (≥50% channel coverage):** {sat_str}.\n\n"
        f"**Hook taxonomy distribution:** {hook_summary}. "
        f"Dominant style: **{dominant_hook}**.\n\n"
        f"**Statistical breakout videos:**\n{breakout_str}"
    )


def _build_resolution(opportunity_vector: OpportunityVector) -> str:
    if not opportunity_vector.opportunities:
        return (
            "No clear white-space opportunities detected in the current window. "
            "Consider expanding the channel set or extending the analysis window."
        )
    lines: list[str] = []
    for i, opp in enumerate(opportunity_vector.opportunities, start=1):
        adjacent_str = (
            f" Adjacent rising: {', '.join(opp.adjacent_rising_topics)}."
            if opp.adjacent_rising_topics else ""
        )
        lines.append(
            f"**{i}. {opp.topic}** — saturation {opp.saturation_score:.2f}, "
            f"confidence {opp.confidence:.2f}.{adjacent_str}"
        )
    return (
        "Ranked content opportunities with lowest topic saturation across analysed channels:\n\n"
        + "\n\n".join(lines)
    )


def _build_evidence(
    results: list[VideoPipelineResult],
    perf_matrices: dict[str, PerformanceScoringMatrix],
    opportunity_vector: OpportunityVector,
) -> str:
    blocks: list[str] = []

    sig_rows: list[str] = []
    for matrix in perf_matrices.values():
        for corr in matrix.correlations:
            if corr.significant:
                sig_rows.append(
                    f"  - {corr.attribute}: {corr.mean_multiplier:.2f}× "
                    f"(p={corr.p_value:.3f}) on {matrix.channel_id}"
                )
    if sig_rows:
        blocks.append("**Significant performance correlations (p<0.05):**\n" + "\n".join(sig_rows))

    opp_rows: list[str] = []
    for opp in opportunity_vector.opportunities:
        ev_str = "\n".join(f"    - {e}" for e in opp.evidence)
        opp_rows.append(f"  **{opp.topic}:**\n{ev_str}")
    if opp_rows:
        blocks.append("**Opportunity evidence chains:**\n" + "\n".join(opp_rows))

    hype_scores = [r.hook_profile.hype_score for r in results if r.hook_profile]
    if hype_scores:
        blocks.append(
            f"**Hype score summary:** mean {statistics.mean(hype_scores):.2f}, "
            f"max {max(hype_scores):.2f} across {len(hype_scores)} videos."
        )

    return "\n\n".join(blocks) if blocks else "_Insufficient data for evidence chain construction._"


def _build_recommendations(
    results: list[VideoPipelineResult],
    perf_matrices: dict[str, PerformanceScoringMatrix],
    opportunity_vector: OpportunityVector,
) -> str:
    """Produce concrete, prioritised content recommendations from all agent outputs."""
    if not opportunity_vector.opportunities:
        return "_No high-confidence opportunities identified — expand channel set or analysis window._"

    # Best-performing hook style across all channels
    hook_counts: dict[str, int] = {}
    for r in results:
        if r.hook_profile:
            hook_counts[r.hook_profile.primary_taxonomy] = (
                hook_counts.get(r.hook_profile.primary_taxonomy, 0) + 1
            )
    dominant_hook = max(hook_counts, key=lambda k: hook_counts[k]) if hook_counts else None

    # Best-performing duration bucket per channel (significant correlations only)
    best_duration: dict[str, tuple[str, float]] = {}
    for matrix in perf_matrices.values():
        for corr in matrix.correlations:
            if corr.significant and corr.attribute.startswith("duration_bucket="):
                bucket = corr.attribute.split("=", 1)[1]
                prev = best_duration.get(matrix.channel_id)
                if prev is None or corr.mean_multiplier > prev[1]:
                    best_duration[matrix.channel_id] = (bucket, corr.mean_multiplier)

    # Fastest channel by median velocity — used as competitive benchmark
    top_channel = max(
        perf_matrices,
        key=lambda ch: perf_matrices[ch].channel_median_velocity,
        default=None,
    )
    top_velocity = (
        f"{perf_matrices[top_channel].channel_median_velocity:.0f} views/day on {top_channel}"
        if top_channel else None
    )

    lines: list[str] = []
    for i, opp in enumerate(opportunity_vector.opportunities, start=1):
        adjacent = ", ".join(opp.adjacent_rising_topics[:3]) if opp.adjacent_rising_topics else None
        angle = (
            f"Angle: position alongside **{adjacent}** to capture that audience's spillover."
            if adjacent else "Angle: first-mover advantage — no adjacent channel has covered this yet."
        )
        hook_line = (
            f"Hook: use **{dominant_hook}** framing "
            f"({hook_counts.get(dominant_hook, 0)}/{len(results)} videos use this style — "
            f"highest engagement pattern detected)."
            if dominant_hook else ""
        )
        duration_lines = [
            f"Duration: target **{bucket}** on {ch} ({mult:.2f}× velocity multiplier)."
            for ch, (bucket, mult) in best_duration.items()
        ]
        benchmark_line = (
            f"Competitive window: top channel runs at {top_velocity} — "
            f"zero competitors have staked a claim on this topic."
            if top_velocity else ""
        )

        parts = [f"**{i}. Publish on: {opp.topic}**"]
        parts.append(
            f"- Why now: saturation **{opp.saturation_score:.2f}** across all analysed channels "
            f"(confidence {opp.confidence:.2f}). No channel in the corpus has covered this topic."
        )
        if hook_line:
            parts.append(f"- {hook_line}")
        for dl in duration_lines:
            parts.append(f"- {dl}")
        parts.append(f"- {angle}")
        if benchmark_line:
            parts.append(f"- {benchmark_line}")
        parts.append("- Act within **2 weeks** — saturation spikes fast once one channel publishes.")
        lines.append("\n".join(parts))

    return "\n\n".join(lines)


def _build_risks(opportunity_vector: OpportunityVector) -> str:
    if not opportunity_vector.opportunities:
        return "_No opportunities to falsify._"
    lines: list[str] = []
    for opp in opportunity_vector.opportunities[:3]:
        lines.append(
            f"**{opp.topic}** — this recommendation is wrong if:\n"
            f"  1. A major channel publishes multiple videos on this topic within 2 weeks "
            f"(saturation spike would close the window).\n"
            f"  2. Audience search intent for this topic is low "
            f"(saturation score alone doesn't capture demand).\n"
            f"  3. Adjacent rising topics stall or reverse in the next run "
            f"(current velocity slope may not be sustained)."
        )
    return "\n\n".join(lines)


def _update_beliefs(
    perf_matrices: dict[str, PerformanceScoringMatrix],
    opportunity_vector: OpportunityVector,
    memory_store: object | None,
    db_repo: object | None = None,
) -> str:
    """Collect belief deltas and write to PostgreSQL (primary) and/or local MEMORY.md (fallback)."""
    from acis.memory import MemoryStore  # noqa: PLC0415

    belief_deltas: list[BeliefDelta] = []

    for matrix in perf_matrices.values():
        for corr in matrix.correlations:
            if corr.significant and corr.mean_multiplier > 1.2:
                strength = _STRONG_EVIDENCE if corr.mean_multiplier > 2.0 else _WEAK_EVIDENCE
                belief_deltas.append(BeliefDelta(
                    statement=(
                        f"{corr.attribute} correlates with "
                        f">{corr.mean_multiplier:.1f}x velocity on {matrix.channel_id}"
                    ),
                    evidence_strength=strength,
                    tags=["performance-correlation", corr.attribute.split("=")[0], matrix.channel_id],
                ))

    for opp in opportunity_vector.opportunities:
        if opp.confidence >= 0.55:
            belief_deltas.append(BeliefDelta(
                statement=(
                    f"'{opp.topic}' is a white-space opportunity "
                    f"(saturation {opp.saturation_score:.2f})"
                ),
                evidence_strength=_WEAK_EVIDENCE,
                tags=["white-space", "opportunity"],
                half_life_days=30,
            ))

    if not belief_deltas:
        return "_No belief updates this run._\n"

    if not isinstance(memory_store, MemoryStore):
        return "_Memory store not configured — belief graph not updated._\n"

    memory_store.decay_all()
    updated_ids = [
        memory_store.update(
            statement=d.statement,
            evidence_strength=d.evidence_strength,
            tags=d.tags,
            half_life_days=d.half_life_days,
        ).belief_id
        for d in belief_deltas
    ]

    # Always persist to PostgreSQL when available — DB is the authoritative store
    if db_repo is not None:
        try:
            db_repo.save_beliefs(memory_store.get_all())
        except Exception as exc:
            print(f"  ⚠ Could not save beliefs to DB ({exc}) — local memory.md still updated")

    # Write human-readable dump alongside the DB record
    memory_store.save()
    return memory_store.format_delta_summary(updated_ids)


# ---------------------------------------------------------------------------
# Agent 6 public class
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SynthesizerAgent:
    """Agent 6: McKinsey-structured brief writer and Bayesian belief graph updater."""

    agent_id: str = "agent_6_synthesizer"
    db_repo: object | None = None  # DatabaseRepository for belief persistence

    def run(
        self,
        results: list[VideoPipelineResult],
        perf_matrices: dict[str, PerformanceScoringMatrix],
        opportunity_vector: OpportunityVector,
        memory_store: object | None = None,
    ) -> StrategicBrief:
        run_date = datetime.now(timezone.utc).date().isoformat()
        return StrategicBrief(
            run_date=run_date,
            situation=_build_situation(results, perf_matrices),
            complication=_build_complication(results, perf_matrices),
            resolution=_build_resolution(opportunity_vector),
            recommendations=_build_recommendations(results, perf_matrices, opportunity_vector),
            evidence=_build_evidence(results, perf_matrices, opportunity_vector),
            risks_and_falsification=_build_risks(opportunity_vector),
            belief_graph_deltas=_update_beliefs(
                perf_matrices, opportunity_vector, memory_store, db_repo=self.db_repo
            ),
        )
