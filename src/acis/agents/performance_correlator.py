from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timezone

from acis.models import (
    CorrelationResult,
    IngestionPayload,
    PerformanceScoringMatrix,
    VideoPipelineResult,
)

# ---------------------------------------------------------------------------
# Velocity helpers
# ---------------------------------------------------------------------------

def _reference_date() -> date:
    return datetime.now(timezone.utc).date()


def compute_video_velocity(view_count: int, upload_date: date, ref: date | None = None) -> float:
    """Age-normalised views/day with under-7-days ramp-up penalty per FR-2.5."""
    if ref is None:
        ref = _reference_date()
    age_days = max((ref - upload_date).days, 1)
    raw = view_count / age_days
    if age_days < 7:
        raw *= age_days / 7
    return raw


def _channel_velocity_stats(velocities: list[float]) -> tuple[float, float, float]:
    """Return (median, mean, stdev) for a list of velocity values."""
    if not velocities:
        return 0.0, 0.0, 0.0
    med = statistics.median(velocities)
    mean = statistics.mean(velocities)
    std = statistics.stdev(velocities) if len(velocities) > 1 else 0.0
    return med, mean, std


# ---------------------------------------------------------------------------
# Mann-Whitney U significance test (no scipy dependency)
# ---------------------------------------------------------------------------

def _normal_cdf(x: float) -> float:
    """Standard normal CDF via Abramowitz & Stegun polynomial approximation."""
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    poly = t * (
        0.319381530
        + t * (-0.356563782
               + t * (1.781477937
                      + t * (-1.821255978
                             + t * 1.330274429)))
    )
    cdf = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x) * poly
    return cdf if x >= 0 else 1.0 - cdf


def mann_whitney_p_value(group_a: list[float], group_b: list[float]) -> float:
    """Two-tailed Mann-Whitney U p-value using normal approximation; returns 1.0 for tiny groups."""
    n1, n2 = len(group_a), len(group_b)
    if n1 < 2 or n2 < 2:
        return 1.0
    u = sum(
        1 if a > b else 0.5 if a == b else 0
        for a in group_a
        for b in group_b
    )
    mu_u = n1 * n2 / 2.0
    sigma_u = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    if sigma_u == 0:
        return 1.0
    z = (u - mu_u) / sigma_u
    return round(2.0 * (1.0 - _normal_cdf(abs(z))), 4)


# ---------------------------------------------------------------------------
# Duration bucket classifier
# ---------------------------------------------------------------------------

def _duration_bucket(duration_seconds: int) -> str:
    minutes = duration_seconds / 60
    if minutes < 5:
        return "duration_bucket=<5min"
    if minutes < 10:
        return "duration_bucket=5-10min"
    if minutes < 15:
        return "duration_bucket=10-15min"
    if minutes < 20:
        return "duration_bucket=15-20min"
    return "duration_bucket=>20min"


# ---------------------------------------------------------------------------
# Agent 4 public class
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PerformanceCorrelatorAgent:
    """Agent 4: algorithmic velocity and correlation analysis for one channel's video set."""

    agent_id: str = "agent_4_performance_correlator"

    def run(
        self,
        channel_id: str,
        payloads: list[IngestionPayload],
        results: list[VideoPipelineResult],
    ) -> PerformanceScoringMatrix:
        ref = _reference_date()

        # Compute raw velocities
        raw_velocities: dict[str, float] = {}
        for payload in payloads:
            vid_id = payload.metadata.video_id
            raw_velocities[vid_id] = compute_video_velocity(
                payload.metadata.view_count, payload.metadata.upload_date, ref
            )

        velocity_list = list(raw_velocities.values())
        median_vel, mean_vel, std_vel = _channel_velocity_stats(velocity_list)
        baseline = max(median_vel, 1.0)

        # Velocity multipliers (each video vs channel median)
        multipliers: dict[str, float] = {
            vid_id: round(v / baseline, 4)
            for vid_id, v in raw_velocities.items()
        }

        # Breakout detection: raw velocity > channel_mean + 2σ
        breakout_threshold = mean_vel + 2 * std_vel
        breakouts = [vid_id for vid_id, v in raw_velocities.items() if v > breakout_threshold]

        # Build attribute groups for correlation
        attribute_groups: dict[str, list[float]] = {}

        for payload, result in zip(payloads, results):
            vid_id = payload.metadata.video_id
            mult = multipliers[vid_id]

            if result.hook_profile is not None:
                hook_attr = f"hook_type={result.hook_profile.primary_taxonomy}"
                attribute_groups.setdefault(hook_attr, []).append(mult)

            dur_attr = _duration_bucket(payload.metadata.duration_seconds)
            attribute_groups.setdefault(dur_attr, []).append(mult)

        # Produce correlation rows: group vs complement
        correlations: list[CorrelationResult] = []
        all_mult = list(multipliers.values())

        for attr, group in sorted(attribute_groups.items()):
            if len(group) < 2:
                continue
            complement = [m for m in all_mult if m not in group]
            if len(complement) < 2:
                continue
            mean_mult = round(statistics.mean(group), 4)
            p_val = mann_whitney_p_value(group, complement)
            correlations.append(CorrelationResult(
                attribute=attr,
                mean_multiplier=mean_mult,
                p_value=p_val,
                significant=p_val < 0.05,
            ))

        correlations.sort(key=lambda c: c.mean_multiplier, reverse=True)
        top_attrs = [c.attribute for c in correlations if c.significant]

        return PerformanceScoringMatrix(
            channel_id=channel_id,
            channel_median_velocity=round(median_vel, 4),
            velocity_multipliers=multipliers,
            correlations=correlations,
            breakout_videos=breakouts,
            top_performing_attributes=top_attrs,
        )
