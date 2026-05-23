from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on env vars being set externally

from acis.runner import (
    build_agentscope_app,
    build_full_sample_app,
    build_live_app,
    write_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ACIS pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run.py --full                     # All 6 agents, sample data\n"
            "  python run.py --full --memory output/memory.md   # with belief persistence\n"
            "  python run.py --agentscope               # LLM agents (requires ANTHROPIC_API_KEY)\n"
            "  python run.py                            # Live mode (requires YOUTUBE_API_KEY)\n"
        ),
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "Run all 6 agents (phases 1-3): hook analysis, performance correlation, "
            "gap detection, and strategic brief generation. Uses sample data; "
            "no external dependencies required."
        ),
    )
    parser.add_argument(
        "--memory",
        default="output/memory.md",
        metavar="PATH",
        help=(
            "Path to MEMORY.md belief store for --full mode (default: output/memory.md). "
            "Created on first run; updated with Bayesian belief deltas on each run."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of videos per channel (overrides config).",
    )
    parser.add_argument(
        "--output",
        default="output/latest_run.json",
        help="Path to the JSON run summary output file.",
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Ignore deduplication and reprocess all videos, even those already in DB.",
    )
    parser.add_argument(
        "--mode",
        choices=["delta", "full"],
        default="delta",
        help="delta (default): skip already-ingested videos. full: reprocess everything.",
    )
    parser.add_argument(
        "--channel",
        default=None,
        metavar="HANDLE",
        help="Run for a single channel only, e.g. @liamottley.",
    )
    parser.add_argument(
        "--agentscope",
        action="store_true",
        help=(
            "Use AgentScope ReActAgent for Agents 1 and 2 instead of the deterministic pipeline. "
            "Requires ANTHROPIC_API_KEY and: pip install 'acis[agents]'."
        ),
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        metavar="MODEL_ID",
        help="Anthropic model ID to use in --agentscope mode (default: claude-sonnet-4-6).",
    )
    parser.add_argument(
        "--transcript-delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help=(
            "Seconds to wait between transcript requests (default: 1.5). "
            "Increase if you get 429 rate-limit errors. Overrides YTAPI_TRANSCRIPT_DELAY env var."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    force_reprocess = args.force_reprocess or args.mode == "full"

    memory_path = Path(args.memory).resolve() if args.memory else None
    _delay_env = os.environ.get("YTAPI_TRANSCRIPT_DELAY")
    transcript_delay = (
        args.transcript_delay
        if args.transcript_delay is not None
        else float(_delay_env) if _delay_env else 1.5
    )

    if args.full:
        app = build_full_sample_app(
            project_root,
            channel_filter=args.channel,
            memory_path=memory_path,
        )
    elif args.agentscope:
        db_url = os.environ.get("DATABASE_URL")
        app = build_agentscope_app(
            project_root,
            model_name=args.model,
            db_url=db_url,
            force_reprocess=force_reprocess,
            channel_filter=args.channel,
            memory_path=memory_path,
            transcript_delay=transcript_delay,
        )
    else:
        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            raise SystemExit(
                "YOUTUBE_API_KEY environment variable is required for live mode.\n"
                "Use --full to run all 6 agents against bundled sample data.\n"
                "Use --agentscope to run with AgentScope ReActAgents (requires ANTHROPIC_API_KEY)."
            )
        db_url = os.environ.get("DATABASE_URL")
        app = build_live_app(
            project_root,
            api_key=api_key,
            db_url=db_url,
            force_reprocess=force_reprocess,
            channel_filter=args.channel,
            memory_path=memory_path,
            transcript_delay=transcript_delay,
        )

    summary = app.run(limit_override=args.limit)
    output_path = project_root / args.output
    write_summary(summary, output_path)

    print(
        f"ACIS run complete — {summary.videos_processed} processed, "
        f"{summary.videos_skipped} skipped, "
        f"{summary.channels_processed} channels."
    )
    print(f"Output: {output_path}")

    if summary.strategic_brief is not None:
        brief_path = output_path.parent / "strategic_brief.md"
        brief_path.write_text(summary.strategic_brief.to_markdown(), encoding="utf-8")
        print(f"Strategic brief: {brief_path}")
        if summary.opportunity_vector:
            print(
                f"White-space opportunities detected: "
                f"{len(summary.opportunity_vector.opportunities)}"
            )


if __name__ == "__main__":
    main()
