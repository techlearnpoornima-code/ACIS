# ACIS — Autonomous Creator Intelligence System

A 6-agent deterministic pipeline that analyses YouTube AI-creator channels and produces a McKinsey-structured strategic brief with actionable content recommendations.

---

## What it does

ACIS ingests videos from a configured list of YouTube channels, runs them through six analysis agents in sequence, and writes a strategic brief identifying content gaps, trending topics, and high-performing hook patterns.

```
YouTube API / Sample Data
        │
        ▼
 IngestionService         collects raw video + transcript + comments
        │
  Agent 1  Channel Researcher    → segments transcript, measures quality
  Agent 2  Topic Extractor       → detects topics, scores salience, finds emergent tools
  Agent 3  Hook Analyzer         → classifies persuasion style, computes hype score
        │
  Agent 4  Performance Correlator  → velocity stats and content-attribute correlations (per channel)
  Agent 5  Gap Detector            → finds white-space topics across all channels
  Agent 6  Synthesizer             → writes strategic brief, updates belief store
```

---

## Quick start

### 1. Install

```bash
# Base install (sample-data mode — no external dependencies)
pip install -e .

# Live mode (YouTube API + PostgreSQL)
pip install -e ".[live]"

# AgentScope LLM agents
pip install -e ".[agents]"
```

### 2. Configure channels

Edit `config/channels.yaml`:

```yaml
default_video_limit: 10
channels:
  - channel_id: liam-ottley
    handle: "@liamottley"
    display_name: "Liam Ottley"
  - channel_id: nick-saraev
    handle: "@nicksaraev"
    display_name: "Nick Saraev"
```

### 3. Set environment variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
YOUTUBE_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here        # only for --agentscope mode
DATABASE_URL=postgresql://acis:acis@localhost:5432/acis   # optional
```

### 4. Run

```bash
# Sample data — no API keys needed, all 6 agents
uv run python run.py --full

# Live YouTube data
uv run python run.py

# Single channel, force-reprocess, with belief persistence
uv run python run.py --channel @liamottley --force-reprocess --memory output/memory.md
```

---

## CLI reference

| Flag | Default | Description |
|---|---|---|
| `--full` | off | Run all 6 agents against bundled sample data (no API key needed) |
| `--memory PATH` | `output/memory.md` | Belief store path — created on first run, updated each run |
| `--limit N` | from config | Cap videos per channel |
| `--channel @handle` | all channels | Process a single channel only |
| `--force-reprocess` | off | Bypass DB deduplication and reprocess everything |
| `--mode delta\|full` | `delta` | `delta` skips already-ingested videos; `full` reprocesses all |
| `--output PATH` | `output/latest_run.json` | JSON output path |
| `--transcript-delay N` | `1.5` | Seconds between transcript requests (increase if you hit 429s) |
| `--agentscope` | off | Use AgentScope ReActAgent for Agents 1–2 (requires `ANTHROPIC_API_KEY`) |
| `--model MODEL_ID` | `claude-sonnet-4-6` | Anthropic model for `--agentscope` mode |

---

## Output files

| File | Contents |
|---|---|
| `output/latest_run.json` | Full structured run — all agent outputs, metrics, every video |
| `output/strategic_brief.md` | McKinsey SCR brief with situation, complication, recommendations |
| `output/memory.md` | Persistent belief store — confidence-weighted observations across runs |

---

## Topic taxonomy

Topics are defined in `config/topics.yaml` — **no code change needed to add new tools**:

```yaml
technical_tools:
  NewTool:
    - '\bnew tool\b'
    - '\bnewt\b'
```

The taxonomy covers 77 topics across four categories: `technical_tools`, `architectures`, `use_cases`, and `business_models`. Agent 2 also runs an **emergent topic detector** that automatically surfaces CamelCase/ALL-CAPS tool names from video text that are not in the taxonomy yet — these appear in the strategic brief as *"Newly detected tools"*.

---

## Ingestion modes

| Mode | Command | Requirements |
|---|---|---|
| Sample data | `python run.py --full` | None |
| Live YouTube | `python run.py` | `YOUTUBE_API_KEY` |
| Live + DB deduplication | `python run.py` + `DATABASE_URL` set | `YOUTUBE_API_KEY`, PostgreSQL |
| AgentScope LLM | `python run.py --agentscope` | `ANTHROPIC_API_KEY` |

**Transcript fetching:** The pipeline uses `youtube-transcript-api` to fetch auto-generated captions. A configurable delay (`--transcript-delay`, default 1.5 s) paces requests to stay under YouTube's rate limit. Videos where transcripts are unavailable are still processed using title, description, and comments.

**Deduplication:** On live runs the pipeline loads all previously ingested `video_id`s from PostgreSQL and skips them. Use `--force-reprocess` to bypass this.

---

## Database setup (optional)

```bash
# Start PostgreSQL and run migrations in order
psql $DATABASE_URL -f migrations/001_init.sql
psql $DATABASE_URL -f migrations/002_topic_tf.sql
psql $DATABASE_URL -f migrations/003_phase2.sql
psql $DATABASE_URL -f migrations/004_phase3.sql
```

---

## Project layout

```
config/
  channels.yaml        channel list and video limit
  topics.yaml          YAML taxonomy (edit here to add new tools — no code change needed)
data/
  sample_channels.json bundled sample data for --full mode
docs/
  technical_reference.md  full agent-by-agent technical reference
migrations/            PostgreSQL schema (apply in numeric order)
output/                generated on first run (gitignored)
src/acis/
  agents/              one file per agent
  ingestion/           YouTube API client + sample client
  models.py            all dataclasses (state objects)
  pipeline.py          FullPipeline — wires agents 1–6
  runner.py            app builder functions
  tools.py             shared utilities (topic extraction, salience, hype)
  memory.py            Bayesian belief store
  config.py            YAML config loader
  db.py                SQLAlchemy repository
run.py                 CLI entry point
```

---

## Technical reference

For full documentation on every agent, metric formula, and data model see [docs/technical_reference.md](docs/technical_reference.md).
