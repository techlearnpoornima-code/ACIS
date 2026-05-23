# Autonomous Creator Intelligence System (ACIS)
## Requirements Analysis & Architecture Document
**Version 2.0 — May 2026**
**Stack: Hermes Agent + AgentScope**

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement & Strategic Context](#2-problem-statement--strategic-context)
3. [Stakeholder Analysis](#3-stakeholder-analysis)
4. [Framework Architecture Decision](#4-framework-architecture-decision)
5. [Functional Requirements](#5-functional-requirements)
6. [Non-Functional Requirements](#6-non-functional-requirements)
7. [System Architecture](#7-system-architecture)
8. [Agent Specifications](#8-agent-specifications)
9. [Data Architecture](#9-data-architecture)
10. [Memory & Longitudinal Learning Layer](#10-memory--longitudinal-learning-layer)
11. [Multi-Modal Analytics Pipeline](#11-multi-modal-analytics-pipeline)
12. [Tool & MCP Layer](#12-tool--mcp-layer)
13. [Infrastructure & Deployment](#13-infrastructure--deployment)
14. [Risk Register](#14-risk-register)
15. [Implementation Roadmap](#15-implementation-roadmap)
16. [Appendices](#16-appendices)

---

## 1. Executive Summary

The Autonomous Creator Intelligence System (ACIS) is a multi-agent competitive intelligence platform for the AI creator ecosystem, built on two complementary frameworks: **Hermes Agent** (NousResearch) as the persistent runtime and learning layer, and **AgentScope** as the multi-agent orchestration engine.

Hermes provides what no custom implementation can cheaply replicate: a closed learning loop with agent-curated memory, autonomous skill creation, FTS5 session search, cross-session belief persistence, and a cron scheduler with multi-platform delivery. AgentScope provides production-grade multi-agent orchestration with MsgHub broadcasting, sequential and fanout pipelines, MCP tool integration, and built-in OpenTelemetry observability.

Together they handle the hard infrastructure problems — persistence, scheduling, observability, multi-platform delivery — leaving ACIS's engineering effort focused entirely on the intelligence layer: the six analysis agents, the hype scoring model, the saturation algorithms, and the belief graph logic.

**Primary output:** A structured strategic brief containing saturated topic maps, white-space opportunity vectors, hook performance scores, narrative reliability assessments, and confidence-weighted recommendations — delivered to Telegram, CLI, or any configured Hermes gateway.

---

## 2. Problem Statement & Strategic Context

### 2.1 The Competitive Intelligence Gap

AI creators on YouTube operate in a high-velocity, high-saturation environment. Topics that were white-space six weeks ago can become oversaturated within two content cycles. Without systematic tracking:

- Creators replicate competitors' topics with no differentiation signal
- Performance drivers (hook style, thumbnail aesthetics, framing) are understood anecdotally rather than empirically
- Narrative trends (the shift from "no-code automation" to "vibe coding") are detected weeks late
- Hype inflation — unrealistic income claims, certainty language — goes unquantified despite being a key trust variable

### 2.2 Why Existing Approaches Fail

| Approach | Limitation |
|---|---|
| Manual research | Not scalable, subjective, no longitudinal tracking |
| Basic scrapers + LLM summaries | Stateless, no correlation, no drift detection |
| Social listening tools | Optimised for brand monitoring, not epistemic content analysis |
| YouTube Analytics (native) | Single-channel only, no competitive view |
| Custom LangGraph pipelines | High build cost; no native memory, scheduling, or delivery |

### 2.3 Core Hypotheses

1. **Performance is predictable.** Hook taxonomy, thumbnail aesthetics, and topic positioning have measurable correlations with view velocity that can be learned and compounded over time.
2. **Narrative drift is detectable early.** Semantic token frequency shifts across a 4–6 week rolling window surface trend direction before it becomes obvious.
3. **Hype is quantifiable.** Income claim taxonomy, certainty language ratios, and tool-capability validation can produce a reliable hype inflation score.
4. **Longitudinal compounding is the moat.** A system that updates beliefs across runs via Hermes's persistent memory has increasing returns; a stateless scraper does not.

---

## 3. Stakeholder Analysis

### 3.1 Primary Users

**Individual AI Creators**
- Goal: Identify content opportunities before saturation; understand what hook styles work in their niche
- Pain: Hours spent manually watching competitor content with no structured output
- Delivery: Hermes gateway → Telegram or CLI; scheduled weekly brief

**Content Strategy Agencies**
- Goal: Data-driven briefs for client channels across the AI/agent ecosystem
- Pain: No cross-channel structured view; all insights are qualitative
- Delivery: Hermes batch runner; JSON or Markdown brief export

### 3.2 Secondary Stakeholders

**Investors / Analysts** — diligence on creator economy positioning and narrative trends

**Platform Researchers** — studying narrative drift and hype patterns in emerging tech content

### 3.3 Out of Scope (v1.0)

- Non-YouTube platforms (Twitter/X, LinkedIn, newsletters)
- Non-English language content
- Real-time alerting (batch runs only in v1.0)

---

## 4. Framework Architecture Decision

### 4.1 Hermes Agent — The Runtime Layer

Hermes Agent (NousResearch) is the persistent agent runtime that ACIS runs inside. It is not an orchestration framework — it is the environment in which agents live between runs.

**What Hermes provides to ACIS:**

| Hermes Capability | ACIS Usage |
|---|---|
| **Skills system** | Each ACIS analysis pipeline is packaged as a Hermes skill, callable by name |
| **Persistent MEMORY.md** | Strategic beliefs, confirmed trends, and channel baselines survive across sessions |
| **FTS5 session search** | Query past run outputs by topic: `"what did we find about Claude Code last month"` |
| **Cron scheduler** | Weekly automated runs with delivery to configured platform |
| **Multi-platform gateway** | Brief delivery via Telegram, Discord, CLI, or email — no custom delivery code |
| **Provider abstraction** | Switch LLM backend (Anthropic → OpenRouter → OpenAI) with `hermes model`, no code changes |
| **Subagent spawning** | Hermes can spawn isolated subagents for parallel channel processing |

**What Hermes does NOT replace:**

- The six analysis agent logic (still custom-built)
- The AgentScope orchestration graph
- The PostgreSQL/pgvector data layer

### 4.2 AgentScope — The Orchestration Layer

AgentScope orchestrates the six ACIS agents within each run. It replaces LangGraph entirely.

**What AgentScope provides:**

| AgentScope Capability | ACIS Usage |
|---|---|
| **`ReActAgent`** | Base class for all six ACIS agents |
| **`SequentialPipeline`** | Chains Agent 1 → Agent 2 in order |
| **`FanoutPipeline`** | Runs Agent 3 (Hook Analyzer) and Agent 4 (Performance Correlator) concurrently |
| **`MsgHub`** | Agent 5 (Gap Detector) broadcasts cross-channel synthesis to Agent 6 |
| **`Toolkit` + MCP** | YouTube ingestion tools registered as MCP server; callable by agents |
| **`AsyncSQLAlchemyMemory`** | Per-run short-term session memory backed by PostgreSQL |
| **Built-in OTel** | All agent calls traced automatically; no custom observability code |
| **Structured output** | Pydantic-based routing and schema enforcement across agent boundaries |

### 4.3 Division of Responsibility

```
┌─────────────────────────────────────────────────────────────────┐
│                        HERMES AGENT                             │
│  Persistent runtime · Skills · MEMORY.md · Cron · Gateway      │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                    AGENTSCOPE                           │  │
│   │  Agent orchestration · Pipelines · MsgHub · Toolkit     │  │
│   │                                                         │  │
│   │   [A1]→[A2]→[A3‖A4]→[A5]→[A6]   (per-run graph)       │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│   PostgreSQL + pgvector  (structured + semantic persistence)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Functional Requirements

### 5.1 Data Ingestion Pipeline

**FR-1.1 Channel Targeting**
Accept a configurable list of target YouTube channel IDs or handles via `config/channels.yaml`. Initial scope: Liam Ottley, Nick Saraev, Alex Finn, plus 7 configurable slots. Editable without code changes.

**FR-1.2 Ingestion Depth**
Per run, fetch the latest N videos per channel (default: N=10, range: 5–50). Support full historical bootstrap mode and incremental delta mode (new videos only since last run).

**FR-1.3 Transcript Extraction**
- Primary: `youtube-transcript-api` for auto-generated captions
- Fallback: `yt-dlp` audio extraction → Whisper transcription (~20–30% of videos lack captions)
- Output: Raw transcript with timestamp segments; first 60 seconds flagged as hook zone

**FR-1.4 Metadata Extraction**
Extract and store: `video_id`, `channel_id`, `title`, `description`, `upload_date`, `view_count`, `like_count`, `comment_count`, `duration_seconds`, `thumbnail_url`.

**FR-1.5 Thumbnail Asset Fetching**
Download high-resolution thumbnail binary (`maxresdefault` → `hqdefault` fallback). Store locally with database reference.

**FR-1.6 Incremental Deduplication**
Skip videos already present in the database (matched by `video_id`). Log skipped count. Re-process only with `--force-reprocess` flag.

**FR-1.7 MCP Tool Exposure**
All ingestion functions (YouTube API fetch, transcript extraction, thumbnail download) are registered as AgentScope `Toolkit` tools, exposable as an MCP server via `mcp_serve.py` for Hermes to invoke directly.

---

### 5.2 Multi-Agent Orchestration Pipeline (AgentScope)

**FR-2.1 Orchestration Graph**
Implement the execution graph using AgentScope pipelines:

```
SequentialPipeline: [Agent1 → Agent2]
         ↓
FanoutPipeline (concurrent): [Agent3 ‖ Agent4]
         ↓
MsgHub broadcast: [Agent5 receives all channel outputs]
         ↓
Sequential: [Agent6]
```

**FR-2.2 Agent 1 — Channel Researcher (`ReActAgent`)**
Inputs: Raw API metadata + transcript text (via Toolkit tools)
Processing:
- Normalise all metadata fields to canonical schema
- Chunk transcript into segments: hook (0–60s), body (60–80%), outro (80–100%)
- Detect language; flag non-English
- Validate transcript completeness (flag if < 60% of duration covered)
- Generate `ChannelResearchNode` JSON

Output: `ChannelResearchNode` passed as `Msg` to pipeline

**FR-2.3 Agent 2 — Topic Extractor (`ReActAgent`)**
Inputs: `ChannelResearchNode` via `Msg`
Processing:
- Extract technical entities: tools, frameworks, platforms, languages
- Extract concept clusters: business models, use cases, architectural patterns
- Extract monetisation signals: course mentions, affiliate references, SaaS plugs
- Score topic salience per video (TF-IDF weighted against channel corpus)
- Update channel-level semantic graph (nodes = topics, edges = co-occurrence)

Output: `SemanticGraphUpdate` — topic list with salience scores + monetisation flags

**FR-2.4 Agent 3 — Hook Analyzer (`ReActAgent`, concurrent)**
Inputs: Hook-zone transcript (first 60s), video title, thumbnail description
Processing:
- Classify hook into primary taxonomy (STATUS, ANTI_CORPORATE, MONEY, URGENCY, TECHNICAL_AUTHORITY, CURIOSITY_GAP, TRANSFORMATION)
- Assign secondary taxonomy if applicable
- Extract income claims with figure, type (`self`, `client`, `hypothetical`, `vague`), and context
- Score emotional intensity (1–10) and certainty language ratio

Output: `HookProfile` — taxonomy + income claims + intensity scores

**FR-2.5 Agent 4 — Performance Correlator (`ReActAgent`, concurrent with A3)**
Inputs: `ChannelResearchNode`, `SemanticGraphUpdate`, `HookProfile`
Processing:
- Calculate age-normalised view velocity: `views / max(days_since_upload, 1)`
- Apply under-7-days penalty: `velocity × (age_days / 7)` if age < 7 days
- Calculate channel-relative velocity multiplier: `video_velocity / channel_median_velocity_30d`
- Correlate hook taxonomy, topic cluster, duration bucket, upload day-of-week → velocity multiplier
- Apply Mann-Whitney U significance test (p < 0.05); surface only significant correlations
- Flag statistical breakouts: velocity > (channel_mean + 2σ)

Output: `PerformanceScoringMatrix` — correlation table + breakout flags

**FR-2.6 Agent 5 — Strategic Gap Detector (`ReActAgent`, MsgHub)**
Inputs: `SemanticGraphUpdate` from all channels (broadcast via MsgHub), historical memory from Hermes MEMORY.md + pgvector
Processing:
- Build cross-channel saturation map: channels covering each topic in last 30/60/90 days
- Compute saturation score: `(channels_covering / total_channels) × recency_weight`
- Identify white-space candidates: saturation < 0.25 + positive adjacent velocity + non-trivial search interest
- Cross-reference Hermes MEMORY.md for historical "already flagged" topics
- Produce ranked opportunity vector (top 5 gaps with evidence chain and confidence)

Output: `OpportunityVector` — ranked gaps with saturation scores and confidence

**FR-2.7 Agent 6 — Recommendation Synthesizer (`ReActAgent`)**
Inputs: All upstream `Msg` outputs + Hermes memory layer
Processing:
- Aggregate all upstream outputs into executive brief structure
- Construct evidence chain per recommendation
- Run self-critique loop: generate 3 falsification conditions per recommendation
- Update Hermes MEMORY.md: increment/decrement belief confidence
- Format output as Markdown brief (McKinsey structure: Situation → Complication → Resolution → Evidence → Risks → Belief Deltas)

Output: `StrategicBrief` Markdown + updated MEMORY.md delta

---

### 5.3 Hermes Memory & Longitudinal Learning

**FR-3.1 Hermes MEMORY.md as Belief Store**
Strategic beliefs are written to Hermes's persistent `MEMORY.md` in structured format:

```markdown
## Strategic Beliefs

### BELIEF-001
Statement: MONEY hooks outperform TECHNICAL_AUTHORITY hooks by >2× velocity on Liam Ottley
Confidence: 0.82
Evidence count: 14
Last confirmed: 2026-05-14
Decay half-life: 60 days
Tags: hook-taxonomy, liam-ottley, performance
```

Hermes's memory system handles cross-session persistence natively — no custom database layer required for belief storage.

**FR-3.2 FTS5 Session Search for Contrastive Memory**
Hermes's built-in FTS5 session search enables queries against all past run outputs:
- "What did we conclude about Claude Code saturation in March?"
- "Show all times the MONEY hook belief was updated"
- "Find runs where evaluations was flagged as a white-space opportunity"

Agent 5 (Gap Detector) uses `hermes_search_sessions()` as a Toolkit tool before finalising its opportunity vector, checking whether a gap has been previously identified.

**FR-3.3 Topic Drift Tracking**
Per-topic salience time-series stored in PostgreSQL. On each run:
- Absolute salience delta: `Δ = current − previous`
- 3-run velocity slope: rising/falling flag
- Alert threshold: slope > 0.07 per run → "rapidly rising"

**FR-3.4 Belief Confidence Decay**
Confidence decays toward 0.5 between confirmation events using half-life function:
`C(t) = 0.5 + (C₀ − 0.5) × e^(−λt)`, where `λ = ln(2) / half_life_days`

Agent 6 recalculates decay on each run before updating beliefs.

**FR-3.5 Hermes Cron Scheduling**
ACIS registered as a Hermes cron job. Natural language schedule: `"every Sunday at 8am"`. Output delivered to configured Hermes gateway (Telegram, Discord, CLI). No custom scheduler code required.

---

### 5.4 Multi-Modal Analytics

**FR-4.1 Thumbnail Vision Analysis**
Vision LLM (Claude claude-sonnet-4-20250514 via Hermes provider; GPT-4o fallback) extracts per thumbnail:
- Face present + expression (excited, serious, shocked, neutral, none)
- Text overlay character count + size estimate
- Color temperature (warm, cool, neutral)
- Composition type (face-dominant, text-dominant, product-screenshot, split-panel, abstract)
- UI screenshot present (boolean)
- Clickbait markers: arrows, circles, red highlights (boolean)

**FR-4.2 Thumbnail–Performance Correlation**
Thumbnail attributes included in Agent 4's correlation matrix. Reports which visual features correlate with velocity multiplier uplift.

---

### 5.5 Narrative Reliability Analysis

**FR-5.1 Hype Inflation Score**
Per-video composite hype score H ∈ [0, 1]:
```
H = 0.30 × income_claim_density
  + 0.25 × certainty_language_ratio
  + 0.30 × (1 − empirical_validation_ratio)
  + 0.15 × outcome_exaggeration_flag
```

**FR-5.2 Income Claim Taxonomy**
Classify each claim: `SELF_VERIFIED`, `CLIENT_ATTRIBUTED`, `HYPOTHETICAL`, `VAGUE`

**FR-5.3 Certainty Language Ratio**
Hedges (could, might, may) vs certainty markers (will, guaranteed, the only way). Ratio = certainty / (certainty + hedges).

**FR-5.4 Empirical Validation Detection**
Flag presence of: benchmark numbers, code demos, error screenshots, A/B test results, timestamped evidence. Absence penalises hype score.

---

## 6. Non-Functional Requirements

### 6.1 Performance

| Metric | Target |
|---|---|
| Full run (3 channels × 10 videos) | < 8 minutes |
| Incremental delta run | < 3 minutes |
| Single video processing | < 45 seconds |
| PostgreSQL indexed query | < 100ms |

### 6.2 Reliability

- AgentScope agent failures do not abort the run. Failed agents log error via OTel, mark video `agent_failed`, continue.
- LLM API errors: Hermes provider layer handles retry with exponential backoff (1s → 2s → 4s → 8s → 16s, max 5 retries). Provider switch via `hermes model` if persistent failure.
- YouTube API quota exhaustion: graceful halt at 80% consumption; incremental mode reduces quota usage ~80%.

### 6.3 Scalability

- Target: 20 channels × 10 videos = 200 videos per run without architectural changes
- AgentScope `FanoutPipeline` with `enable_gather=True` for concurrent channel processing
- `MAX_CONCURRENT_CHANNELS=5` configurable via Hermes config

### 6.4 Observability

AgentScope's built-in OpenTelemetry tracing is activated on init — all agent calls, token counts, and latencies traced automatically. No custom observability code.

```python
import agentscope
agentscope.init(
    project="acis",
    otlp_endpoint="http://localhost:4317",  # optional; defaults to stdout
)
```

### 6.5 Security

- All API keys in `.env` or Hermes config; never in code
- Hermes handles key storage for LLM providers natively
- No PII collected (YouTube data is public)

### 6.6 Reproducibility

- All LLM inputs/outputs stored via `AsyncSQLAlchemyMemory` (PostgreSQL-backed)
- LLM temperature: 0 for classification tasks, 0.3 for synthesis
- Each run stamped with `run_id`; full replay possible from stored inputs

---

## 7. System Architecture

### 7.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         HERMES AGENT RUNTIME                         │
│                                                                      │
│  CLI / Telegram / Discord  ←──  hermes gateway                      │
│                                                                      │
│  MEMORY.md (beliefs)  ·  Skills  ·  FTS5 session search             │
│  Cron scheduler  ·  Provider abstraction (Claude / OpenRouter)       │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                     AGENTSCOPE RUNTIME                        │  │
│  │                                                                │  │
│  │  ┌──────────────┐   SequentialPipeline                        │  │
│  │  │  Ingestion   │──▶ [Agent1: Channel Researcher]             │  │
│  │  │  MCP Tools   │         │                                   │  │
│  │  │  (Toolkit)   │    [Agent2: Topic Extractor]                │  │
│  │  └──────────────┘         │                                   │  │
│  │                     FanoutPipeline (concurrent)               │  │
│  │                    [Agent3: Hook] ‖ [Agent4: Perf]            │  │
│  │                           │                                   │  │
│  │                     MsgHub (cross-channel broadcast)          │  │
│  │                    [Agent5: Gap Detector]                     │  │
│  │                           │                                   │  │
│  │                    [Agent6: Synthesizer]                      │  │
│  │                           │                                   │  │
│  │                    StrategicBrief → Hermes delivery           │  │
│  │                                                                │  │
│  │  OTel tracing (all agents auto-instrumented)                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────┐  ┌──────────────────────────────────┐ │
│  │   PostgreSQL 16          │  │   pgvector                       │ │
│  │   + AsyncSQLAlchemy      │  │   (semantic memory, embeddings)  │ │
│  │   (runs, videos,         │  │   text-embedding-3-large         │ │
│  │    agent outputs,        │  │                                  │ │
│  │    topic drift series)   │  └──────────────────────────────────┘ │
│  └──────────────────────────┘                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 7.2 AgentScope Execution Graph

```python
# Conceptual orchestration — src/graph/orchestrator.py

async def run_acis_pipeline(channel_results: list[IngestionPayload]) -> StrategicBrief:

    # Per-channel: sequential A1 → A2
    per_channel_outputs = []
    for payload in channel_results:
        msg = Msg("ingestion", payload.to_json(), "system")
        msg = await sequential_pipeline(
            agents=[channel_researcher, topic_extractor],
            msg=msg
        )
        # Concurrent A3 ‖ A4 per channel
        [hook_msg, perf_msg] = await fanout_pipeline(
            agents=[hook_analyzer, performance_correlator],
            msg=msg,
            enable_gather=True
        )
        per_channel_outputs.append((hook_msg, perf_msg))

    # Cross-channel: MsgHub broadcasts all outputs to Gap Detector
    async with MsgHub(
        participants=[gap_detector],
        announcement=Msg("orchestrator", summarise(per_channel_outputs), "system")
    ) as hub:
        gap_msg = await gap_detector()

    # Final synthesis
    brief_msg = await synthesizer(gap_msg)
    return parse_brief(brief_msg)
```

### 7.3 Hermes Skill Definition

ACIS is packaged as a Hermes skill callable by name from any gateway:

```markdown
<!-- ~/.hermes/skills/acis/skill.md -->
# ACIS — Creator Intelligence Brief

Runs the full ACIS competitive intelligence pipeline against configured YouTube channels.

## Usage
- "Run ACIS" — full run, all channels, 10 videos each
- "Run ACIS delta" — incremental run, new videos only
- "Run ACIS for @liamottley" — single channel run
- "Show ACIS beliefs" — display current strategic belief graph from MEMORY.md
- "What did ACIS find about Claude Code?" — FTS5 search against past run outputs

## Schedule
Every Sunday at 08:00. Deliver to Telegram.
```

### 7.4 Technology Stack

| Layer | Technology | Role |
|---|---|---|
| **Agent runtime** | Hermes Agent (NousResearch) | Persistent memory, scheduling, delivery, provider abstraction |
| **Orchestration** | AgentScope | Multi-agent pipelines, MsgHub, Toolkit, OTel |
| **Agent base class** | AgentScope `ReActAgent` | All 6 ACIS agents |
| **LLM primary** | Claude claude-sonnet-4-20250514 (via Hermes provider) | Classification, synthesis, vision |
| **LLM fallback** | OpenRouter / GPT-4o (via Hermes `hermes model`) | Rate limit failover |
| **Embeddings** | OpenAI `text-embedding-3-large` | Semantic memory, vector search |
| **Short-term memory** | `AsyncSQLAlchemyMemory` (AgentScope) | Per-run session state, PostgreSQL-backed |
| **Long-term memory** | Hermes `MEMORY.md` + FTS5 session search | Strategic beliefs, contrastive memory |
| **Vector store** | PostgreSQL 16 + pgvector | Semantic similarity search |
| **YouTube ingestion** | `youtube-transcript-api` + `yt-dlp` + Whisper | Transcripts and metadata |
| **Tool layer** | AgentScope `Toolkit` + MCP | Ingestion tools as callable agent tools |
| **Observability** | AgentScope built-in OTel | All agent traces; no custom code |
| **Scheduling** | Hermes cron | Natural language schedule, multi-platform delivery |
| **Containerisation** | Docker + docker-compose | Single-command execution |
| **Config** | Pydantic Settings + YAML + Hermes config | Type-safe with env override |
| **Runtime** | Python 3.11+ | Ecosystem fit |

---

## 8. Agent Specifications

### 8.1 Agent 1 — Channel Researcher

**AgentScope type:** `ReActAgent`

**System prompt:** You are a structured data extraction specialist for YouTube content. Your job is to normalise raw video metadata and transcript data into canonical JSON schemas. Return only valid JSON — no prose.

**Toolkit tools:**
- `fetch_video_metadata(video_id)` → normalised metadata dict
- `segment_transcript(transcript, video_duration)` → {hook, body, outro}
- `detect_language(text)` → language code
- `validate_transcript_completeness(segments, duration)` → completeness ratio

**Output schema:** `ChannelResearchNode`
```json
{
  "video_id": "string",
  "transcript_completeness": 0.94,
  "segments": {
    "hook": { "text": "...", "duration_seconds": 58 },
    "body": { "text": "...", "duration_seconds": 840 },
    "outro": { "text": "...", "duration_seconds": 120 }
  },
  "transcript_source": "api",
  "language": "en",
  "word_count": 4820,
  "words_per_minute": 142
}
```

**Error handling:** Empty transcript → mark `transcript_status: "unavailable"`, continue metadata-only.

---

### 8.2 Agent 2 — Topic Extractor

**AgentScope type:** `ReActAgent`

**System prompt:** You are a technical taxonomy specialist for the AI/agent creator ecosystem. Extract structured topic entities from transcripts. Return only valid JSON. Be precise — a mention of "LangChain" is a tool reference; a discussion of "why agents fail" is an architecture concept.

**Toolkit tools:**
- `compute_tfidf_salience(topics, channel_corpus)` → salience scores
- `update_cooccurrence_graph(topic_pairs, video_id)` → graph update
- `extract_monetisation_signals(transcript)` → signal list

**Output schema:** `SemanticGraphUpdate`
```json
{
  "technical_tools": ["LangChain", "n8n", "Claude"],
  "architectures": ["RAG", "multi-agent", "MCP"],
  "use_cases": ["lead generation", "customer support"],
  "business_models": ["agency", "course"],
  "monetisation_refs": [
    { "type": "course_plug", "product": "Agency Accelerator", "timestamp": 742 }
  ],
  "salience_scores": { "LangChain": 0.34, "MCP": 0.61 }
}
```

---

### 8.3 Agent 3 — Hook Analyzer

**AgentScope type:** `ReActAgent` (runs concurrently with Agent 4 via `FanoutPipeline`)

**System prompt:** You are a persuasion psychology and content framing analyst. Analyse the first 60 seconds of a YouTube video (transcript + title + thumbnail) and classify its hook strategy. Identify income claims precisely — distinguish self-reported, client-attributed, and hypothetical. Return only valid JSON.

**Hook taxonomy decision tree:**
```
Opens with income figure or outcome?     → MONEY
Challenges mainstream assumption?        → ANTI_CORPORATE
References status, peers, success?       → STATUS
Withholds key information until later?   → CURIOSITY_GAP
Frames problem → solution arc?           → TRANSFORMATION
Uses benchmarks, demos, technical data?  → TECHNICAL_AUTHORITY
Uses time pressure or FOMO language?     → URGENCY
```

**Output schema:** `HookProfile`
```json
{
  "primary_taxonomy": "MONEY",
  "secondary_taxonomy": "STATUS",
  "emotional_intensity": 8,
  "certainty_ratio": 0.74,
  "income_claims": [
    {
      "exact_quote": "my client generated $47,000 in 3 months",
      "figure": 47000,
      "claim_type": "client_attributed",
      "context": "Discussing automation agency results"
    }
  ],
  "hype_score": 0.71
}
```

---

### 8.4 Agent 4 — Performance Correlator

**AgentScope type:** `ReActAgent` (runs concurrently with Agent 3)

**Note:** This agent is primarily algorithmic; LLM is used only for final interpretation of correlation results, not for computation.

**Toolkit tools (compute-heavy, non-LLM):**
- `compute_velocity_multiplier(video, channel_stats)` → float
- `run_correlation_matrix(videos, attribute_groups)` → correlation table
- `mann_whitney_significance(group_a, group_b)` → p-value
- `detect_breakout_videos(videos, channel_stats)` → flagged list

**Velocity calculation:**
```python
def velocity_multiplier(video, channel):
    age_days = max((now - video.upload_date).days, 1)
    raw_velocity = video.views / age_days
    if age_days < 7:
        raw_velocity *= (age_days / 7)  # penalise incomplete ramp-up
    return raw_velocity / channel.median_velocity_30d
```

**Output schema:** `PerformanceScoringMatrix`
```json
{
  "velocity_multipliers": { "video_id_1": 2.4, "video_id_2": 0.8 },
  "correlations": [
    { "attribute": "hook_type=MONEY", "mean_multiplier": 2.31, "p_value": 0.023, "significant": true },
    { "attribute": "hook_type=TECHNICAL_AUTHORITY", "mean_multiplier": 1.12, "p_value": 0.18, "significant": false }
  ],
  "breakout_videos": ["video_id_1"],
  "top_performing_attributes": ["hook_type=MONEY", "duration_bucket=10-15min"]
}
```

---

### 8.5 Agent 5 — Strategic Gap Detector

**AgentScope type:** `ReActAgent` (receives all channel outputs via `MsgHub` broadcast)

**System prompt:** You are a strategic analyst with access to cross-channel topic saturation data and historical intelligence from past runs. Identify genuine white-space opportunities — topics with low saturation, rising adjacent interest, and no prior identification in the belief graph. Be conservative: only flag gaps you can substantiate with data. Return a ranked opportunity vector in JSON.

**Toolkit tools:**
- `compute_saturation_score(topic, window_days)` → float
- `get_adjacent_velocity(topic)` → trend direction
- `search_hermes_sessions(query)` → past run results (FTS5)
- `query_belief_graph(topic)` → existing beliefs about topic
- `pgvector_similarity_search(topic_embedding, threshold)` → similar past topics

**Saturation score:**
```python
def saturation_score(topic, window_days=60):
    channels_covering = count_channels_with_topic(topic, window_days)
    recency_weight = recency_decay(topic, half_life_days=14)
    return (channels_covering / total_channels) * recency_weight
```

**White-space criteria (all must hold):**
1. Saturation score < 0.25
2. Adjacent topic velocity slope > 0 (rising)
3. Not flagged in Hermes MEMORY.md as "previously saturated + bounced"
4. pgvector search finds no near-identical past opportunity (cosine distance > 0.15)

**Output schema:** `OpportunityVector`
```json
{
  "opportunities": [
    {
      "topic": "LLM evaluation frameworks",
      "saturation_score": 0.11,
      "confidence": 0.78,
      "evidence": [
        "Only 1 of 8 channels covered evals in last 60 days",
        "Adjacent topic 'agent reliability' rising at 0.09/run",
        "No prior ACIS identification of this gap"
      ],
      "adjacent_rising_topics": ["agent reliability", "benchmark design"]
    }
  ]
}
```

---

### 8.6 Agent 6 — Recommendation Synthesizer (with Critic Loop)

**AgentScope type:** `ReActAgent`

**System prompt:** You are a senior strategic advisor synthesising multi-channel competitive intelligence into an executive brief. Your output must be evidence-backed, falsifiable, and honest about confidence limits. After drafting each recommendation, generate 3 specific conditions under which it would be wrong. Update the belief graph with new evidence. Format output as structured Markdown.

**Processing phases:**

Phase 1 — Synthesis: Aggregate all upstream `Msg` objects into brief structure

Phase 2 — Critic loop: For each recommendation, generate 3 falsification conditions ("this is wrong if...")

Phase 3 — Belief update: Call `update_hermes_memory(belief_deltas)` to write new/updated beliefs to MEMORY.md

Phase 4 — Formatting: Output McKinsey-structure Markdown brief

**Belief update formula:**
```python
def bayesian_update(prior: float, evidence_strength: float) -> float:
    # evidence_strength ∈ [-1, 1]; negative = contradicting evidence
    lr = math.exp(evidence_strength * 2)
    posterior_odds = (prior / (1 - prior)) * lr
    return posterior_odds / (1 + posterior_odds)
```

**Brief output structure:**
```markdown
# ACIS Strategic Brief — [Date]

## Situation
[Current state of the creator ecosystem]

## Complication
[Key tensions, shifts, and emerging pressures]

## Resolution
[Recommended positioning and content angles]

## Evidence
[Data chain per recommendation]

## Risks & Falsification
[3 conditions per recommendation under which it is wrong]

## Belief Graph Deltas
[What changed in the system's strategic beliefs this run]
```

---

## 9. Data Architecture

### 9.1 Core Database Schema

```sql
-- Channels
CREATE TABLE channels (
    channel_id          VARCHAR(64) PRIMARY KEY,
    handle              VARCHAR(128),
    display_name        VARCHAR(256),
    subscriber_count    INTEGER,
    first_ingested_at   TIMESTAMPTZ,
    last_ingested_at    TIMESTAMPTZ,
    median_velocity_30d FLOAT,
    metadata            JSONB
);

-- Videos
CREATE TABLE videos (
    video_id            VARCHAR(64) PRIMARY KEY,
    channel_id          VARCHAR(64) REFERENCES channels(channel_id),
    title               TEXT NOT NULL,
    description         TEXT,
    upload_date         DATE NOT NULL,
    duration_seconds    INTEGER,
    view_count          INTEGER,
    like_count          INTEGER,
    comment_count       INTEGER,
    thumbnail_path      TEXT,
    transcript_status   VARCHAR(32),  -- 'api', 'whisper', 'unavailable'
    ingested_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Transcripts
CREATE TABLE transcripts (
    video_id            VARCHAR(64) PRIMARY KEY REFERENCES videos(video_id),
    full_text           TEXT,
    hook_text           TEXT,
    body_text           TEXT,
    outro_text          TEXT,
    word_count          INTEGER,
    source              VARCHAR(16),
    language            VARCHAR(8)
);

-- AgentScope session memory (AsyncSQLAlchemyMemory)
-- Table managed by AgentScope; schema auto-created on init
-- agentscope_messages (id, user_id, session_id, role, content, marks, created_at)

-- Agent outputs
CREATE TABLE agent_outputs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES runs(run_id),
    video_id            VARCHAR(64) REFERENCES videos(video_id),
    agent_id            VARCHAR(32),
    output_data         JSONB NOT NULL,
    llm_model           VARCHAR(64),
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    latency_ms          INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Topic drift time-series
CREATE TABLE topic_salience_series (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID REFERENCES runs(run_id),
    channel_id          VARCHAR(64) REFERENCES channels(channel_id),
    topic               TEXT NOT NULL,
    salience            FLOAT,
    delta               FLOAT,
    velocity_slope      FLOAT,
    run_timestamp       TIMESTAMPTZ NOT NULL
);
CREATE INDEX ON topic_salience_series (channel_id, topic, run_timestamp);

-- Semantic embeddings (pgvector)
CREATE TABLE topic_embeddings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            VARCHAR(64) REFERENCES videos(video_id),
    chunk_index         INTEGER,
    chunk_text          TEXT,
    embedding           VECTOR(3072),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON topic_embeddings USING ivfflat (embedding vector_cosine_ops);

-- Prediction outcomes (contrastive memory — supplements Hermes MEMORY.md)
CREATE TABLE prediction_outcomes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    belief_statement    TEXT,
    run_id              UUID REFERENCES runs(run_id),
    predicted_at        TIMESTAMPTZ,
    outcome_observed_at TIMESTAMPTZ,
    outcome_type        VARCHAR(32),  -- 'confirmed', 'refuted', 'indeterminate'
    notes               TEXT
);

-- Runs
CREATE TABLE runs (
    run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    status              VARCHAR(32),
    channels_processed  INTEGER,
    videos_processed    INTEGER,
    videos_skipped      INTEGER,
    total_input_tokens  INTEGER,
    total_output_tokens INTEGER,
    config_snapshot     JSONB
);
```

### 9.2 Memory Layering Strategy

| Memory Type | Storage | Managed By | Contents |
|---|---|---|---|
| Per-run session state | PostgreSQL (`AsyncSQLAlchemyMemory`) | AgentScope | Agent `Msg` history, tool call results |
| Strategic beliefs | Hermes `MEMORY.md` | Hermes | Belief statements, confidence scores, tags |
| Past run recall | Hermes FTS5 session index | Hermes | All run outputs, searchable by topic |
| Semantic similarity | pgvector | Custom | Topic embeddings for gap cross-reference |
| Topic drift | PostgreSQL `topic_salience_series` | Custom | Salience time-series per topic/channel |

---

## 10. Memory & Longitudinal Learning Layer

### 10.1 Hermes MEMORY.md Structure

```markdown
# ACIS Strategic Memory

## Channel Baselines
- Liam Ottley: median_velocity_30d=1847 views/day, primary_hook=MONEY, top_topic=automation_agency
- Nick Saraev: median_velocity_30d=923 views/day, primary_hook=TECHNICAL_AUTHORITY, top_topic=n8n

## Strategic Beliefs

### BELIEF-001
Statement: MONEY hooks outperform TECHNICAL_AUTHORITY by >2× velocity on Liam Ottley
Confidence: 0.82 | Evidence: 14 runs | Last confirmed: 2026-05-14 | Half-life: 60 days
Tags: hook-taxonomy, liam-ottley, performance

### BELIEF-002
Statement: "Claude Code" topic saturation crossed 0.55 threshold in April 2026
Confidence: 0.91 | Evidence: 6 runs | Last confirmed: 2026-04-28 | Half-life: 90 days
Tags: topic-saturation, claude-code

## Prediction Outcomes
- 2026-03-01: Flagged "LLM evaluations" as white-space → CONFIRMED (3 major videos since)
- 2026-02-10: Flagged "vibe coding tools" as white-space → CONFIRMED (became dominant topic)
- 2026-01-15: Flagged "AI regulation content" as white-space → REFUTED (remained niche)

## Calibration Score
Prediction accuracy (last 12 predictions): 0.75
```

### 10.2 Topic Drift Tracking Example

```
Topic: "LLM evaluations" on channel @nicksaraev

Run T₁ (Jan 2026): salience = 0.04
Run T₂ (Feb 2026): salience = 0.09   Δ = +0.05
Run T₃ (Mar 2026): salience = 0.18   Δ = +0.09  velocity = 0.07 → RISING FLAG
Run T₄ (Apr 2026): salience = 0.31   Δ = +0.13  → white-space window closing
Run T₅ (May 2026): salience = 0.47   Δ = +0.16  → saturating
```

ACIS flags the opportunity at T₃ — giving a ~4–6 week actionable window before saturation.

### 10.3 Cross-Channel Correlated Signal Detection

When ≥ 2 channels show directional shift in the same topic within a 14-day window, ACIS records a **correlated ecosystem signal** with +0.15 confidence bonus in the belief graph. This is stored in Hermes MEMORY.md as a high-confidence belief regardless of single-channel evidence count.

---

## 11. Multi-Modal Analytics Pipeline

### 11.1 Thumbnail Analysis

Invoked as an AgentScope Toolkit tool within Agent 1 (Channel Researcher):

```python
async def analyse_thumbnail(thumbnail_path: str) -> ToolResponse:
    """Analyse a YouTube thumbnail for visual content signals.

    Args:
        thumbnail_path (str): Local path to the thumbnail image file.
    """
    with open(thumbnail_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    result = await hermes_vision_call(
        image_data=image_data,
        prompt=THUMBNAIL_ANALYSIS_PROMPT,
        model="claude-sonnet-4-20250514"
    )
    return ToolResponse(content=[TextBlock(type="text", text=result)])
```

**Extraction targets per thumbnail:**
```json
{
  "face_present": true,
  "face_expression": "shocked",
  "text_overlay_chars": 18,
  "text_size": "large",
  "color_temperature": "warm",
  "composition": "face-dominant",
  "ui_screenshot_present": false,
  "clickbait_markers": {
    "arrows_present": true,
    "circles_highlights": false,
    "red_elements": true
  }
}
```

---

## 12. Tool & MCP Layer

### 12.1 Ingestion Tools (AgentScope Toolkit)

All ingestion functions are registered as AgentScope Toolkit tools and optionally exposed as an MCP server:

```python
toolkit = Toolkit()
toolkit.register_tool_function(fetch_channel_videos, preset_kwargs={"api_key": YT_API_KEY})
toolkit.register_tool_function(extract_transcript)
toolkit.register_tool_function(run_whisper_fallback)
toolkit.register_tool_function(download_thumbnail)
toolkit.register_tool_function(analyse_thumbnail)
toolkit.register_tool_function(compute_velocity_multiplier)
toolkit.register_tool_function(compute_saturation_score)
toolkit.register_tool_function(search_hermes_sessions)  # FTS5 bridge
toolkit.register_tool_function(update_hermes_memory)    # MEMORY.md write bridge
```

### 12.2 MCP Server Exposure

ACIS ingestion tools can be exposed as an MCP server, allowing Hermes's own agent loop to invoke them directly from the CLI or gateway:

```bash
# Start ACIS as MCP server
python mcp_serve.py --toolkit acis_ingestion

# Hermes can then call:
# "Fetch the latest 5 videos from @liamottley"
# "Extract the transcript for video dQw4w9WgXcQ"
```

### 12.3 Hermes–AgentScope Bridge Tools

Two bridge tools connect Hermes's persistent layer to AgentScope agents:

**`search_hermes_sessions(query: str)`**
Calls Hermes's FTS5 session search API. Used by Agent 5 to check whether a gap topic has been previously identified.

**`update_hermes_memory(belief_deltas: list[BeliefDelta])`**
Writes updated beliefs to Hermes `MEMORY.md`. Called by Agent 6 at end of each run. Handles Bayesian confidence update + decay recalculation before writing.

---

## 13. Infrastructure & Deployment

### 13.1 Docker Compose

```yaml
version: "3.9"
services:

  hermes:
    image: nousresearch/hermes-agent:latest
    volumes:
      - hermes_data:/root/.hermes
      - ./skills:/root/.hermes/skills/acis
    env_file: .env
    ports:
      - "8765:8765"  # gateway port
    depends_on:
      postgres:
        condition: service_healthy

  acis:
    build: .
    command: python run.py
    env_file: .env
    volumes:
      - ./config:/app/config:ro
      - ./output:/app/output
      - ./thumbnails:/app/thumbnails
      - hermes_data:/root/.hermes  # shared Hermes state
    depends_on:
      postgres:
        condition: service_healthy
      hermes:
        condition: service_started

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: acis
      POSTGRES_USER: acis
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U acis"]
      interval: 5s
      retries: 5

  whisper:
    image: onerahmet/openai-whisper-asr-webservice:latest
    environment:
      ASR_MODEL: medium

volumes:
  postgres_data:
  hermes_data:
```

### 13.2 Environment Variables

```bash
# LLM (Hermes manages provider routing; set in hermes config or .env)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...           # embeddings + GPT-4o fallback

# YouTube
YOUTUBE_API_KEY=AIza...

# Database
POSTGRES_PASSWORD=...
DATABASE_URL=postgresql+asyncpg://acis:${POSTGRES_PASSWORD}@postgres:5432/acis

# AgentScope OTel (optional)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# ACIS config
MAX_CONCURRENT_CHANNELS=5
VIDEOS_PER_CHANNEL=10
WHISPER_MODEL=medium
```

### 13.3 Directory Structure

```
acis/
├── run.py                        # Entrypoint (invokes Hermes skill or direct)
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── config/
│   └── channels.yaml
├── migrations/
│   └── 001_initial_schema.sql
├── skills/                       # Hermes skills directory (mounted)
│   └── acis/
│       ├── skill.md              # Hermes skill definition
│       └── MEMORY.md             # Belief graph (Hermes-managed)
├── src/
│   ├── ingestion/
│   │   ├── youtube_client.py
│   │   ├── transcript_extractor.py
│   │   ├── whisper_fallback.py
│   │   └── thumbnail_fetcher.py
│   ├── agents/
│   │   ├── channel_researcher.py
│   │   ├── topic_extractor.py
│   │   ├── hook_analyzer.py
│   │   ├── performance_correlator.py
│   │   ├── gap_detector.py
│   │   └── synthesizer.py
│   ├── graph/
│   │   └── orchestrator.py       # AgentScope pipelines + MsgHub
│   ├── tools/
│   │   ├── toolkit.py            # Toolkit registration
│   │   ├── ingestion_tools.py
│   │   ├── analytics_tools.py
│   │   └── hermes_bridge.py      # search_hermes_sessions, update_hermes_memory
│   ├── db/
│   │   ├── models.py
│   │   └── repository.py
│   └── utils/
│       ├── config.py
│       └── rate_limiter.py
├── output/
│   └── briefs/
├── thumbnails/
└── tests/
```

### 13.4 Execution

```bash
# First-time setup
cp .env.example .env
# Fill in API keys; configure Hermes provider:
hermes model  # select Claude / OpenRouter / etc.

# Start all services
docker compose up --build

# Trigger ACIS via Hermes CLI
hermes
> Run ACIS

# Trigger ACIS via Telegram (after hermes gateway setup)
# → "Run ACIS delta"

# Direct Python execution (without Hermes gateway)
docker compose run acis python run.py
docker compose run acis python run.py --mode=delta
docker compose run acis python run.py --channel="@liamottley" --videos=5

# View current belief graph
hermes
> Show ACIS beliefs

# Query past runs
hermes
> What did ACIS find about Claude Code last month?
```

---

## 14. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| YouTube API quota exhaustion | Medium | High | Quota tracker + graceful halt; incremental mode reduces usage ~80% |
| Transcript unavailability (~20–30%) | High | Medium | Whisper fallback; metadata-only processing if both fail |
| Hermes–AgentScope bridge latency | Low | Medium | Bridge tools are thin wrappers; FTS5 search < 50ms locally |
| MEMORY.md write conflicts (concurrent runs) | Low | High | File lock on `update_hermes_memory`; single-writer guarantee |
| AgentScope `AsyncSQLAlchemyMemory` schema drift | Low | Medium | Pin AgentScope version; run migrations on version bump |
| LLM rate limits during concurrent fanout | Medium | Medium | Hermes provider retry + AgentScope tool interruption handling |
| Velocity bias for new videos (< 7 days) | High | Medium | Age-normalised weighting; 7-day minimum gate |
| pgvector index degradation at scale | Low | Medium | IVFFlat with nlist=100; periodic VACUUM ANALYZE |
| Belief corruption from bad run | Low | High | MEMORY.md is append-friendly; bad run = don't commit delta |
| Whisper quality on AI jargon | Medium | Low | Medium model; post-correction wordlist for common AI terms |

---

## 15. Implementation Roadmap

### Phase 1 — Foundation (Weeks 1–3)

- [ ] Hermes Agent installed and configured (provider:OpenAI and Claude via Anthropic API)
- [ ] AgentScope installed; `agentscope.init()` with PostgreSQL memory backend
- [ ] YouTube ingestion pipeline + Whisper fallback
- [ ] Agent 1 (Channel Researcher) as `ReActAgent` with Toolkit tools
- [ ] Agent 2 (Topic Extractor) as `ReActAgent`
- [ ] `SequentialPipeline` connecting A1 → A2
- [ ] PostgreSQL schema + migrations
- [ ] CLI runner via `python run.py`

**Exit criteria:** `SequentialPipeline` ingests 3 channels × 10 videos and produces `SemanticGraphUpdate` JSON per video.

### Phase 2 — Intelligence Pipeline (Weeks 4–6)

- [ ] Agent 3 (Hook Analyzer) as `ReActAgent`
- [ ] Agent 4 (Performance Correlator) as `ReActAgent` + compute tools
- [ ] `FanoutPipeline` running A3 ‖ A4 concurrently
- [ ] Agent 5 (Gap Detector) with `MsgHub` cross-channel broadcast
- [ ] Agent 6 (Synthesizer) with critic loop
- [ ] Full brief output to Markdown file

**Exit criteria:** End-to-end run produces a readable strategic brief with opportunity vector and hook correlation data.

### Phase 3 — Memory & Hermes Integration (Weeks 7–9)

- [ ] Hermes MEMORY.md belief graph structure defined
- [ ] `update_hermes_memory` bridge tool — writes belief deltas from Agent 6
- [ ] `search_hermes_sessions` bridge tool — FTS5 search for Agent 5
- [ ] Belief confidence decay function in Agent 6
- [ ] Hermes skill definition (`skill.md`) — ACIS callable from CLI
- [ ] Hermes cron job — weekly Sunday 8am schedule
- [ ] Topic drift tracking — `topic_salience_series` table populated per run

**Exit criteria:** Second run shows measurable MEMORY.md updates; drift alerts fire correctly; `hermes` CLI can invoke `Run ACIS`.

### Phase 4 — Multi-Modal, MCP & Delivery (Weeks 10–12)

- [ ] Thumbnail vision analysis in Agent 1
- [ ] Thumbnail–performance correlation in Agent 4
- [ ] Hype inflation score (FR-5.1 through FR-5.4)
- [ ] pgvector semantic gap cross-reference in Agent 5
- [ ] MCP server exposure (`mcp_serve.py`) for Hermes direct tool invocation
- [ ] Hermes gateway configured → Telegram delivery
- [ ] AgentScope OTel traces → Grafana or AgentScope Studio
- [ ] Contrastive memory prediction outcome logging
- [ ] Integration test suite

**Exit criteria:** System runs 5 consecutive weekly runs with no data integrity errors; brief delivered via Telegram; all OTel traces visible.

---

## 16. Appendices

### Appendix A — Hook Taxonomy Examples

| Taxonomy | Example Title | Key Markers |
|---|---|---|
| MONEY | "I Made $23K Last Month With This One AI Agent" | Dollar figure, first-person, past tense |
| STATUS | "Why Every Top Agency Owner Is Switching to This Stack" | Peer group reference, bandwagon |
| ANTI_CORPORATE | "OpenAI Doesn't Want You Building This" | Named antagonist, forbidden knowledge |
| URGENCY | "Build This Now Before Everyone Else Does" | Imperative, time pressure, competitive FOMO |
| TECHNICAL_AUTHORITY | "I Benchmarked 6 Agent Frameworks — Here's the Data" | Benchmark, evidence-first, specific count |
| CURIOSITY_GAP | "The One Thing Missing From Every AI Agent Tutorial" | "One thing", withholding, completion drive |
| TRANSFORMATION | "From $0 to $8K/mo: My Exact 90-Day AI Freelance Journey" | Before/after, time-bounded, specific outcome |

### Appendix B — Saturation Score Calibration

| Score | Interpretation | Action |
|---|---|---|
| 0.00–0.15 | True white space | High opportunity; validate demand signal |
| 0.16–0.30 | Early mover advantage | Act within 2–4 weeks; window closing |
| 0.31–0.55 | Moderate saturation | Differentiation required |
| 0.56–0.75 | High saturation | Avoid unless significant angle differentiation |
| 0.76–1.00 | Fully saturated | Avoid; wait for decay cycle |

### Appendix C — Estimated Operating Costs (Monthly, 4 runs/week)

| Component | Estimate | Notes |
|---|---|---|
| Claude claude-sonnet-4-20250514 (primary) | $12–$40 | ~8K tokens/video × 30 videos × 4 runs/week |
| OpenAI embeddings | $2–$5 | ~500K tokens/month |
| GPT-4o fallback (~10% of calls) | $3–$8 | Contingency via Hermes provider switch |
| Hermes Agent | $0 | Open source (MIT) |
| AgentScope | $0 | Open source |
| PostgreSQL (self-hosted) | $0–$20 | Cloud VM if not local |
| **Total** | **$17–$73/month** | |

### Appendix D — Glossary

| Term | Definition |
|---|---|
| Velocity multiplier | A video's daily view rate divided by the channel's median daily view rate over the last 30 days |
| Saturation score | Proportion of tracked channels covering a topic within a recency-weighted window |
| Belief confidence | Bayesian posterior C ∈ [0, 1] representing the system's confidence in a strategic belief |
| Topic drift | Rate of change of a topic's salience score across sequential run timestamps |
| White-space opportunity | Topic with low saturation, positive adjacent velocity, and no prior identification |
| Hook zone | First 60 seconds of transcript; primary persuasion and framing signal |
| Hype inflation score | Composite H ∈ [0, 1] measuring degree of unrealistic framing in a video's narrative |
| Contrastive memory | Record of past predictions and outcomes; used to calibrate system forecast accuracy |
| Hermes skill | A packaged capability in Hermes Agent; callable by name from any gateway interface |
| MsgHub | AgentScope's async context manager that broadcasts messages between a group of agents |
| FanoutPipeline | AgentScope pipeline that distributes one input to multiple agents concurrently |
| Bridge tool | An AgentScope Toolkit tool that wraps a Hermes API (FTS5 search, MEMORY.md write) |

---

*ACIS v2.0 — built on Hermes Agent (NousResearch) + AgentScope. Review cycle: after Phase 2 delivery and after Phase 4 delivery.*
