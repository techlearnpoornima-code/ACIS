"""AgentScope single-shot LLM topic extraction for ACIS Agent 2.

Agent 1 (Channel Researcher) runs deterministically — segmentation and
language detection are algorithmic and don't benefit from LLM reasoning.

Agent 2 (Topic Extractor) makes ONE Anthropic API call to extend the
regex baseline with topics the LLM recognises but the taxonomy doesn't cover.
Total: 1 API call per video instead of 11.

Activate via: python run.py --agentscope (requires ANTHROPIC_API_KEY)
Requires:     pip install 'acis[agents]'
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

try:
    import agentscope
    from agentscope.model import AnthropicChatModel  # noqa: F401 — kept for init_agentscope
except ImportError as _err:
    raise ImportError(
        "AgentScope is required for this module: pip install 'acis[agents]'"
    ) from _err

from acis.models import ChannelResearchNode, SemanticGraphUpdate
from acis.tools import (
    build_topic_pairs as _build_topic_pairs,
    compute_salience as _compute_salience,
    compute_tf as _compute_tf,
)

# Transcript characters sent to Claude — keeps prompt within token budget
_MAX_TRANSCRIPT_CHARS = 4000


@dataclass(slots=True)
class SingleShotTopicExtractorAgent:
    """Agent 2: one Anthropic API call extends regex-detected topics with LLM knowledge.

    Runs deterministic TopicExtractorAgent first to get a baseline, then asks
    Claude once to add any topics it recognises that the regex missed.
    Falls back to the baseline on any API or parse error.

    Requires: pip install 'acis[agents]'
    """

    agent_id: str = "agent_2_topic_extractor"
    model_name: str = "claude-sonnet-4-6"
    api_key: str | None = None

    def run(self, node: ChannelResearchNode) -> SemanticGraphUpdate:
        """One Claude call on top of the deterministic baseline."""
        from acis.agents.topic_extractor import TopicExtractorAgent  # noqa: PLC0415

        baseline = TopicExtractorAgent(agent_id=self.agent_id).run(node)

        combined_text = " ".join([
            node.segments["hook"].text,
            node.segments["body"].text,
            node.segments["outro"].text,
        ])

        prompt = (
            f"You are analysing a YouTube video for an AI creator channel.\n"
            f"Title: {node.title}\n\n"
            f"Transcript (first {_MAX_TRANSCRIPT_CHARS} chars):\n"
            f"{combined_text[:_MAX_TRANSCRIPT_CHARS]}\n\n"
            f"Regex detection already found:\n"
            f"{json.dumps({'technical_tools': baseline.technical_tools, 'architectures': baseline.architectures, 'use_cases': baseline.use_cases, 'business_models': baseline.business_models}, indent=2)}\n\n"
            f"Add any additional topics you are CONFIDENT are genuinely discussed. "
            f"Do NOT repeat topics already listed above.\n"
            f"Return ONLY a JSON object — no markdown, no explanation:\n"
            f'{{"technical_tools": [...], "architectures": [...], '
            f'"use_cases": [...], "business_models": [...]}}'
        )

        try:
            import anthropic  # noqa: PLC0415
            client = anthropic.Anthropic(
                api_key=self.api_key or os.environ.get("ANTHROPIC_API_KEY")
            )
            response = client.messages.create(
                model=self.model_name,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            additions = _parse_json(text)
        except Exception as exc:
            print(f"  ⚠ {node.video_id}: Agent 2 LLM failed ({exc!s:.100}) — using baseline")
            return baseline

        merged = {
            "technical_tools": _merge(baseline.technical_tools, additions.get("technical_tools", [])),
            "architectures":    _merge(baseline.architectures,   additions.get("architectures", [])),
            "use_cases":        _merge(baseline.use_cases,       additions.get("use_cases", [])),
            "business_models":  _merge(baseline.business_models, additions.get("business_models", [])),
        }
        added_count = sum(
            len(merged[k]) - len(getattr(baseline, k))
            for k in ("technical_tools", "architectures", "use_cases", "business_models")
        )
        if added_count:
            print(f"    ✓ {node.video_id}: Agent 2 LLM added {added_count} topic(s) to baseline")

        return SemanticGraphUpdate(
            video_id=node.video_id,
            technical_tools=merged["technical_tools"],
            architectures=merged["architectures"],
            use_cases=merged["use_cases"],
            business_models=merged["business_models"],
            monetisation_refs=baseline.monetisation_refs,
            salience_scores=_compute_salience(node, merged),
            tf_scores=_compute_tf(node, merged),
            topic_pairs=_build_topic_pairs(merged),
            emergent_topics=baseline.emergent_topics,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _merge(base: list[str], additions: list[str]) -> list[str]:
    """Return base + new items from additions, deduplicated case-insensitively."""
    seen = {t.lower() for t in base}
    return base + [t for t in additions if isinstance(t, str) and t.lower() not in seen]


def _parse_json(text: str) -> dict:
    """Parse JSON from model output, tolerating markdown code fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return json.loads(text)


# ── Initialisation ─────────────────────────────────────────────────────────────

def init_agentscope(
    model_name: str = "claude-sonnet-4-6",
    api_key: str | None = None,
) -> dict[str, Any]:
    """Initialise AgentScope and return model config for SingleShotTopicExtractorAgent.

    Args:
        model_name: Anthropic model identifier (default: 'claude-sonnet-4-6').
        api_key: Anthropic API key; omit to read from ANTHROPIC_API_KEY env var.
    """
    agentscope.init(project="acis")
    return {"model_name": model_name, "api_key": api_key}
