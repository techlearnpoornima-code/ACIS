from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Belief dataclass
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Belief:
    """A single strategic belief entry in the ACIS belief store."""

    belief_id: str
    statement: str
    confidence: float       # 0–1; decays toward 0.5 between confirmation events
    evidence_count: int
    last_confirmed: date
    half_life_days: int     # confidence half-life for the decay model
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Math functions
# ---------------------------------------------------------------------------

def bayesian_update(prior: float, evidence_strength: float) -> float:
    """Update belief confidence from new evidence (evidence_strength ∈ [-1, 1]).

    Negative values represent contradicting evidence.
    lr = exp(evidence_strength × 2); uses log-odds update.
    """
    prior = max(0.01, min(0.99, prior))
    lr = math.exp(evidence_strength * 2)
    posterior_odds = (prior / (1 - prior)) * lr
    return round(posterior_odds / (1 + posterior_odds), 4)


def belief_decay(confidence: float, days_since_confirmation: int, half_life_days: int) -> float:
    """Decay confidence toward 0.5 using exponential half-life model (FR-3.4).

    C(t) = 0.5 + (C₀ − 0.5) × e^(−λt),  λ = ln(2) / half_life_days
    """
    if days_since_confirmation <= 0:
        return confidence
    lam = math.log(2) / max(half_life_days, 1)
    return round(0.5 + (confidence - 0.5) * math.exp(-lam * days_since_confirmation), 4)


# ---------------------------------------------------------------------------
# MEMORY.md parser and writer
# ---------------------------------------------------------------------------

_BELIEF_HEADER = re.compile(r"^###\s+(BELIEF-\S+)", re.MULTILINE)
_FIELD_LINE = re.compile(r"^(\w[\w\s]+?):\s*(.+)$", re.MULTILINE)


def _parse_belief_block(block_id: str, block_text: str) -> Belief | None:
    """Parse one BELIEF-xxx block; returns None on any parse error."""
    fields: dict[str, str] = {}
    for m in _FIELD_LINE.finditer(block_text):
        fields[m.group(1).strip().lower()] = m.group(2).strip()
    try:
        statement = fields.get("statement", "")
        # Support "0.82" or "0.82 | Evidence count: 14 | ..." on same line
        conf_raw = fields.get("confidence", "0.5").split("|")[0].strip()
        confidence = float(conf_raw)
        evidence_count = int(fields.get("evidence count", "0"))
        last_confirmed_raw = fields.get("last confirmed", "")
        last_confirmed = (
            date.fromisoformat(last_confirmed_raw.split("|")[0].strip())
            if last_confirmed_raw else date.today()
        )
        half_raw = fields.get("decay half-life", "60").split()[0]
        half_life_days = int(half_raw)
        tags_raw = fields.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        return Belief(
            belief_id=block_id,
            statement=statement,
            confidence=confidence,
            evidence_count=evidence_count,
            last_confirmed=last_confirmed,
            half_life_days=half_life_days,
            tags=tags,
        )
    except (ValueError, KeyError):
        return None


def _serialize_belief(b: Belief) -> str:
    tags_str = ", ".join(b.tags) if b.tags else ""
    return (
        f"### {b.belief_id}\n"
        f"Statement: {b.statement}\n"
        f"Confidence: {b.confidence} | "
        f"Evidence count: {b.evidence_count} | "
        f"Last confirmed: {b.last_confirmed.isoformat()} | "
        f"Decay half-life: {b.half_life_days} days\n"
        f"Tags: {tags_str}\n"
    )


# ---------------------------------------------------------------------------
# MemoryStore — standalone MEMORY.md belief manager
# ---------------------------------------------------------------------------

