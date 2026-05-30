"""MCP server — exposes ACIS ingestion and analysis tools as MCP endpoints.

Run with:
    uv run python mcp_serve.py

Requires: pip install 'acis[live]'
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main() -> None:
    try:
        import agentscope  # noqa: F401
        from agentscope.tools import Toolkit  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit(
            "MCP server requires AgentScope: pip install 'acis[agents]'\n" + str(exc)
        ) from exc

    from acis.tools import (
        compute_salience,
        compute_tf,
        detect_emergent_topics,
        detect_language,
        extract_topics,
        segment_transcript,
        validate_transcript_completeness,
    )

    toolkit = Toolkit(name="acis", description="ACIS ingestion and analysis tools")

    toolkit.register_tool_function(segment_transcript)
    toolkit.register_tool_function(detect_language)
    toolkit.register_tool_function(validate_transcript_completeness)
    toolkit.register_tool_function(extract_topics)
    toolkit.register_tool_function(compute_salience)
    toolkit.register_tool_function(compute_tf)
    toolkit.register_tool_function(detect_emergent_topics)

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8766"))
    print(f"ACIS MCP server starting on {host}:{port}")
    toolkit.serve_mcp(host=host, port=port)


if __name__ == "__main__":
    main()
