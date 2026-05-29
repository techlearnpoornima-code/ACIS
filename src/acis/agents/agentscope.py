"""AgentScope ReActAgent implementations for ACIS Agent 1 and Agent 2.

These are opt-in alternatives to the plain Python agents in agents/.
The LLM reasons over tool calls in the ReAct loop instead of following a
fixed deterministic pipeline. Both agents fall back gracefully to the
deterministic implementation if the LLM fails to call the finalise tool
within max_iters.

Activate via: python run.py --agentscope (requires ANTHROPIC_API_KEY).
Requires:     pip install 'acis[agents]'
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

try:
    import agentscope
    from agentscope.agent import ReActAgent
    from agentscope.formatter import AnthropicChatFormatter
    from agentscope.message import Msg, TextBlock
    from agentscope.model import AnthropicChatModel
    from agentscope.tool import Toolkit, ToolResponse
except ImportError as _err:
    raise ImportError(
        "AgentScope is required for this module: pip install 'acis[agents]'"
    ) from _err

from acis.models import (
    ChannelResearchNode,
    IngestionPayload,
    SemanticGraphUpdate,
    TextWindow,
    TranscriptSegment,
)
from acis.tools import (
    build_topic_pairs as _build_topic_pairs,
    compute_salience as _compute_salience,
    compute_tf as _compute_tf,
    detect_language as _detect_language,
    extract_monetisation_signals as _extract_monetisation_signals,
    extract_topics as _extract_topics,
    normalise_metadata,
    segment_transcript as _segment_transcript,
    validate_transcript_completeness as _validate_completeness,
    word_count as _word_count,
    words_per_minute as _words_per_minute,
)

# ── System prompts ─────────────────────────────────────────────────────────────

_AGENT1_SYS_PROMPT = """\
You are Agent 1 — Channel Research Agent for ACIS (Autonomous Creator Intelligence System).

Call the tools in this exact order. Steps 1–4 take NO arguments — they operate on the
video already loaded:

  1. segment_transcript()               — splits transcript into hook / body / outro windows
  2. detect_language()                  — identifies the language (ISO 639-1 code)
  3. count_words()                      — counts total words in the transcript
  4. get_transcript_completeness()      — fraction (0.0–1.0) of video duration covered
  5. finalise_research(                 — MUST be called last
       transcript_completeness,         — float returned by step 4
       language,                        — string returned by step 2
       n_words,                         — integer returned by step 3
       n_words_per_minute,              — compute: round(n_words / (duration_seconds / 60))
     )

Rules:
- Call each tool exactly once, in order.
- Steps 1–4 take NO arguments — do not pass any input.
- Do not fabricate any values; use only what the tools return.
- If completeness < 0.6, note the low coverage before finalising.
"""

_AGENT2_SYS_PROMPT = """\
You are Agent 2 — Topic Extractor Agent for ACIS (Autonomous Creator Intelligence System).

Call the tools in this order. Steps 1–2 take NO arguments:

  1. extract_topics_by_pattern()        — regex taxonomy match; returns base topic lists
  2. extract_monetisation_signals()     — detects course plugs, retainer offers, etc.
  3. Review the transcript text provided. Merge any additional topics you are confident
     about into the four category lists. Only add topics genuinely present — do not guess.
  4. compute_topic_salience(topics_json)   — topics_json = merged JSON from steps 1+3
  5. compute_topic_tf(topics_json)         — same topics_json
  6. build_topic_pairs(topics_json)        — same topics_json
  7. finalise_semantic_graph(...)          — MUST be called last with all gathered values