class MemoryStore:
    """Reads, updates, and writes ACIS strategic beliefs to a MEMORY.md file.

    Uses the Hermes MEMORY.md format for forward-compatibility (FR-3.1).
    All belief logic (Bayesian update, decay, serialisation) is self-contained —
    no Hermes Python package is required.
    """

    def __init__(self, memory_path: Path) -> None:
        self._path = memory_path
        self._beliefs: dict[str, Belief] = {}
        self._header_text: str = "# ACIS Strategic Memory\n\n## Strategic Beliefs\n\n"

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Parse MEMORY.md from disk into the in-memory belief dict."""
        if not self._path.exists():
            return
        raw = self._path.read_text(encoding="utf-8")
        positions = [(m.group(1), m.start()) for m in _BELIEF_HEADER.finditer(raw)]
        if not positions:
            return
        self._header_text = raw[: positions[0][1]]
        for i, (bid, start) in enumerate(positions):
            end = positions[i + 1][1] if i + 1 < len(positions) else len(raw)
            belief = _parse_belief_block(bid, raw[start:end])
            if belief is not None:
                self._beliefs[bid] = belief

    def save(self) -> None:
        """Serialise all beliefs back to MEMORY.md."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = self._header_text
        for belief in sorted(self._beliefs.values(), key=lambda b: b.belief_id):
            body += _serialize_belief(belief) + "\n"
        self._path.write_text(body, encoding="utf-8")

    # ------------------------------------------------------------------
    # Belief management
    # ------------------------------------------------------------------

    def _next_belief_id(self) -> str:
        if not self._beliefs:
            return "BELIEF-001"
        last = max(int(bid.split("-")[1]) for bid in self._beliefs)
        return f"BELIEF-{last + 1:03d}"

    def decay_all(self, as_of: date | None = None) -> None:
        """Apply time-based confidence decay to every belief."""
        ref = as_of or datetime.now(timezone.utc).date()
        for belief in self._beliefs.values():
            days = (ref - belief.last_confirmed).days
            belief.confidence = belief_decay(belief.confidence, days, belief.half_life_days)

    def update(
        self,
        statement: str,
        evidence_strength: float,
        tags: list[str] | None = None,
        half_life_days: int = 60,
        belief_id: str | None = None,
    ) -> Belief:
        """Upsert a belief using a Bayesian confidence update from new evidence.

        Matches an existing belief by belief_id first, then by statement prefix.
        Creates a new belief when no match is found.
        """
        today = datetime.now(timezone.utc).date()
        tags = tags or []

        target: Belief | None = None
        if belief_id and belief_id in self._beliefs:
            target = self._beliefs[belief_id]
        else:
            prefix = statement[:60].lower()
            for b in self._beliefs.values():
                if b.statement[:60].lower() == prefix:
                    target = b
                    break

        if target is not None:
            target.confidence = bayesian_update(target.confidence, evidence_strength)
            target.evidence_count += 1
            target.last_confirmed = today
            for tag in tags:
                if tag not in target.tags:
                    target.tags.append(tag)
            return target

        new_id = belief_id or self._next_belief_id()
        initial_confidence = bayesian_update(0.5, evidence_strength)
        new_belief = Belief(
            belief_id=new_id,
            statement=statement,
            confidence=initial_confidence,
            evidence_count=1,
            last_confirmed=today,
            half_life_days=half_life_days,
            tags=tags,
        )
        self._beliefs[new_id] = new_belief
        return new_belief

    def get_all(self) -> list[Belief]:
        """Return all beliefs sorted by belief_id."""
        return sorted(self._beliefs.values(), key=lambda b: b.belief_id)

    def format_delta_summary(self, updated_ids: list[str]) -> str:
        """Return a Markdown delta summary for the given belief IDs."""
        if not updated_ids:
            return "_No belief updates this run._\n"
        lines: list[str] = []
        for bid in updated_ids:
            b = self._beliefs.get(bid)
            if b:
                lines.append(
                    f"- **{bid}**: {b.statement[:80]} "
                    f"→ confidence {b.confidence:.2f} (evidence: {b.evidence_count} runs)"
                )
        return "\n".join(lines) + "\n"
