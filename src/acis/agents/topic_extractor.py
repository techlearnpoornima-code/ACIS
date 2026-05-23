from __future__ import annotations

from dataclasses import dataclass

from acis.models import ChannelResearchNode, SemanticGraphUpdate
from acis.tools import (
    build_topic_pairs,
    compute_salience,
    compute_tf,
    detect_emergent_topics,
    extract_monetisation_signals,
    extract_topics,
)


@dataclass(slots=True)
class TopicExtractorAgent:
    """Agent 2: extracts technical topics, use-cases, and monetisation signals; scores salience."""

    agent_id: str = "agent_2_topic_extractor"

    def run(self, node: ChannelResearchNode) -> SemanticGraphUpdate:
        extracted_topics = extract_topics(node)
        combined_text = " ".join(
            [node.segments["hook"].text, node.segments["body"].text, node.segments["outro"].text]
        )
        return SemanticGraphUpdate(
            video_id=node.video_id,
            technical_tools=extracted_topics["technical_tools"],
            architectures=extracted_topics["architectures"],
            use_cases=extracted_topics["use_cases"],
            business_models=extracted_topics["business_models"],
            monetisation_refs=extract_monetisation_signals(combined_text),
            salience_scores=compute_salience(node, extracted_topics),
            tf_scores=compute_tf(node, extracted_topics),
            topic_pairs=build_topic_pairs(extracted_topics),
            emergent_topics=detect_emergent_topics(node),
        )
