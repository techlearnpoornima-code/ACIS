# ACIS Phase 1 Flow Diagram

This document explains how the current Phase 1 system executes using one concrete example from [output/latest_run.json](/Users/poornimabyregowda/playground/ACIS/output/latest_run.json).

Example video used below:
- `video_id`: `liam-001`
- `channel`: `@liamottley`
- `title`: `I built an AI agency system that closes clients on autopilot`

## 1. End-to-End Flow

```text
run.py --sample-data
    |
    v
build_sample_app()
    |
    v
load_config(config/channels.yaml)
    |
    v
IngestionService.collect()
    |
    v
SampleIngestionClient.fetch_latest_videos(channel, limit)
    |
    v
IngestionPayload
  - metadata
  - transcript_segments
  - comments
    |
    v
SequentialPipeline.run(payload)
    |
    +--> Agent 1: ChannelResearchAgent.run(payload)
    |       - normalise metadata
    |       - segment transcript into hook/body/outro
    |       - detect language
    |       - compute transcript completeness
    |       - compute word count and words/minute
    |       -> ChannelResearchNode
    |
    +--> Agent 2: TopicExtractorAgent.run(node)
            - extract topics by regex patterns
            - extract monetisation signals
            - compute tf_scores
            - compute salience_scores
            - build topic_pairs
            -> SemanticGraphUpdate
    |
    v
RunSummary
    |
    v
output/latest_run.json
```

## 2. Example Execution for `liam-001`

### Step 1: Ingestion

`SampleIngestionClient` loads the video from [data/sample_channels.json](/Users/poornimabyregowda/playground/ACIS/data/sample_channels.json).

The payload contains:
- title and metadata
- 7 transcript segments
- transcript source = `api`

### Step 2: Agent 1 output

Agent 1 produces this `ChannelResearchNode` shape:

```text
video_id: liam-001
language: en
transcript_completeness: 1.0
word_count: 122
words_per_minute: 9
```

Segment windows in the current implementation:
- `hook.duration_seconds = 154`
- `body.duration_seconds = 530`
- `outro.duration_seconds = 156`

Important implementation detail:
- The segmentation code assigns a transcript segment based on the segment `start` time, not by splitting it at exact boundaries.
- Because of that, the first 154 seconds of transcript ended up in `hook`, even though the intended conceptual hook window is `0-60s`.

### Step 3: Agent 2 topic extraction

Agent 2 scans the combined title, description, and transcript windows using regex patterns from [src/acis/tools.py](/Users/poornimabyregowda/playground/ACIS/src/acis/tools.py:16).

For `liam-001`, the extracted topics in `output/latest_run.json` are:

```text
technical_tools:
Claude, Claude Code, n8n, Airtable, MCP, CRM, RAG

architectures:
multi-agent, routing

use_cases:
lead generation

business_models:
agency, course, retainer
```

Monetisation signals:

```text
course -> course_plug
retainer -> service_offer
```

## 3. How TF Is Calculated

TF is computed in [`compute_tf()`](/Users/poornimabyregowda/playground/ACIS/src/acis/tools.py:215).

Formula:

```text
tf(topic) = raw_count_of_topic_tokens / total_filtered_tokens
```

### 3.1 Token base used by the code

The code builds one token stream from:
- title
- hook text
- body text
- outro text

It lowercases the text, tokenizes with:

```text
\b[a-z0-9-]+\b
```

Then it removes only the stopwords listed in `STOPWORDS`.

For `liam-001`, the current code produced:
- total filtered tokens = `90`

Some token counts:
- `claude = 2`
- `code = 1`
- `n8n = 1`
- `lead = 1`
- `generation = 1`
- `multi = 1`
- `agent = 1`
- `agency = 2`
- `course = 2`
- `retainer = 1`
- `routing = 1`

### 3.2 Example TF calculations

#### `Claude`

Topic tokens:

```text
["claude"]
```

Raw count:

```text
counts["claude"] = 2
```

TF:

```text
2 / 90 = 0.022222
```

Matches output:
- `tf_scores["Claude"] = 0.022222`

#### `Claude Code`

Topic tokens:

```text
["claude", "code"]
```

Raw count:

```text
counts["claude"] + counts["code"] = 2 + 1 = 3
```

TF:

```text
3 / 90 = 0.033333
```

Matches output:
- `tf_scores["Claude Code"] = 0.033333`

#### `lead generation`

Topic tokens:

```text
["lead", "generation"]
```

Raw count:

