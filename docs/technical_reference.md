# ACIS — Technical Reference

**AI Competitive Intelligence System**  
A 6-agent pipeline — deterministic by default, LLM-powered via AgentScope — that analyses YouTube AI creator channels and produces a McKinsey-structured strategic brief with actionable content recommendations. Hermes Agent provides the persistent runtime: cross-session belief memory, FTS5 session search, cron scheduling, and multi-platform brief delivery.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Data Flow](#2-data-flow)
3. [Agents In Depth](#3-agents-in-depth)
   - [Agent 1 — Channel Researcher](#agent-1--channel-researcher)
   - [Agent 2 — Topic Extractor](#agent-2--topic-extractor)
     - [YAML taxonomy](#yaml-taxonomy-configtopicsyaml)
     - [Emergent topic detection](#emergent-topic-detection)
   - [Agent 3 — Hook Analyzer](#agent-3--hook-analyzer)
   - [Agent 4 — Performance Correlator](#agent-4--performance-correlator)
   - [Agent 5 — Gap Detector](#agent-5--gap-detector)
   - [Agent 6 — Synthesizer](#agent-6--synthesizer)
4. [Metrics Deep Dive](#4-metrics-deep-dive)
   - [Salience Score](#salience-score)
   - [Velocity & Velocity Multiplier](#velocity--velocity-multiplier)
   - [Hype Score and Its Components](#hype-score-and-its-components)
   - [Saturation Score & Opportunity Confidence](#saturation-score--opportunity-confidence)
5. [Data Models (States)](#5-data-models-states)
6. [Memory System](#6-memory-system)
7. [Configuration](#7-configuration)
8. [CLI Reference](#8-cli-reference)
9. [Database Schema](#9-database-schema)
10. [AgentScope Integration](#10-agentscope-integration)
    - [Why AgentScope?](#why-agentscope)
    - [ReActAgent mode vs. deterministic pipeline](#reactagent-mode-vs-deterministic-pipeline)
    - [Agent 1 toolkit](#agent-1-toolkit)
    - [Agent 2 toolkit](#agent-2-toolkit)
    - [Fallback behaviour](#fallback-behaviour)
11. [Hermes Integration](#11-hermes-integration)
    - [What Hermes provides](#what-hermes-provides)
    - [Hermes bridge](#hermes-bridge-srcacishermes_bridgepy)
    - [Agent wiring](#agent-wiring)
    - [Skill packaging](#skill-packaging-skillsacisskillmd)
    - [Docker deployment](#docker-deployment)
    - [MCP server](#mcp-server-mcp_servepy)

---

## 1. Architecture Overview

```
YouTube API / Sample Data
         │
         ▼
  IngestionService              ← collects IngestionPayloads per channel
         │
         ▼  (per video)
   Agent 1  Channel Researcher  → ChannelResearchNode
         │
   Agent 2  Topic Extractor     → SemanticGraphUpdate
         │
   Agent 3  Hook Analyzer       → HookProfile
         │
         ▼  (per channel, after all videos)
   Agent 4  Performance Correlator → PerformanceScoringMatrix
         │
         ▼  (cross-channel, once)
   Agent 5  Gap Detector        → OpportunityVector
         │
   Agent 6  Synthesizer         → StrategicBrief + MemoryStore update
```

**Execution order:**
- Agents 1–3 run for **every video**, one after another
- Agent 4 runs **once per channel** after all that channel's videos are processed (needs the full corpus to compute median velocity)
- Agents 5–6 run **once at the end**, consuming every channel's results together

---

## 2. Data Flow

### Input

Each video enters as an `IngestionPayload`. This is the raw bundle before any analysis.

```python
IngestionPayload(
    metadata=VideoMetadata(
        video_id="abc123",
        channel_id="liam-ottley",
        title="I Built a $10k/mo AI Agency in 30 Days",
        upload_date=date(2024, 11, 1),
        duration_seconds=720,      # 12 minutes
        view_count=85000,
        like_count=3200,
        comment_count=410,
        transcript_source="api",   # 'api' | 'whisper' | 'unavailable'
    ),
    transcript_segments=[
        TranscriptSegment(start=0,   duration=5, text="what's up everyone"),
        TranscriptSegment(start=5,   duration=4, text="today I'm going to show you"),
        TranscriptSegment(start=720, duration=6, text="check out my course link below"),
    ],
    comments=[
        VideoComment(comment_id="c1", author="Alice", text="this changed my life",
                     like_count=12, published_at="2024-11-02T10:00:00Z"),
    ]
)
```

### Output

The pipeline produces a `RunSummary` with all agent outputs attached. The final human-readable output is `output/strategic_brief.md`.

---

## 3. Agents In Depth

### Agent 1 — Channel Researcher

**File:** `src/acis/agents/channel_researcher.py`  
**Input:** `IngestionPayload`  
**Output:** `ChannelResearchNode`

**What it does:**  
Takes raw video data and prepares it for all downstream agents. The most important job is splitting the transcript into three **time windows** — each window is analysed separately because different parts of a video serve different purposes.

**Time window segmentation:**

```
0s ──────────── 60s ──────────── 80% of duration ──────────── end
│    HOOK       │         BODY                  │    OUTRO    │
│  (what grabs) │  (the actual content)          │  (CTA/wrap) │
```

- **Hook (0–60s):** The opening pitch. This is what YouTube shows in previews. Agent 3 analyses this window specifically for persuasion tactics.
- **Body (60s – 80%):** The main content. Agent 2 extracts topic patterns from here.
- **Outro (80–100%):** Usually contains course plugs, community links, calls to action. Agent 2 also checks here for monetisation signals.

**Transcript completeness:**  
Measures how much of the video has caption coverage.

```python
completeness = sum(segment.duration for segment in segments) / video_duration_seconds
```

A completeness of 0.92 means captions cover 92% of the video. If it drops below 0.60, a warning is printed — the topic extractor will miss anything spoken in the uncovered gaps.

**Example output:**
```python
ChannelResearchNode(
    video_id="abc123",
    transcript_completeness=0.92,
    language="en",
    word_count=1840,
    words_per_minute=153,   # typical spoken English is 120–180 wpm
    segments={
        "hook":  TextWindow(text="what's up everyone today I'm going to show you...", duration_seconds=58),
        "body":  TextWindow(text="so the first thing you need is an n8n workflow...", duration_seconds=516),
        "outro": TextWindow(text="if you want the full course link in description...", duration_seconds=146),
    }
)
```

---

### Agent 2 — Topic Extractor

**File:** `src/acis/agents/topic_extractor.py`  
**Input:** `ChannelResearchNode`  
**Output:** `SemanticGraphUpdate`

**What it does:**  
Scans the full video text (title + all three windows) against a **YAML-driven taxonomy** of regex patterns. Any topic whose regex matches is "detected" for that video. Then it scores each detected topic with a **salience score** (how important this topic is to the video, not just whether it was mentioned). It also runs a separate **emergent topic detector** that surfaces tool-like names not yet in the taxonomy.

**Topic taxonomy (4 categories, defined in `config/topics.yaml`):**

| Category | What it captures | Example topics |
|---|---|---|
| `technical_tools` | Specific software, models, platforms | Claude, GPT-4, n8n, Cursor, Supabase |
| `architectures` | System design patterns | multi-agent, RAG, routing, evaluation |
| `use_cases` | What problem the AI solves | customer support, code generation, outreach |
| `business_models` | How money is made | agency, course, SaaS, consulting |

**Why 4 categories?**  
Each category answers a different competitive intelligence question:
- `technical_tools` → which tools are trending or absent?
- `architectures` → what patterns are being discussed vs. ignored?
- `use_cases` → what problems does the audience want solved?
- `business_models` → how are creators monetising, and are there untapped models?

#### YAML taxonomy (`config/topics.yaml`)

The taxonomy is loaded at startup from `config/topics.yaml` by `_load_topic_patterns()` in `src/acis/tools.py`. If the file is missing or unreadable the code silently falls back to a hardcoded copy of the same patterns. This means **no code change is required to add a new tool** — edit the YAML and re-run:

```yaml
# config/topics.yaml — add a new tool entry under the right category:
technical_tools:
  NewTool:
    - '\bnew tool\b'
    - '\bnewt\b'   # abbreviation
```

Each entry is `TopicName: [list of regex patterns]`. Patterns are tested with `re.search()` against the full lowercased video text, so partial word matches work. Use `\b` word-boundary anchors to avoid false positives (e.g. `\bcursor\b(?! key)` avoids matching "cursor key").

The current taxonomy covers **77 topics** across the 4 categories.

#### Emergent topic detection

In addition to the fixed taxonomy, Agent 2 calls `detect_emergent_topics()` to automatically surface **new tool-like names** that appear in the video but are not yet in `topics.yaml`. This catches genuinely new frameworks and models before they are manually added — and **writes them back to `config/topics.yaml` immediately** so they are tracked as first-class topics on the next run.

**How it works (in `src/acis/tools.py`):**

1. Scan the title and full video text for every capitalised token matching `[A-Z][a-zA-Z0-9-]+`.
2. Count how often each token appears across the video.
3. Discard tokens that are:
   - Already in the taxonomy (checked via `_KNOWN_TOPICS_FLAT` — a lowercase frozenset of all known topic names)
   - In `_EMERGENT_EXCLUSIONS` — a curated blocklist of common English words that look capitalised in titles (e.g. `The`, `How`, `New`, `API`, `LLM`, `Model`, `Agent`)
4. Keep tokens that pass the **tool-likeness heuristic** (`_is_tool_like`):
   - CamelCase (`LangSmith`, `CrewAI`) — has a lowercase→uppercase transition
   - ALL-CAPS 2–6 characters (`MCP`, `RAG`, `SDK`)
   - Letter + digit suffix with an uppercase start (`GPT4`, `Llama3`)
   - OR: appeared in the title **and** was mentioned at least twice anywhere in the video
5. Return the top 5 most-frequent candidates.
6. **Persist to `config/topics.yaml`** — calls `_append_emergent_to_yaml()`, which writes each new name into an `emergent` category with an auto-generated word-boundary pattern, then reloads `TOPIC_PATTERNS` and `_KNOWN_TOPICS_FLAT` in-process so later videos in the same run won't re-detect the same terms.

**Auto-generated entry format:**
```yaml
emergent:
  QLoRA:
    - '\bqlora\b'
  Composio:
    - '\bcomposio\b'
```

Entries in `emergent` are picked up by `extract_topics()` on subsequent runs just like any manually added tool. Move an entry to `technical_tools` (and add richer patterns) once you have confirmed it is worth curating.

**Example:** A video discussing `QLoRA` fine-tuning before "QLoRA" was in the taxonomy would surface it as an emergent topic — it passes CamelCase detection, is not in the exclusion list, and gets written to the YAML automatically.

**Downstream use of emergent topics:**
- **Agent 5 — Gap Detector:** Includes emergent topics in the full topic pool when computing per-channel coverage, and assigns them to the `"emerging"` category in the gap analysis.
- **Agent 6 — Synthesizer:** Counts emergent topics across all results and surfaces the top 8 in the strategic brief's Situation section as *"Newly detected tools (not in taxonomy)"*.

**Example output:**
```python
SemanticGraphUpdate(
    video_id="abc123",
    technical_tools=["Claude", "n8n"],
    architectures=["agentic", "routing"],
    use_cases=["customer support"],
    business_models=["agency", "course"],
    salience_scores={
        "Claude": 0.3812,   # very central to this video
        "n8n": 0.2104,
        "agency": 0.1533,
        "course": 0.0841,   # mentioned briefly in the outro
    },
    tf_scores={"Claude": 0.0182, "n8n": 0.0091, "agency": 0.0072, "course": 0.0038},
    topic_pairs=[("Claude", "n8n"), ("Claude", "agency"), ("n8n", "agency")],
    emergent_topics=["QLoRA", "Composio", "AgentOps"],  # auto-detected; written to topics.yaml
)
```

`topic_pairs` records which topics co-occurred in the same video — this builds up a graph of which concepts are discussed together across the corpus.

`emergent_topics` lists auto-detected tool-like names that were new this run. They are written to `config/topics.yaml` under the `emergent` category during the run — no manual step needed to start tracking them.

---

### Agent 3 — Hook Analyzer

**File:** `src/acis/agents/hook_analyzer.py`  
**Input:** `ChannelResearchNode`, `SemanticGraphUpdate`  
**Output:** `HookProfile`

**What it does:**  
Analyses only the **hook window** (title + first 60 seconds) and classifies the persuasion strategy the creator used. Also computes a hype score that measures how sensationalised the content is.

**Why analyse hooks specifically?**  
The hook is the only part of a video that appears in YouTube search results, suggested thumbnails, and notification previews. It determines click-through rate independent of content quality. Understanding which hook styles correlate with high view velocity tells creators *how to frame* a video, not just *what to make it about*.

**Hook taxonomies:**

| Taxonomy | What it signals | Trigger patterns |
|---|---|---|
| `MONEY` | Revenue/income focused | `$10k`, `six-figure`, `making $X/month` |
| `STATUS` | Authority from experience | `after 6 months`, `my client`, `case study`, `here's my exact...` |
| `ANTI_CORPORATE` | Us-vs-them framing | `nobody shows you`, `the truth about`, `what gurus don't tell you` |
| `CURIOSITY_GAP` | Withheld information | `here's why`, `the secret`, `wait until you see` |
| `TRANSFORMATION` | Before/after narrative | `from X to Y`, `changed everything`, `game-changer` |
| `TECHNICAL_AUTHORITY` | Data and proof | `benchmark`, `step-by-step`, `live demo`, `I tested` |
| `URGENCY` | Time pressure | `right now`, `before it's too late`, `do this today` |

**Why classify all videos even if they're TECHNICAL_AUTHORITY?**  
The hype score is computed for **every video regardless of hook type** because hype and hook type are independent signals. A `TECHNICAL_AUTHORITY` video can still be high-hype (e.g. "I benchmarked 5 tools — insane results!!!"). A `MONEY` video can be low-hype if it cites real screenshots and hedges claims carefully. The hype score measures *credibility signals*, not *topic framing*. They answer different questions:
- Hook taxonomy → "how did they frame it to get clicks?"
- Hype score → "how trustworthy are the claims they made?"

**Example output:**
```python
HookProfile(
    video_id="abc123",
    primary_taxonomy="MONEY",         # matched "$10k/mo" pattern
    secondary_taxonomy="STATUS",      # also matched "in 30 Days" (experience signal)
    emotional_intensity=7,
    certainty_ratio=0.75,
    income_claims=[
        IncomeClaim(
            exact_quote="$10k",
            figure=10000.0,
            claim_type="self_verified",   # speaker claimed it about themselves
            context="I built a $10k/mo AI agency in 30 days using this exact system"
        )
    ],
    hype_score=0.62
)
```

---

### Agent 4 — Performance Correlator

**File:** `src/acis/agents/performance_correlator.py`  
**Input:** `channel_id`, all payloads and results for that channel  
**Output:** `PerformanceScoringMatrix`

**What it does:**  
Takes one channel's full video set and finds which content attributes (hook type, video length) statistically correlate with higher view velocity. Uses non-parametric statistics so no normality assumption is needed.

**Why run per channel, not across all channels?**  
Different channels have wildly different baseline velocities. A video with 500 views/day might be a breakout for a small channel but below-average for a large one. By normalising within each channel we compare videos on a level playing field — a multiplier of 2.1 means "this video got 2.1× the channel's normal rate", which is meaningful regardless of channel size.

**Example output:**
```python
PerformanceScoringMatrix(
    channel_id="nick-saraev",
    channel_median_velocity=3738.0,
    velocity_multipliers={
        "nick-001": 2.14,
        "nick-002": 0.88,
        "nick-003": 1.31,
    },
    correlations=[
        CorrelationResult(attribute="duration_bucket=10-15min",
                          mean_multiplier=1.49, p_value=0.030, significant=True),
        CorrelationResult(attribute="hook_type=TECHNICAL_AUTHORITY",
                          mean_multiplier=1.22, p_value=0.061, significant=False),
    ],
    breakout_videos=["nick-001"],
    top_performing_attributes=["duration_bucket=10-15min"]
)
```

---

### Agent 5 — Gap Detector

**File:** `src/acis/agents/gap_detector.py`  
**Input:** all `VideoPipelineResult`s across all channels  
**Output:** `OpportunityVector`

**What it does:**  
Identifies content gaps — topics that exist in the taxonomy but that no (or very few) channels in the corpus have covered. A gap is valuable when it's adjacent to topics that *are* trending (meaning the audience exists, they're just not getting this content yet).

**Example output:**
```python
OpportunityVector(
    opportunities=[
        OpportunityItem(
            topic="Gemini",
            saturation_score=0.0,     # zero channels covered it
            confidence=0.85,
            evidence=["No channel covered 'Gemini' in this run window",
                      "Adjacent topics with rising salience: Claude, Claude Code, Cursor"],
            adjacent_rising_topics=["Claude", "Claude Code", "Cursor"]
        ),
    ],
    channels_analyzed=3,
    videos_analyzed=30
)
```

---

### Agent 6 — Synthesizer

**File:** `src/acis/agents/synthesizer.py`  
**Input:** all previous outputs + optional `MemoryStore`  
**Output:** `StrategicBrief`

Assembles all agent outputs into a McKinsey SCR (Situation–Complication–Resolution) brief, writes actionable recommendations, and updates the belief store. See [Memory System](#6-memory-system) for how beliefs are updated.

---

## 4. Metrics Deep Dive

### Salience Score

**What it answers:** "How central is this topic to this specific video — not just whether it was mentioned, but how much of the video is about it?"

**Why not just use a binary detected/not-detected flag?**  
A video might say "Claude" once in passing ("you could use Claude for this") vs. a video where Claude is the entire subject. Both would be "detected", but only the second video is actually valuable signal for a Claude-focused competitor analysis. Salience captures this difference.

**Step-by-step calculation:**

**Step 1 — Build a token counter for the video**

The full text (title + hook + body + outro) is lowercased, tokenised by word boundary, and common stopwords (`a`, `the`, `is`, `to`, etc.) are removed.

```
Text: "today we build a claude agent with n8n claude handles the routing"
Tokens after stopwords: ["today", "we", "build", "claude", "agent", "n8n",
                         "claude", "handles", "routing"]
Token counts: {"claude": 2, "n8n": 1, "agent": 1, "routing": 1, ...}
Total tokens: 9
```

**Step 2 — Compute raw Term Frequency (TF)**

```
TF("Claude") = 2 / 9 = 0.2222
TF("n8n")    = 1 / 9 = 0.1111
```

TF alone has a problem: in a 1-hour video with 8,000 words, "Claude" appearing 10 times gives `TF = 0.00125`, which looks tiny even though it's actually substantial. That's why we apply log normalisation.

**Step 3 — Log-normalise TF**

```
log_TF = log(1 + TF × 100) / log(101)
```

The `× 100` stretches the range so that even small TF values register on the scale. Dividing by `log(101)` normalises the result to [0, 1].

```
log_TF("Claude") = log(1 + 0.2222 × 100) / log(101)
                 = log(23.22) / log(101)
                 = 3.145 / 4.615
                 = 0.681

log_TF("n8n")    = log(1 + 0.1111 × 100) / log(101)
                 = log(12.11) / log(101)
                 = 2.494 / 4.615
                 = 0.540
```

**Step 4 — Compute coverage**

Multi-word topics like "Claude Code" are tokenised into `["claude", "code"]`. Coverage checks how many of those tokens actually appear in the video.

```
Topic "Claude Code" → tokens: ["claude", "code"]
  "claude" appears → yes
  "code" appears   → yes
  coverage = 2/2 = 1.0   (full match)

Topic "GitHub Copilot" → tokens: ["github", "copilot"]
  "github" appears → no
  "copilot" appears → yes
  coverage = 1/2 = 0.5   (partial match — mentioned generically)
```

**Step 5 — Final salience**

```
salience = log_TF × coverage

salience("Claude")     = 0.681 × 1.0 = 0.681
salience("n8n")        = 0.540 × 1.0 = 0.540
salience("Claude Code") = 0.540 × 1.0 = 0.540  (if both tokens present)
salience("GitHub Copilot") = 0.380 × 0.5 = 0.190  (partial match penalty)
```

**Interpretation guide:**

| Salience | What it means |
|---|---|
| 0.5 – 1.0 | Core topic — the video is substantially about this |
| 0.2 – 0.5 | Supporting topic — mentioned frequently but not the main focus |
| 0.05 – 0.2 | Peripheral mention — brought up once or twice |
| < 0.05 | Incidental — barely appears, possibly coincidental |

---

### Velocity & Velocity Multiplier

#### Velocity (views/day)

**What it answers:** "How fast is this video accumulating views, normalised for its age?"

Raw view count is useless for comparison. A 3-year-old video with 500,000 views might be performing worse than a 2-week-old video with 50,000 views. Velocity fixes this.

```python
velocity = view_count / age_days
```

**The ramp-up penalty:**  
YouTube's algorithm pushes new videos hard in the first few days — a spike that doesn't reflect long-term performance. Without a correction, a 2-day-old video with a burst of algorithm traffic would look like a breakout when it's actually just new.

```python
if age_days < 7:
    velocity = velocity × (age_days / 7)
```

**Worked example:**

| Video | Views | Age | Raw velocity | Penalty | Final velocity |
|---|---|---|---|---|---|
| A (2 days old) | 20,000 | 2 | 10,000/day | × 2/7 = 0.286 | **2,857/day** |
| B (30 days old) | 90,000 | 30 | 3,000/day | none | **3,000/day** |
| C (1 year old) | 500,000 | 365 | 1,370/day | none | **1,370/day** |

Without the penalty, Video A would look 3× better than B. With it, B correctly ranks higher — it has sustained performance, not an algorithm burst.

#### Channel Median Velocity

**Why median, not mean?**  
A single breakout video can skew the mean dramatically. If one video gets 10× the channel's normal views, the mean would suggest every video performs at "5× normal" when in reality 9 out of 10 are average. The **median** is robust to outliers and gives a true picture of the channel's typical performance level.

```
Channel videos: [800, 950, 1100, 1200, 950, 12000, 850, 1050, 900, 1150]
Mean:   2095 views/day  ← skewed by the 12,000 outlier
Median: 1000 views/day  ← reflects what a typical video actually gets
```

#### Velocity Multiplier

**What it answers:** "Did this specific video over- or under-perform relative to what this channel normally gets?"

```
multiplier = video_velocity / channel_median_velocity
```

| Multiplier | Interpretation |
|---|---|
| > 2.0 | Strong outperformer |
| 1.0 – 2.0 | Above-average |
| 0.5 – 1.0 | Below-average |
| < 0.5 | Underperformer |

**Example:**
```
channel_median_velocity = 1000 views/day

Video A: 2140 views/day → multiplier = 2.14  (breakout candidate)
Video B:  880 views/day → multiplier = 0.88  (slightly below average)
Video C: 1310 views/day → multiplier = 1.31  (solid performer)
```

#### Breakout Detection

A video is flagged as a **breakout** when its raw velocity exceeds the channel's mean + 2 standard deviations:

```
breakout if: velocity > channel_mean + 2σ
```

This is a standard statistical outlier definition — roughly the top 2.5% of a normal distribution. Breakout videos are highlighted in the brief because they reveal what exceptional performance looks like for that specific channel.

#### Mann-Whitney U Test

**What it answers:** "Is there a statistically significant relationship between this attribute (e.g. '10–15 min duration') and higher velocity multipliers?"

**Why not a t-test?**  
A t-test assumes the data is normally distributed. Video performance data almost never is — it's right-skewed (a few viral videos, many average ones). The Mann-Whitney U test makes no distribution assumptions, making it more reliable for this use case.

**How it works:**  
For each attribute (e.g. `duration_bucket=10-15min`), the agent splits all videos into two groups:
- **Group A:** videos that have this attribute
- **Group B:** all other videos

It then tests whether Group A's velocity multipliers are systematically higher than Group B's. The result is a p-value.

```
Group A (10-15 min videos): multipliers = [1.49, 2.14, 1.31]  mean = 1.65
Group B (all other videos):  multipliers = [0.88, 0.72, 0.95]  mean = 0.85

p-value = 0.030  →  significant (p < 0.05)
mean_multiplier = 1.49  →  these videos get 49% more views than channel average
```

A `significant=True` result tells the recommendation engine: "videos with this attribute reliably outperform — include it in the recommendation".

---

### Hype Score and Its Components

**What it answers:** "How sensationalised and unsubstantiated is this video's hook? Is it making credible claims or using clickbait tactics?"

**Why calculate hype score for every video, including TECHNICAL_AUTHORITY ones?**  
Hook taxonomy and hype score are completely independent:
- Hook taxonomy classifies *what kind of hook* was used (the framing strategy)
- Hype score measures *how credible* the claims within that hook are

A `TECHNICAL_AUTHORITY` video can still be high-hype if it says "I benchmarked 5 tools — INSANE results, this will change EVERYTHING!!!" with no actual data. A `MONEY` video can be low-hype if it says "I earned approximately $8k–$10k last month; here's the screenshot". The hype score catches this.

The strategic brief uses hype scores to:
1. Show the mean/max hype across the corpus (are creators in this space generally credible or clickbait-heavy?)
2. Inform hook recommendations — if high-hype videos underperform, recommend measured framing

**The four components:**

#### 1. Income Density

**What it is:** How many distinct money/revenue claims appear in the hook (title + first 60s), normalised to a 0–1 scale using 3 claims as the ceiling.

```python
income_density = min(len(income_claims) / 3.0, 1.0)
```

| Income claims | income_density |
|---|---|
| 0 | 0.0 |
| 1 | 0.33 |
| 2 | 0.67 |
| 3+ | 1.0 (capped) |

**What counts as an income claim?** The agent scans for:
- Dollar amounts: `$10k`, `$50,000`, `$2.5M`
- Rate expressions: `10k per month`, `$5k MRR`, `$1M ARR`
- Vague large claims: `six-figure`, `seven-figure`, `hundreds of thousands`

Each detected claim is also classified by **who it's attributed to**:

| Claim type | Example | Credibility |
|---|---|---|
| `self_verified` | "I made $10k last month" | Creator's own claim |
| `client_attributed` | "my client made $50k" | Third-party, harder to verify |
| `hypothetical` | "you could make $10k if you..." | Not a real claim |
| `vague` | "six-figure income" | No specific number |

#### 2. Certainty Ratio

**What it is:** The ratio of certainty-asserting words to hedging words. Measures whether the creator is making bold unqualified claims or being careful about what they promise.

```python
certainty_ratio = certainty_count / (certainty_count + hedge_count)
# Returns 0.5 if neither group is present
```

**Certainty words** (push ratio up): `will`, `guaranteed`, `always`, `never`, `must`, `definitely`, `certainly`, `obviously`, `absolutely`, `proven`

**Hedge words** (push ratio down): `could`, `might`, `may`, `possibly`, `perhaps`, `maybe`, `sometimes`, `potentially`, `likely`, `seems`, `appears`

**Examples:**

```
"This will DEFINITELY make you money guaranteed"
→ certainty_count = 3 (will, definitely, guaranteed)
→ hedge_count = 0
→ certainty_ratio = 3/3 = 1.0  (maximum certainty, high hype contribution)

"This might potentially help you earn more income"
→ certainty_count = 0
→ hedge_count = 2 (might, potentially)
→ certainty_ratio = 0/2 = 0.0  (measured framing, low hype contribution)

"I built this — results may vary but it seems promising"
→ certainty_count = 0
→ hedge_count = 2 (may, seems)
→ certainty_ratio = 0.0
```

#### 3. Empirical Validation

**What it is:** A boolean — does the hook contain at least one piece of concrete evidence? When `True`, it **reduces** the hype score by 0.30 (the largest single factor).

**Why does it reduce hype?**  
A video that shows a screenshot, runs a live demo, or cites actual benchmark numbers is making verifiable claims. Even if it uses strong certainty language, the presence of real evidence substantially reduces the risk that the audience is being misled.

**What counts as empirical evidence:**

| Signal | Example |
|---|---|
| `benchmark` | "I benchmarked Claude vs GPT-4" |
| `A/B test` | "I ran an A/B test on 200 emails" |
| `actual numbers/data/metrics` | "actual metrics from my real client" |
| `screenshot` | "here's the screenshot of my Stripe dashboard" |
| `proof` | "here's proof of the results" |
| `demonstrated` | "I demonstrated this works live" |
| `live build/demo/on screen` | "live build on screen" or "live demo" |

```
Hook: "I tested 5 AI coding tools — here's the benchmark data, live on screen"
→ has_empirical = True
→ hype contribution from this component: 0.30 × (1 - True) = 0.30 × 0 = 0.0
```

#### 4. Outcome Exaggeration

**What it is:** A boolean — do any income claims use vague language or suspiciously round large numbers? When `True`, it adds 0.15 to the hype score.

**What triggers it:**

```python
# Trigger 1: any claim is vague (no specific number)
claim.claim_type == "vague"   # e.g. "six-figure income"

# Trigger 2: specific but suspiciously round and large
claim.figure >= 10_000 and claim.figure % 1_000 == 0
# e.g. $10,000 / $50,000 / $1,000,000 — psychologically chosen round numbers
```

Real business revenue is rarely a perfectly round number. "$10k/month" is almost certainly a simplified/aspirational figure. "$8,847/month" is likely real data. The exaggeration flag catches the former.

#### Full Hype Score Formula

```
H = 0.30 × income_density
  + 0.25 × certainty_ratio
  + 0.30 × (1 − has_empirical_validation)
  + 0.15 × has_outcome_exaggeration
```

**Worked example 1 — high hype:**
```
Title: "How I Make $50k/Month With AI (GUARANTEED Results)"
Hook: "six-figure income, will definitely work for you, amazing results"

income_claims    = 2 ($50k + "six-figure")  → income_density = 0.67
certainty_ratio  = 3 certainty / 3 total    → 1.0
has_empirical    = False                    → 1 - False = 1.0
has_exaggeration = True ($50k is round/large) → 1.0

H = 0.30 × 0.67 + 0.25 × 1.0 + 0.30 × 1.0 + 0.15 × 1.0
  = 0.201 + 0.250 + 0.300 + 0.150
  = 0.90  ← very high hype
```

**Worked example 2 — low hype:**
```
Title: "I Tested 5 AI Coding Tools — Real Benchmark Data (2024)"
Hook: "live benchmark on screen, results might surprise you, actual metrics"

income_claims    = 0                        → income_density = 0.0
certainty_ratio  = 0 certainty / 1 hedge   → 0.0
has_empirical    = True (benchmark, live)   → 1 - True = 0.0
has_exaggeration = False                    → 0.0

H = 0.30 × 0.0 + 0.25 × 0.0 + 0.30 × 0.0 + 0.15 × 0.0
  = 0.0  ← very low hype (credible, evidence-backed)
```

**Hype score interpretation:**

| H range | Label | Meaning |
|---|---|---|
| 0.0 – 0.25 | Low | Evidence-backed, measured claims |
| 0.25 – 0.50 | Moderate | Mix of claims and evidence |
| 0.50 – 0.75 | High | Mostly unsubstantiated claims |
| 0.75 – 1.0 | Very high | Clickbait / outcome exaggeration |

---

### Saturation Score & Opportunity Confidence

#### Saturation Score

**What it answers:** "What fraction of monitored channels covered this topic in the last run window?"

```
saturation = channels_covering_topic / total_channels_analysed
```

**Example with 3 channels:**

| Topic | Covered by | Saturation |
|---|---|---|
| Claude | liam-ottley, nick-saraev, alex-finn | 3/3 = **1.0** (fully saturated) |
| n8n | liam-ottley, nick-saraev | 2/3 = **0.67** (widespread) |
| Gemini | none | 0/3 = **0.0** (white space) |

White-space threshold is `saturation < 0.25` — any topic covered by fewer than 1 in 4 channels is considered an opportunity.

#### Opportunity Confidence

**What it answers:** "How reliable is this gap signal? Should we act on it?"

A topic with saturation 0.0 could be white space (great opportunity) *or* it could just be irrelevant to the audience (no one covers it because no one cares). Confidence tries to distinguish between the two by incorporating adjacency (related hot topics), corpus size, and any cross-channel salience signal.

```
confidence = 0.35 × (1 − saturation)   # how big is the gap?
           + 0.25 × adjacency_factor    # are related topics already trending?
           + 0.25 × corpus_factor       # how much data did we have?
           + 0.15 × salience_factor     # where it was covered, was it central?
```

**Component breakdown:**

| Component | Formula | What it captures |
|---|---|---|
| `gap_factor` | `1 − saturation` | Bigger gap = higher confidence |
| `adjacency_factor` | `min(adjacent_count / 3, 1.0)` | Adjacent trending topics prove audience exists |
| `corpus_factor` | `min(video_count / 20, 1.0)` | More videos = more reliable signal |
| `salience_factor` | `min(mean_salience × 10, 1.0)` | Where covered, was it core or peripheral? |

**Worked example:**

```
Topic: "Gemini"
saturation     = 0.0    → gap_factor = 1.0
adjacent_count = 3 (Claude, Claude Code, Cursor) → adjacency_factor = min(3/3, 1) = 1.0
video_count    = 30     → corpus_factor = min(30/20, 1) = 1.0
mean_salience  = 0.0 (not covered anywhere) → salience_factor = 0.0

confidence = 0.35 × 1.0 + 0.25 × 1.0 + 0.25 × 1.0 + 0.15 × 0.0
           = 0.35 + 0.25 + 0.25 + 0.0
           = 0.85
```

High confidence (0.85) because the gap is total, the corpus is big enough to trust it, and there are 3 adjacent topics already trending — the audience clearly exists and is hungry for related content.

---

## 5. Data Models (States)

Each agent passes its output to the next. These are the typed state objects.

```
IngestionPayload          ← raw video data from YouTube or sample file
        │ Agent 1
ChannelResearchNode       ← segmented transcript, completeness, quality metrics
        │ Agent 2
SemanticGraphUpdate       ← topics, salience scores, TF scores, topic co-occurrences
        │ Agent 3
HookProfile               ← taxonomy, hype score, income claims, intensity
        │ (bundled)
VideoPipelineResult       ← A1 + A2 + A3 outputs for one video
        │ Agent 4 (per channel)
PerformanceScoringMatrix  ← velocity stats, correlations, breakouts
        │ Agent 5 (cross-channel)
OpportunityVector         ← ranked white-space opportunities with evidence
        │ Agent 6
StrategicBrief            ← McKinsey brief with recommendations
```

### Complete field reference

**`IngestionPayload`**
```python
metadata: VideoMetadata          # API response fields
transcript_segments: list[TranscriptSegment]
comments: list[VideoComment]     # top-N by relevance
full_text: str                   # property: all segment texts joined
```

**`ChannelResearchNode`**
```python
video_id: str
channel_id: str
title: str
transcript_completeness: float   # 0–1; warn if < 0.60
transcript_source: str           # 'api' | 'whisper' | 'unavailable'
language: str                    # 'en' | 'unknown' | ISO code
word_count: int
words_per_minute: int
segments: dict[str, TextWindow]  # 'hook' | 'body' | 'outro'
metadata: dict[str, Any]         # normalised VideoMetadata fields
```

**`SemanticGraphUpdate`**
```python
video_id: str
technical_tools: list[str]       # taxonomy-matched tools (from config/topics.yaml)
architectures: list[str]         # taxonomy-matched architecture patterns
use_cases: list[str]             # taxonomy-matched use-case topics
business_models: list[str]       # taxonomy-matched monetisation models
monetisation_refs: list[dict]    # course plugs, community links detected in outro
salience_scores: dict[str, float]
tf_scores: dict[str, float]      # raw TF per topic (for future IDF computation)
topic_pairs: list[tuple[str,str]]# co-occurrence edges for graph analysis
emergent_topics: list[str]       # auto-detected tool-like terms; written to topics.yaml under 'emergent'
```

**`HookProfile`**
```python
video_id: str
primary_taxonomy: str            # dominant hook style
secondary_taxonomy: str | None   # second match if present
emotional_intensity: int         # 1–10 (exclamations + intensity words + CAPS)
certainty_ratio: float           # 0–1 (certainty / (certainty + hedges))
income_claims: list[IncomeClaim] # each with figure, claim_type, context
hype_score: float                # 0–1 composite
```

**`PerformanceScoringMatrix`**
```python
channel_id: str
channel_median_velocity: float           # views/day baseline
velocity_multipliers: dict[str, float]   # video_id → multiplier vs median
correlations: list[CorrelationResult]    # all hook + duration results, sorted desc
breakout_videos: list[str]               # video_ids at mean + 2σ
top_performing_attributes: list[str]     # significant correlations only (p < 0.05)
```

**`OpportunityItem`**
```python
topic: str
saturation_score: float             # 0–1
confidence: float                   # 0–1
evidence: list[str]                 # 2–4 human-readable evidence bullets
adjacent_rising_topics: list[str]   # up to 5 co-trending topics
```

---

## 6. Memory System

**File:** `src/acis/memory.py` | **Output:** `output/memory.md`

The memory store allows ACIS to learn across runs. Each run either confirms or challenges existing beliefs, and confidence is updated accordingly using a Bayesian model.

### Belief format (MEMORY.md)

```markdown
### BELIEF-001
Statement: 'Gemini' is a white-space opportunity (saturation 0.00)
Confidence: 0.85 | Evidence count: 3 | Last confirmed: 2026-05-22 | Decay half-life: 30 days
Tags: white-space, opportunity
```

### Bayesian confidence update

When a belief is confirmed by new evidence:

```
lr = exp(evidence_strength × 2)
posterior_odds = (prior / (1 − prior)) × lr
new_confidence = posterior_odds / (1 + posterior_odds)
```

| Scenario | evidence_strength | Effect |
|---|---|---|
| White-space confirmed again | +0.25 | Moderate confidence increase |
| Strong performance correlation (> 2× multiplier) | +0.60 | Large confidence increase |
| Topic now appears (gap closed) | −0.25 | Confidence decreases |

**Worked example:**

```
Prior confidence: 0.62 (first observation)
New run confirms gap still exists: evidence_strength = +0.25

lr = exp(0.25 × 2) = exp(0.5) = 1.649
prior_odds = 0.62 / (1 − 0.62) = 0.62 / 0.38 = 1.632
posterior_odds = 1.632 × 1.649 = 2.692
new_confidence = 2.692 / (1 + 2.692) = 0.729
```

After 3 confirming runs, confidence reaches ~0.85. After 5 runs, ~0.91.

### Decay model

Confidence drifts back toward 0.5 (uncertain) if a belief is not confirmed:

```
C(t) = 0.5 + (C₀ − 0.5) × e^(−λt)
λ = ln(2) / half_life_days
```

| Days since last run | Confidence (starting at 0.85, half-life 30d) |
|---|---|
| 0 | 0.850 |
| 30 | 0.675 |
| 60 | 0.588 |
| 90 | 0.544 |
| 120 | 0.522 |

At 120 days without confirmation the belief is essentially neutral — the system stops acting on it.

---

## 7. Configuration

**File:** `config/channels.yaml`

```yaml
default_video_limit: 10
channels:
  - channel_id: liam-ottley    # internal slug — stable DB key
    handle: "@liamottley"      # exact YouTube @handle for live API
    display_name: "Liam Ottley"
```

### Ingestion modes

| Mode | Data source | Required env vars |
|---|---|---|
| `--full` | `data/sample_channels.json` | None |
| `--agentscope` | Sample or live | `ANTHROPIC_API_KEY` |
| Live (default) | YouTube Data API v3 | `YOUTUBE_API_KEY` |

---

## 8. CLI Reference

```bash
uv run python run.py --full                        # sample data, all 6 agents
uv run python run.py --full --channel @liamottley  # single channel
uv run python run.py                               # live YouTube mode
uv run python run.py --force-reprocess             # ignore DB deduplication
uv run python run.py --limit 5                     # cap at 5 videos per channel
uv run python run.py --agentscope                  # LLM agents for A1+A2
```

| Flag | Default | Description |
|---|---|---|
| `--full` | off | Sample data, all 6 agents |
| `--memory PATH` | `output/memory.md` | Belief store path |
| `--limit N` | from config | Max videos per channel |
| `--channel @handle` | all | Single channel filter |
| `--force-reprocess` | off | Bypass DB deduplication |
| `--output PATH` | `output/latest_run.json` | JSON output path |
| `--model MODEL_ID` | `claude-sonnet-4-6` | Anthropic model for `--agentscope` |

### Output files

| File | Contents |
|---|---|
| `output/latest_run.json` | Full structured run (all agent outputs) |
| `output/strategic_brief.md` | McKinsey brief with recommendations |
| `output/memory.md` | Persistent belief store |

---

## 9. Database Schema

| Table | Agent | Key columns |
|---|---|---|
| `channels` | Ingestion | `channel_id`, `handle` |
| `runs` | Every run | `run_id`, `started_at`, `status` |
| `videos` | Ingestion | `video_id`, `upload_date`, `view_count`, `duration_seconds` |
| `transcripts` | Ingestion | `video_id`, `hook_text`, `body_text`, `outro_text`, `source` |
| `transcript_cache` | Ingestion | `video_id`, `segments_json` (raw), `source`, `fetched_at` |
| `video_comments` | Ingestion | `video_id`, `like_count` |
| `agent_outputs` | Pipeline | `video_id`, `agent_id`, `output_json` |
| `topic_tf` | Agent 2 | `video_id`, `topic`, `tf_score` |
| `topic_salience_series` | Agent 2 | `video_id`, `topic`, `salience`, `run_date` |
| `hook_profiles` | Agent 3 | `video_id`, `primary_taxonomy`, `hype_score` |
| `performance_matrices` | Agent 4 | `channel_id`, `channel_median_velocity` |
| `opportunity_vectors` | Agent 5 | `run_id`, `topic`, `saturation_score`, `confidence` |
| `strategic_briefs` | Agent 6 | `run_id`, `recommendations` |
| `prediction_outcomes` | Future | Tracks whether recommendations proved correct |

**Deduplication:** On live runs, the pipeline loads all existing `video_id`s from the `videos` table before fetching from YouTube. Any already-ingested video is skipped and counted in `videos_skipped`. Use `--force-reprocess` to bypass this.

**Transcript cache (`transcript_cache` table):** Raw transcript segments (`[{start, duration, text}]`) are stored as JSONB after the first YouTube fetch. On all subsequent runs — including `--force-reprocess` — transcripts are served from this table and the YouTube API is never called again for that video. For videos processed before this table existed, `get_cached_transcript()` falls back to reconstructing three pseudo-segments from the `transcripts` table (hook/body/outro text) so existing data is also reused without a network call.

---

## 10. AgentScope Integration

### Why AgentScope?

The deterministic agents (Agents 1–3) follow fixed code paths: segment transcript, match regex patterns, score salience. This is fast and reproducible but cannot recognise tool names the regex taxonomy hasn't seen yet.

AgentScope's integration adds **one Claude API call per video** in Agent 2 to extend the regex baseline with topics the LLM recognises from its world knowledge. Agent 1 remains fully deterministic — transcript segmentation and language detection are algorithmic operations that gain nothing from LLM reasoning.

**Activate with:** `python run.py --agentscope` (requires `ANTHROPIC_API_KEY` and `pip install 'acis[agents]'`)

### Single-shot mode vs. deterministic pipeline

```
Deterministic mode (default):
  IngestionPayload → ChannelResearchAgent (fixed code)   → ChannelResearchNode
  ChannelResearchNode → TopicExtractorAgent (regex only) → SemanticGraphUpdate
  API calls per video: 0

AgentScope mode (--agentscope):
  IngestionPayload → ChannelResearchAgent (fixed code)         → ChannelResearchNode
  ChannelResearchNode → SingleShotTopicExtractorAgent (1 call) → SemanticGraphUpdate
  API calls per video: 1
```

In both modes the output types are identical. Agents 3–6 always run deterministically regardless of mode.

### How SingleShotTopicExtractorAgent works

**File:** `src/acis/agents/agentscope.py` — `SingleShotTopicExtractorAgent`  
**Model:** `claude-sonnet-4-6` via `anthropic.Anthropic().messages.create()`  
**API calls:** 1 per video

```
1. Run TopicExtractorAgent deterministically → baseline topics
2. Send ONE prompt to Claude:
     - title + transcript (first 4000 chars)
     - baseline topics already found by regex
     - "add anything genuinely present that regex missed"
3. Parse JSON response → extract additions per category
4. Merge additions into baseline (deduplicated, case-insensitive)
5. Recompute salience, TF, and topic pairs on merged set
```

**Why not a ReAct loop?** A ReAct loop makes one API call per tool call — for a fixed deterministic sequence that was 11 calls per video. Since the tool order is always the same, a single prompt with the full transcript delivers the same result at 1/11th the cost and without rate-limit pressure.

**Fallback:** Any API or JSON parse error silently returns the deterministic baseline — the run always completes.

```python
# Console output when LLM adds topics:
✓ abc123: Agent 2 LLM added 2 topic(s) to baseline
```

### Initialisation

```python
from acis.agents.agentscope import init_agentscope, SingleShotTopicExtractorAgent

model_config = init_agentscope(model_name="claude-sonnet-4-6", api_key="sk-ant-...")
agent2 = SingleShotTopicExtractorAgent(**model_config)
```

`init_agentscope()` calls `agentscope.init(project="acis")` and returns `{"model_name": ..., "api_key": ...}`. The agent calls `anthropic.Anthropic()` directly — no AgentScope model wrapper in the hot path.

---

## 11. Hermes Integration

### What Hermes provides

Hermes Agent (NousResearch) is the **persistent runtime layer** that ACIS runs inside. It is not an orchestration framework — it is the environment agents live in between runs.

| Hermes capability | How ACIS uses it |
|---|---|
| **Persistent MEMORY.md** | Strategic beliefs survive across runs via Bayesian confidence updates |
| **FTS5 session search** | Agent 5 queries past run outputs: "was this gap previously identified?" |
| **Cron scheduler** | ACIS runs automatically every Sunday at 08:00 — no cron infrastructure needed |
| **Multi-platform gateway** | Strategic brief delivered to Telegram or CLI — no custom delivery code |
| **Provider abstraction** | Switch LLM backend (Anthropic → OpenRouter → OpenAI) with `hermes model` |
| **Skill system** | ACIS packaged as a named skill, callable from any Hermes gateway |

Hermes runs as a Docker container (port 8765). When `HERMES_BASE_URL` is set, ACIS routes memory and search calls to the Hermes API. When it is unset, ACIS falls back to a local `output/memory.md` file — so the pipeline runs without Hermes in all development and sample-data scenarios.

### Hermes bridge (`src/acis/hermes_bridge.py`)

The bridge is the sole integration point between the ACIS Python codebase and the Hermes runtime. It exports three public symbols:

**`BeliefDelta` dataclass**

```python
@dataclass
class BeliefDelta:
    statement: str           # human-readable belief statement
    evidence_strength: float # ∈ [-1, 1]; positive = confirms, negative = contradicts
    tags: list[str]          # e.g. ["white-space", "opportunity"]
    half_life_days: int      # confidence decay speed (30 = fast, 90 = slow)
```

**`search_hermes_sessions(query: str) → list[dict]`**

Calls `GET {HERMES_BASE_URL}/api/sessions/search?q={query}&limit=10`. Returns a list of matching session summaries from the Hermes FTS5 index — every past ACIS run output is indexed and searchable. Returns `[]` if Hermes is unreachable.

**`update_hermes_memory(belief_deltas, *, memory_store=None) → str`**

Calls `POST {HERMES_BASE_URL}/api/memory/update` with belief delta payloads. Hermes performs the Bayesian confidence update and writes to its persistent `MEMORY.md`. Falls back to `MemoryStore.update()` + local file write if Hermes is unreachable or `HERMES_BASE_URL` is unset. Returns a Markdown summary of what changed.

**Routing logic:**

```
HERMES_BASE_URL set?
  ├── yes → call Hermes HTTP API
  │          ├── success → Hermes writes MEMORY.md, returns summary
  │          └── error   → print warning, fall through to local fallback
  └── no  → local MemoryStore (output/memory.md)
```

### Agent wiring

**Agent 5 — Gap Detector** calls `search_hermes_sessions` per candidate opportunity before finalising the output:

```python
hermes_hits = search_hermes_sessions(f"gap opportunity {topic}")
evidence = _build_evidence_chain(..., hermes_hits=hermes_hits)
```

The evidence chain reads:
- `"Recurring gap: confirmed in N prior ACIS run(s) via Hermes FTS5"` — when past sessions match
- `"First-time detection — no prior ACIS session confirms this gap"` — when no hits

**Agent 6 — Synthesizer** collects `BeliefDelta` objects from all performance correlations and white-space opportunities, then calls `update_hermes_memory` once at end of run:

```python
belief_deltas = [
    BeliefDelta(
        statement="duration_bucket=10-15min correlates with >1.5x velocity on nick-saraev",
        evidence_strength=0.60,
        tags=["performance-correlation", "duration_bucket", "nick-saraev"],
    ),
    BeliefDelta(
        statement="'Gemini' is a white-space opportunity (saturation 0.00)",
        evidence_strength=0.25,
        tags=["white-space", "opportunity"],
        half_life_days=30,
    ),
]
summary = update_hermes_memory(belief_deltas, memory_store=memory_store)
```

### Skill packaging (`skills/acis/skill.md`)

ACIS is packaged as a Hermes skill, stored at `skills/acis/skill.md` and mounted into the Hermes container at `~/.hermes/skills/acis/skill.md`. This allows calling ACIS from any Hermes gateway using natural language:

```
"Run ACIS"                           → full run, all channels
"Run ACIS delta"                     → incremental run, new videos only
"Run ACIS for @liamottley"           → single channel run
"Show ACIS beliefs"                  → display MEMORY.md belief graph
"What did ACIS find about Claude Code?" → FTS5 search past outputs
```

**Cron schedule** defined in `skill.md`: `Every Sunday at 08:00. Deliver to Telegram.`  
No custom scheduler code is required — Hermes interprets the natural language schedule and triggers the skill at the configured time.

### Docker deployment

`docker-compose.yml` brings up two services:

```yaml
hermes:        # NousResearch Hermes Agent — port 8765
  volumes:
    - ./skills/acis → mounted as the ACIS skill
    - ./output      → mounted as Hermes session index (makes run outputs searchable via FTS5)

postgres:      # PostgreSQL 16 — port 5432
  volumes:
    - ./migrations → auto-applied on first container start
```

**Single-command start:**
```bash
cp .env.example .env    # fill in YOUTUBE_API_KEY, ANTHROPIC_API_KEY, POSTGRES_PASSWORD
docker compose up -d
```

Set `HERMES_BASE_URL=http://localhost:8765` in `.env` to enable the bridge.

### MCP server (`mcp_serve.py`)

The MCP server exposes ACIS tools as callable endpoints for the Hermes agent loop to invoke directly — Hermes can plan its own sequence of tool calls without going through `run.py`.

```bash
uv run python mcp_serve.py   # starts on 0.0.0.0:8766 by default
```

Registered tools:

| Tool | Purpose |
|---|---|
| `segment_transcript` | Split transcript into hook / body / outro |
| `detect_language` | ISO language detection |
| `validate_transcript_completeness` | Coverage fraction |
| `extract_topics` | Regex taxonomy match |
| `compute_salience` | log-TF × coverage score |
| `compute_tf` | Raw TF per topic |
| `detect_emergent_topics` | Auto-discover tool-like names not in taxonomy; writes them to `config/topics.yaml` under `emergent` |
| `search_hermes_sessions` | FTS5 past-run search (Hermes bridge) |
| `update_hermes_memory` | Write beliefs to MEMORY.md (Hermes bridge) |

Override host/port with `MCP_HOST` and `MCP_PORT` env vars.
