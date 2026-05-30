from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class BeliefDelta:
    """A single belief change to write to the Hermes MEMORY.md store."""

    statement: str
    evidence_strength: float  # ∈ [-1, 1]; positive confirms, negative contradicts
    tags: list[str] = field(default_factory=list)
    half_life_days: int = 60


def _hermes_base_url() -> str:
    return os.environ.get("HERMES_BASE_URL", "").rstrip("/")


# Per-process flags — set True after first failure to skip repeated network calls and warnings.
_search_unavailable: bool = False
_update_unavailable: bool = False


def search_hermes_sessions(query: str) -> list[dict]:
    """FTS5 bridge: query past ACIS run outputs stored in the Hermes session index.

    Returns matching session summaries; empty list when Hermes is not configured or unreachable.
    Used by Agent 5 (Gap Detector) to check whether a gap topic was previously identified.
    """
    global _search_unavailable  # noqa: PLW0603
    base_url = _hermes_base_url()
    if not base_url or _search_unavailable:
        return []
    try:
        import requests  # noqa: PLC0415

        resp = requests.get(
            f"{base_url}/api/sessions/search",
            params={"q": query, "limit": 10},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as exc:
        _search_unavailable = True
        print(f"  ⚠ Hermes unreachable — session search disabled for this run ({exc!s:.80})")
        return []


def update_hermes_memory(
    belief_deltas: list[BeliefDelta],
    *,
    memory_store: object | None = None,
) -> str:
    """Write belief updates to Hermes MEMORY.md via API; falls back to local MemoryStore.

    Called by Agent 6 (Synthesizer) at end of each run.
    Returns a Markdown delta summary of changes made.
    """
    if not belief_deltas:
        return "_No belief updates this run._\n"

    global _update_unavailable  # noqa: PLW0603
    base_url = _hermes_base_url()
    if base_url and not _update_unavailable:
        try:
            import requests  # noqa: PLC0415

            payload = [
                {
                    "statement": d.statement,
                    "evidence_strength": d.evidence_strength,
                    "tags": d.tags,
                    "half_life_days": d.half_life_days,
                }
                for d in belief_deltas
            ]
            resp = requests.post(
                f"{base_url}/api/memory/update",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            updated = resp.json().get("updated", [])
            lines = [
                f"- **{item.get('belief_id', '?')}**: "
                f"{item.get('statement', '')[:80]} "
                f"→ confidence {item.get('confidence', '?')}"
                for item in updated
            ]
            header = "**Hermes MEMORY.md updated via API:**\n"
            return (header + "\n".join(lines) + "\n") if lines else f"Hermes: {len(belief_deltas)} belief(s) submitted.\n"
        except Exception as exc:
            _update_unavailable = True
            print(f"  ⚠ Hermes unreachable — memory update falling back to local MEMORY.md ({exc!s:.80})")

    # Local MemoryStore fallback — used when HERMES_BASE_URL is unset or Hermes is unreachable
    from acis.memory import MemoryStore  # noqa: PLC0415

    if not isinstance(memory_store, MemoryStore):
        return "_Memory store not configured — belief graph not updated._\n"

    memory_store.decay_all()
    updated_ids: list[str] = []
    for delta in belief_deltas:
        b = memory_store.update(
            statement=delta.statement,
            evidence_strength=delta.evidence_strength,
            tags=delta.tags,
            half_life_days=delta.half_life_days,
        )
        updated_ids.append(b.belief_id)
    memory_store.save()
    return memory_store.format_delta_summary(updated_ids)