Rules:
- Steps 1–2 take NO arguments — do not pass any input.
- topics_json must be a JSON object: '{"technical_tools":[...],"architectures":[...],"use_cases":[...],"business_models":[...]}'
- All *_json arguments for finalise_semantic_graph must be valid JSON strings.
- Do not fabricate salience scores or TF values — use only what the tools return.
"""

# ── Serialisation helpers ──────────────────────────────────────────────────────

def _payload_to_msg_content(payload: IngestionPayload) -> str:
    """Serialise an IngestionPayload to the JSON string passed as the initial agent Msg."""
    meta = normalise_metadata(payload)
    return json.dumps({
        "video_id": meta["video_id"],
        "title": meta["title"],
        "duration_seconds": meta["duration_seconds"],
        "full_text": payload.full_text,
        "segments": [
            {"start": s.start, "duration": s.duration, "text": s.text}
            for s in payload.transcript_segments
        ],
    }, ensure_ascii=False)


def _node_from_dict(data: dict[str, Any]) -> ChannelResearchNode:
    """Reconstruct a ChannelResearchNode from its to_dict() representation."""
    segments = {
        k: TextWindow(text=v["text"], duration_seconds=v["duration_seconds"])
        for k, v in data["segments"].items()
    }
    return ChannelResearchNode(
        video_id=data["video_id"],
        channel_id=data["channel_id"],
        title=data["title"],
        transcript_completeness=data["transcript_completeness"],
        transcript_source=data["transcript_source"],
        language=data["language"],
        word_count=data["word_count"],
        words_per_minute=data["words_per_minute"],
        segments=segments,
        metadata=data["metadata"],
    )


def _text_response(data: Any) -> ToolResponse:
    """Wrap a JSON-serialisable value in a ToolResponse with a single TextBlock."""
    return ToolResponse(content=[TextBlock(type="text", text=json.dumps(data))])


# ── Agent 1 ───────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class ReActChannelResearchAgent:
    """Agent 1 via AgentScope ReActAgent — LLM coordinates deterministic transcript tools.

    Requires: pip install 'acis[agents]'
    """

    agent_id: str = "agent_1_channel_researcher"
    model: Any = field(default=None)  # AnthropicChatModel instance from init_agentscope()
    max_iters: int = 8
    # Written by the finalise_research tool closure; read after agent completes
    _result: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def _build_toolkit(self, payload: IngestionPayload):
        toolkit = Toolkit()
        agent_self = self
        _state: dict = {}  # shared mutable state across closures

        def segment_transcript():
            """Split transcript into hook (0-60s), body (60-80%), and outro windows. No arguments needed."""
            result = _segment_transcript(payload.transcript_segments, payload.metadata.duration_seconds)
            _state["segments"] = {
                k: {"text": v.text, "duration_seconds": v.duration_seconds}
                for k, v in result.items()
            }
            return _text_response(_state["segments"])

        def detect_language():
            """Detect the primary language of the transcript. Returns an ISO 639-1 language code. No arguments needed."""
            return _text_response({"language": _detect_language(payload.full_text)})

        def count_words():
            """Count the number of words in the transcript. No arguments needed."""
            return _text_response({"word_count": _word_count(payload.full_text)})

        def get_transcript_completeness():
            """Compute what fraction (0.0–1.0) of the video duration is covered by transcript. No arguments needed."""
            return _text_response({
                "transcript_completeness": _validate_completeness(
                    payload.transcript_segments, payload.metadata.duration_seconds
                )
            })

        def finalise_research(
            transcript_completeness: float,
            language: str,
            n_words: int,
            n_words_per_minute: int,
        ):
            """Complete Agent 1. Call LAST with scalar values from the tools above.

            Args:
                transcript_completeness: Float 0.0–1.0 from get_transcript_completeness.
                language: Language code string from detect_language.
                n_words: Integer word count from count_words.
                n_words_per_minute: Compute as round(n_words / (duration_seconds / 60)).
            """
            agent_self._result = {
                "transcript_completeness": transcript_completeness,
                "language": language,
                "word_count": n_words,
                "words_per_minute": n_words_per_minute,
                "segments": _state.get("segments", {}),
            }
            return _text_response({"status": "ChannelResearchNode finalised"})

        for fn in (segment_transcript, detect_language, count_words,
                   get_transcript_completeness, finalise_research):
            toolkit.register_tool_function(fn)
        return toolkit

    def run(self, payload: IngestionPayload) -> ChannelResearchNode:
        """Run Agent 1 via ReActAgent; falls back to deterministic pipeline on any failure."""
        self._result = None
        meta = normalise_metadata(payload)

        agent = ReActAgent(
            name="ChannelResearcher",
            sys_prompt=_AGENT1_SYS_PROMPT,
            model=self.model,
            formatter=AnthropicChatFormatter(),
            toolkit=self._build_toolkit(payload),
            max_iters=self.max_iters,
        )

        asyncio.run(agent(Msg(
            name="user",
            role="user",
            content=(
                f"Analyse this video:\n"
                f"video_id: {payload.metadata.video_id}\n"
                f"title: {payload.metadata.title}\n"
                f"duration_seconds: {payload.metadata.duration_seconds}\n\n"
                f"Call the tools in order — they already have access to the transcript data."
            ),
        )))

        if self._result is None:
            print(
                f"  ⚠ {payload.metadata.video_id}: Agent 1 ReAct did not call "
                f"finalise_research — falling back to deterministic pipeline"
            )
            return self._fallback(payload)

        r = self._result
        if r["transcript_completeness"] < 0.6:
            print(
                f"  ⚠ {payload.metadata.video_id}: low transcript coverage "
                f"({r['transcript_completeness']:.0%}) — topic extraction may be incomplete"
            )
        return ChannelResearchNode(
            video_id=payload.metadata.video_id,
            channel_id=payload.metadata.channel_id,
            title=payload.metadata.title,
            transcript_completeness=r["transcript_completeness"],
            transcript_source=payload.metadata.transcript_source,
            language=r["language"],
            word_count=r["word_count"],
            words_per_minute=r["words_per_minute"],
            segments={
                k: TextWindow(text=v["text"], duration_seconds=v["duration_seconds"])
                for k, v in r["segments"].items()
            },
            metadata=meta,
        )

    def _fallback(self, payload: IngestionPayload) -> ChannelResearchNode:
        from acis.agents.channel_researcher import ChannelResearchAgent  # noqa: PLC0415
        return ChannelResearchAgent(agent_id=self.agent_id).run(payload)


# ── Agent 2 ───────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class ReActTopicExtractorAgent:
    """Agent 2 via AgentScope ReActAgent — LLM extends regex patterns with its own topic knowledge.

    Requires: pip install 'acis[agents]'
    """

    agent_id: str = "agent_2_topic_extractor"
    model: Any = field(default=None)  # AnthropicChatModel instance from init_agentscope()
    max_iters: int = 12
    _result: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def _build_toolkit(self, node: ChannelResearchNode):
        toolkit = Toolkit()
        agent_self = self
        combined_text = " ".join([
            node.segments["hook"].text,
            node.segments["body"].text,
            node.segments["outro"].text,
        ])

        def extract_topics_by_pattern():
            """Match transcript text against TOPIC_PATTERNS regexes. Returns known topics per category. No arguments needed."""
            return _text_response(_extract_topics(node))

        def extract_monetisation_signals():
            """Identify course plugs, consulting offers, retainer mentions, and cohort offers. No arguments needed."""
            return _text_response({"signals": _extract_monetisation_signals(combined_text)})

        def compute_topic_salience(topics_json: str):
            """Score each topic using log-normalised TF × coverage ratio within this video.

            Args:
                topics_json: JSON object string — '{"technical_tools":[...],"architectures":[...],"use_cases":[...],"business_models":[...]}'
            """
            topics = json.loads(topics_json)
            return _text_response(_compute_salience(node, topics))

        def compute_topic_tf(topics_json: str):
            """Compute raw per-video TF for each topic.

            Args:
                topics_json: JSON object string — same format as compute_topic_salience.
            """
            topics = json.loads(topics_json)
            return _text_response(_compute_tf(node, topics))

        def build_topic_pairs(topics_json: str):
            """Build all unique co-occurrence pairs across topic categories for graph edges.

            Args:
                topics_json: JSON object string — same format as compute_topic_salience.
            """
            topics = json.loads(topics_json)
            pairs = _build_topic_pairs(topics)
            return _text_response({"pairs": [list(p) for p in pairs]})

        def finalise_semantic_graph(
            technical_tools_json: str,
            architectures_json: str,
            use_cases_json: str,
            business_models_json: str,
            monetisation_refs_json: str,
            salience_scores_json: str,
            tf_scores_json: str,
            topic_pairs_json: str,
        ):
            """Complete Agent 2. Call this LAST with all gathered values to finalise the SemanticGraphUpdate.

            Args:
                technical_tools_json: JSON array string of tool names — '["Claude","n8n"]'.
                architectures_json: JSON array string of architecture pattern names.
                use_cases_json: JSON array string of use-case labels.
                business_models_json: JSON array string of business model labels.
                monetisation_refs_json: JSON array string from extract_monetisation_signals.
                salience_scores_json: JSON object string from compute_topic_salience.
                tf_scores_json: JSON object string from compute_topic_tf.
                topic_pairs_json: JSON array string from build_topic_pairs (list of [t1,t2] pairs).
            """
            agent_self._result = {
                "technical_tools": json.loads(technical_tools_json),
                "architectures": json.loads(architectures_json),
                "use_cases": json.loads(use_cases_json),
                "business_models": json.loads(business_models_json),
                "monetisation_refs": json.loads(monetisation_refs_json),
                "salience_scores": json.loads(salience_scores_json),
                "tf_scores": json.loads(tf_scores_json),
                "topic_pairs": json.loads(topic_pairs_json),
            }
            return _text_response({"status": "SemanticGraphUpdate finalised"})

        for fn in (extract_topics_by_pattern, extract_monetisation_signals,
                   compute_topic_salience, compute_topic_tf,
                   build_topic_pairs, finalise_semantic_graph):
            toolkit.register_tool_function(fn)
        return toolkit

    def run(self, node: ChannelResearchNode) -> SemanticGraphUpdate:
        """Run Agent 2 via ReActAgent; falls back to deterministic pipeline on any failure."""
        self._result = None
        combined_text = " ".join([
            node.segments["hook"].text,
            node.segments["body"].text,
            node.segments["outro"].text,
        ])

        agent = ReActAgent(
            name="TopicExtractor",
            sys_prompt=_AGENT2_SYS_PROMPT,
            model=self.model,
            formatter=AnthropicChatFormatter(),
            toolkit=self._build_toolkit(node),
            max_iters=self.max_iters,
        )

        asyncio.run(agent(Msg(
            name="user",
            role="user",
            content=(
                f"Extract topics for video '{node.video_id}' — title: {node.title!r}.\n\n"
                f"Transcript text:\n{combined_text}\n\n"
                f"Call the tools in order — they already have access to the research node data."
            ),
        )))

        if self._result is None:
            print(
                f"  ⚠ {node.video_id}: Agent 2 ReAct did not call "
                f"finalise_semantic_graph — falling back to deterministic pipeline"
            )
            return self._fallback(node)

        r = self._result
        return SemanticGraphUpdate(
            video_id=node.video_id,
            technical_tools=r.get("technical_tools", []),
            architectures=r.get("architectures", []),
            use_cases=r.get("use_cases", []),
            business_models=r.get("business_models", []),
            monetisation_refs=r.get("monetisation_refs", []),
            salience_scores=r.get("salience_scores", {}),
            tf_scores=r.get("tf_scores", {}),
            topic_pairs=[tuple(p) for p in r.get("topic_pairs", [])],
        )

    def _fallback(self, node: ChannelResearchNode) -> SemanticGraphUpdate:
        from acis.agents.topic_extractor import TopicExtractorAgent  # noqa: PLC0415
        return TopicExtractorAgent(agent_id=self.agent_id).run(node)


# ── Initialisation ─────────────────────────────────────────────────────────────

def init_agentscope(
    model_name: str = "claude-sonnet-4-6",
    api_key: str | None = None,
) -> Any:
    """Initialise AgentScope and return an AnthropicChatModel instance for both ReActAgents.

    Call once per process. Pass the returned model to ReActChannelResearchAgent and
    ReActTopicExtractorAgent via their model= constructor argument.

    Args:
        model_name: Anthropic model identifier (default: 'claude-sonnet-4-6').
        api_key: Anthropic API key; omit to read from ANTHROPIC_API_KEY env var.
    """
    agentscope.init(project="acis")
    return AnthropicChatModel(model_name=model_name, api_key=api_key)
