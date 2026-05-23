# ACIS — Autonomous Creator Intelligence Brief

Runs the full ACIS 6-agent competitive intelligence pipeline against configured YouTube channels
and returns a McKinsey-structured strategic brief with content gap opportunities.

## Usage

- "Run ACIS" — full run, all channels, default video limit
- "Run ACIS delta" — incremental run, new videos only (skips already-ingested)
- "Run ACIS for @liamottley" — single channel run
- "Run ACIS full" — all 6 agents against sample data (no YouTube API key needed)
- "Show ACIS beliefs" — display the current strategic belief graph from MEMORY.md
- "What did ACIS find about Claude Code?" — FTS5 search against past run outputs

## Schedule

Every Sunday at 08:00. Deliver to Telegram.

## Outputs

- Strategic brief (Markdown) with situation, complication, resolution, recommendations
- Belief graph deltas written to MEMORY.md via Hermes API
- Full structured JSON at output/latest_run.json

## Configuration

All channels and video limits are set in config/channels.yaml.
Topic taxonomy is in config/topics.yaml — add new tools without touching code.
API keys are read from environment or Hermes config (YOUTUBE_API_KEY, ANTHROPIC_API_KEY).