```text
1 + 1 = 2
```

TF:

```text
2 / 90 = 0.022222
```

Matches output:
- `tf_scores["lead generation"] = 0.022222`

#### `retainer`

Topic tokens:

```text
["retainer"]
```

Raw count:

```text
1
```

TF:

```text
1 / 90 = 0.011111
```

Matches output:
- `tf_scores["retainer"] = 0.011111`

## 4. How Salience Is Calculated

Salience is computed in [`compute_salience()`](/Users/poornimabyregowda/playground/ACIS/src/acis/tools.py:229).

Current formula:

```text
raw_count = sum(counts[token] for token in topic_tokens)
tf = raw_count / total_tokens
coverage = (# topic tokens that appear at least once) / (# topic tokens)
log_tf = log(1 + tf * 100) / log(101)
salience = round(log_tf * coverage, 4)
```

This is not corpus-level TF-IDF yet.
- It is a single-video approximation.
- `tf_scores` are stored separately for future cross-video IDF work.

### 4.1 Example salience calculations

#### `Claude`

Inputs:

```text
raw_count = 2
tf = 2 / 90 = 0.022222
coverage = 1 / 1 = 1.0
log_tf = log(1 + 0.022222 * 100) / log(101)
       = log(3.2222) / log(101)
       = 0.25353
salience = round(0.25353 * 1.0, 4) = 0.2535
```

Matches output:
- `salience_scores["Claude"] = 0.2535`

#### `Claude Code`

Inputs:

```text
raw_count = 3
tf = 3 / 90 = 0.033333
coverage = 2 / 2 = 1.0
log_tf = log(1 + 0.033333 * 100) / log(101)
       = log(4.3333) / log(101)
       = 0.317725
salience = round(0.317725 * 1.0, 4) = 0.3177
```

Matches output:
- `salience_scores["Claude Code"] = 0.3177`

#### `multi-agent`

Inputs:

```text
topic_tokens = ["multi", "agent"]
raw_count = 1 + 1 = 2
tf = 2 / 90 = 0.022222
coverage = 2 / 2 = 1.0
log_tf = 0.25353
salience = 0.2535
```

Matches output:
- `salience_scores["multi-agent"] = 0.2535`

#### `retainer`

Inputs:

```text
raw_count = 1
tf = 1 / 90 = 0.011111
coverage = 1.0
log_tf = log(1 + 1.1111) / log(101)
       = 0.161906
salience = 0.1619
```

Matches output:
- `salience_scores["retainer"] = 0.1619`

## 5. How Topic Pairs Are Built

Topic pairs are built in [`build_topic_pairs()`](/Users/poornimabyregowda/playground/ACIS/src/acis/tools.py:246).

Logic:
- merge all extracted topics across all categories
- de-duplicate them with `set(...)`
- sort them
- generate all 2-item combinations

So if the extracted topics are:

```text
[Claude, Claude Code, n8n, Airtable, MCP, CRM, RAG, multi-agent, routing, lead generation, agency, course, retainer]
```

The system creates every unique pair, for example:
- `(Claude, Claude Code)`
- `(Claude, n8n)`
- `(agency, course)`
- `(lead generation, routing)`

These pairs are meant to feed the future co-occurrence graph.

## 6. What Gets Written to `latest_run.json`

For each video, the JSON output contains:
- `channel_research`
- `semantic_graph`
- `comments`

For `liam-001`, the values in the output match the current code path:
- topic extraction came from regex pattern matching
- `tf_scores` came from filtered token counts over the combined text
- `salience_scores` came from log-normalised TF with full-token coverage

## 7. Practical Reading of the Example

Using `liam-001`, the system is effectively saying:
- the video strongly centers on `Claude`, `Claude Code`, `agency`, and `lead generation`
- `Claude Code` is the most salient single detected topic because its token bundle appears 3 times in a 90-token filtered corpus
- `retainer`, `RAG`, `CRM`, `MCP`, and `routing` are present but less central because they only contribute one token hit each

## 8. Current Limitations of This Phase 1 Flow

- `salience_scores` are not true TF-IDF yet; they are per-video approximations.
- Segment boundaries are coarse because transcript chunks are bucketed by start time.
- Topic extraction is regex-driven, so missed synonyms or phrasing variations will not be captured.
- Agent 2 does not yet use channel-level corpus statistics even though the architecture doc eventually expects that.

This is still enough for the Phase 1 exit criterion: the pipeline ingests videos and emits structured `SemanticGraphUpdate` JSON per video.
