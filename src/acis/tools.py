from __future__ import annotations

import math
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

from acis.models import ChannelResearchNode, IngestionPayload, TextWindow, TranscriptSegment

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "how",
    "if", "in", "into", "is", "it", "my", "nobody", "of", "on", "or", "so", "that",
    "the", "their", "this", "to", "we", "with", "you", "your",
}

# Hardcoded fallback — used only if config/topics.yaml is missing or unreadable.
_HARDCODED_TOPIC_PATTERNS: dict[str, dict[str, list[str]]] = {
    "technical_tools": {
        "Claude": [r"\bclaude\b"],
        "Claude Code": [r"\bclaude code\b"],
        "GPT-4": [r"\bgpt-?4o?\b", r"\bgpt4\b"],
        "Gemini": [r"\bgemini\b"],
        "Cursor": [r"\bcursor\b(?! key)"],
        "Windsurf": [r"\bwindsurf\b"],
        "GitHub Copilot": [r"\bcopilot\b", r"\bgithub copilot\b"],
        "n8n": [r"\bn8n\b"],
        "Zapier": [r"\bzapier\b"],
        "Make": [r"\bmake\.com\b", r"\bintegromat\b", r"\bmake automation\b"],
        "LangChain": [r"\blangchain\b"],
        "LangGraph": [r"\blanggraph\b"],
        "CrewAI": [r"\bcrewai\b"],
        "AutoGen": [r"\bautogen\b"],
        "Dify": [r"\bdify\b"],
        "Airtable": [r"\bairtable\b"],
        "Supabase": [r"\bsupabase\b"],
        "Pinecone": [r"\bpinecone\b"],
        "Weaviate": [r"\bweaviate\b"],
        "MCP": [r"\bmcp\b"],
        "Python": [r"\bpython\b"],
        "CRM": [r"\bcrm\b"],
        "RAG": [r"\brag\b"],
        "OpenAI": [r"\bopenai\b"],
        "Anthropic": [r"\banthropic\b"],
        "Perplexity": [r"\bperplexity\b"],
    },
    "architectures": {
        "multi-agent": [r"\bmulti agent\b", r"\bmulti-agent\b"],
        "agentic": [r"\bagentic\b"],
        "routing": [r"\brouting\b"],
        "orchestration": [r"\borchestration\b"],
        "observability": [r"\bobservability\b"],
        "evaluation": [r"\bevals?\b", r"\bevaluation\b", r"\bbenchmark\b"],
        "retrieval": [r"\bretrieval\b"],
        "fine-tuning": [r"\bfine-?tuning\b", r"\bfine tuned?\b"],
        "voice agents": [r"\bvoice agent\b", r"\bspeech agent\b"],
        "computer use": [r"\bcomputer use\b"],
        "prompt engineering": [r"\bprompt engineering\b", r"\bprompt design\b"],
    },
    "use_cases": {
        "lead generation": [r"\blead gen(?:eration)?\b"],
        "customer support": [r"\bcustomer support\b"],
        "sales automation": [r"\bsales automation\b"],
        "reliability audits": [r"\breliability audits?\b"],
        "reporting": [r"\breporting\b", r"\bdashboards?\b"],
        "outreach": [r"\boutreach\b", r"\bcold email\b"],
        "code generation": [r"\bcode gen(?:eration)?\b", r"\bvibe coding\b"],
        "content creation": [r"\bcontent creation\b", r"\bcontent workflow\b"],
        "data extraction": [r"\bdata extract(?:ion)?\b", r"\bscraping\b"],
    },
    "business_models": {
        "agency": [r"\bagency\b"],
        "course": [r"\bcourse\b", r"\bcohort\b", r"\bcommunity\b", r"\bworkshop\b"],
        "consulting": [r"\bconsulting\b"],
        "productised service": [r"\bproductised service\b", r"\bproductized service\b"],
        "retainer": [r"\bretainer\b"],
        "SaaS": [r"\bsaas\b"],
        "newsletter": [r"\bnewsletter\b"],
        "bootcamp": [r"\bbootcamp\b"],
    },
}


def _topics_yaml_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config" / "topics.yaml"


def _load_topic_patterns() -> dict[str, dict[str, list[str]]]:
    """Load taxonomy from config/topics.yaml; falls back to hardcoded dict if unavailable."""
    try:
        import yaml  # noqa: PLC0415 — optional dep, imported lazily
        path = _topics_yaml_path()
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        print(f"  ⚠ Could not load config/topics.yaml ({exc}); using hardcoded taxonomy")
    return _HARDCODED_TOPIC_PATTERNS


TOPIC_PATTERNS: dict[str, dict[str, list[str]]] = _load_topic_patterns()

# Flat set of all known topic names (lowercase) — used by emergent detector to avoid duplicates.
_KNOWN_TOPICS_FLAT: frozenset[str] = frozenset(
    topic.lower()
    for category_topics in TOPIC_PATTERNS.values()
    for topic in category_topics
)

# Common English words that look capitalised in title text but are not tool names.
_EMERGENT_EXCLUSIONS: frozenset[str] = frozenset({
    # Articles, conjunctions, prepositions (capitalised in titles)
    "The", "An", "A", "In", "On", "At", "By", "For", "Of", "To", "With", "From",
    # Question words
    "How", "What", "When", "Where", "Why", "Who",
    # Auxiliaries
    "Is", "Are", "Can", "Will", "Do", "Did", "Does", "Has", "Have", "Was", "Were",
    # Connectives
    "So", "But", "And", "If", "Then", "Now", "Also", "Even", "Just", "Only",
    "This", "That", "These", "Those", "Here", "There",
    # YouTube channel noise
    "Subscribe", "Like", "Comment", "Watch", "Video", "Channel", "Tutorial",
    "Course", "Playlist", "Shorts", "Live", "Click", "Link",
    # Generic adjectives
    "New", "Best", "Top", "Big", "Good", "Great", "Bad", "Simple", "Easy",
    "Hard", "Real", "Full", "Free", "Fast", "Quick", "Smart", "True", "False",
    "Better", "Worst", "Latest", "First", "Last", "Next", "Same", "Right",
    # Overly generic tech/biz nouns
    "App", "Bot", "Tool", "Data", "Code", "Tech", "Web", "Dev",
    "API", "SDK", "IDE", "CLI", "GUI", "URL", "URL", "ROI", "KPI", "SOC",
    "LLM", "NLP", "NLU", "TTS", "STT",
    "Time", "Day", "Week", "Month", "Year", "Way", "Part", "Step", "Thing",
    "Work", "Build", "Use", "Get", "Set", "Run", "Make", "See", "Take",
    "Business", "Company", "Team", "Client", "Project", "System", "Process",
    "Model", "Agent", "Platform", "Product", "Feature", "Update",
    "Hello", "Hey", "Thanks", "Please", "Actually", "Basically", "Literally",
    # Numbers / pronouns that pass heuristic checks
    "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Your", "Our", "My", "Its", "Their", "His", "Her", "You", "They",
    # Platforms / generic formats that are not trackable tools
    "YouTube", "Twitter", "LinkedIn", "Instagram", "Facebook", "Reddit", "Google",
    "PDF", "CSV", "JSON", "XML", "HTML", "CSS",
    # Business / analytical frameworks (not software tools)
    "SWOT", "OKR", "MVP", "GTM", "B2B", "B2C", "SOP",
    # Common title/video noise words
    "Ep", "Episode", "Series", "Mini", "Intro", "Outro",
    "Pro", "Plus", "Max", "Ultra", "Premium",
})


_YAML_HEADER = """\
# ACIS Topic Taxonomy
#
# Add new tools/frameworks/use-cases here — no code change required.
# Each entry: TopicName: [list of regex patterns matched against lowercase video text]
# Use single quotes around patterns so backslashes are preserved literally.
# Patterns are tested with re.search(), so partial matches work fine.
#
# (The 'emergent' section is auto-populated by detect_emergent_topics.)
"""


def _append_emergent_to_yaml(new_topics: list[str]) -> None:
    """Write newly detected tool names into config/topics.yaml under 'emergent', then reload globals."""
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        return

    path = _topics_yaml_path()
    if not path.exists():
        return

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return

        emergent_section: dict[str, list[str]] = data.setdefault("emergent", {})
        added: list[str] = []
        for topic in new_topics:
            if topic not in emergent_section:
                pattern = rf"\b{re.escape(topic.lower())}\b"
                emergent_section[topic] = [pattern]
                added.append(topic)

        if not added:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write(_YAML_HEADER)
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        global TOPIC_PATTERNS, _KNOWN_TOPICS_FLAT  # noqa: PLW0603
        TOPIC_PATTERNS = _load_topic_patterns()
        _KNOWN_TOPICS_FLAT = frozenset(
            t.lower()
            for category_topics in TOPIC_PATTERNS.values()
            for t in category_topics
        )
        print(f"  ✓ Emergent topics added to config/topics.yaml: {added}")
    except Exception as exc:
        print(f"  ⚠ Could not update config/topics.yaml with emergent topics ({exc})")


def _is_tool_like(word: str) -> bool:
    """Heuristic: return True for CamelCase, ALL-CAPS acronyms, or digit-suffixed names."""
    if len(word) < 2:
        return False
    if re.search(r"[a-z][A-Z]", word):
        return True  # CamelCase: e.g. LangSmith, CrewAI
    if re.match(r"^[A-Z]{2,6}$", word):
        return True  # ALL-CAPS: e.g. MCP, RAG, SDK
    if re.search(r"[A-Za-z]\d", word) and word[0].isupper():
        return True  # digit suffix: e.g. GPT4, Llama3
    return False


def detect_emergent_topics(node: ChannelResearchNode) -> list[str]:
    """Find capitalised terms in video text that look like tool names but aren't in the taxonomy."""
    title_caps: set[str] = set(re.findall(r"\b[A-Z][a-zA-Z0-9-]+\b", node.title))
    full_text = " ".join([
        node.title,
        node.segments["hook"].text,
        node.segments["body"].text,
        node.segments["outro"].text,
    ])
    all_caps = re.findall(r"\b[A-Z][a-zA-Z0-9-]+\b", full_text)
    counts: Counter = Counter(all_caps)
    emergent: list[str] = []
    for word, count in counts.most_common(30):
        if len(word) < 3:
            continue
        if word.lower() in _KNOWN_TOPICS_FLAT:
            continue
        if word in _EMERGENT_EXCLUSIONS:
            continue
        if _is_tool_like(word) or (word in title_caps and count >= 2):
            emergent.append(word)
        if len(emergent) >= 5:
            break

    if emergent:
        _append_emergent_to_yaml(emergent)

    return emergent


def normalise_metadata(payload: IngestionPayload) -> dict[str, object]:
    metadata = payload.metadata
    return {
        "video_id": metadata.video_id,
        "channel_id": metadata.channel_id,
        "channel_handle": metadata.channel_handle,
        "channel_display_name": metadata.channel_display_name,
        "title": metadata.title.strip(),
        "description": metadata.description.strip(),
        "upload_date": metadata.upload_date.isoformat(),
        "duration_seconds": metadata.duration_seconds,
        "view_count": metadata.view_count,
        "like_count": metadata.like_count,
        "comment_count": metadata.comment_count,
        "thumbnail_url": metadata.thumbnail_url,
    }


def segment_transcript(segments: list[TranscriptSegment], video_duration: int) -> dict[str, TextWindow]:
    """Split transcript into hook (0–60s), body (60–80%), and outro (80–100%) windows."""
    if video_duration <= 0:
        full_text = " ".join(s.text.strip() for s in segments)
        return {
            "hook": TextWindow(text=full_text, duration_seconds=0),
            "body": TextWindow(text="", duration_seconds=0),
            "outro": TextWindow(text="", duration_seconds=0),
        }
    boundaries = {
        "hook": min(60, video_duration),
        "body": int(video_duration * 0.8),
        "outro": video_duration,
    }
    buckets = {"hook": [], "body": [], "outro": []}
    durations = {"hook": 0, "body": 0, "outro": 0}

    for segment in segments:
        # Use start position so segments are assigned to the window they begin in
        if segment.start < boundaries["hook"]:
            bucket = "hook"
        elif segment.start < boundaries["body"]:
            bucket = "body"
        else:
            bucket = "outro"
        buckets[bucket].append(segment.text.strip())
        durations[bucket] += segment.duration

    return {
        name: TextWindow(text=" ".join(texts).strip(), duration_seconds=durations[name])
        for name, texts in buckets.items()
    }


def detect_language(text: str) -> str:
    """Detect language using langdetect when available; falls back to ASCII-ratio heuristic."""
    if not text.strip():
        return "unknown"
    try:
        from langdetect import DetectorFactory, LangDetectException, detect  # noqa: PLC0415
        DetectorFactory.seed = 0  # deterministic output
        try:
            return detect(text[:2000])
        except LangDetectException:
            pass
    except ImportError:
        pass
    ascii_ratio = sum(1 for char in text if ord(char) < 128) / max(len(text), 1)
    return "en" if ascii_ratio > 0.95 else "unknown"


def validate_transcript_completeness(segments: list[TranscriptSegment], duration: int) -> float:
    """Return the fraction of video duration covered by transcript segments (capped at 1.0)."""
    covered = sum(segment.duration for segment in segments)
    return round(min(covered / max(duration, 1), 1.0), 3)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def words_per_minute(words: int, duration_seconds: int) -> int:
    if duration_seconds <= 0:
        return 0
    return int(round(words / max(duration_seconds / 60, 1e-6)))


def extract_topics(node: ChannelResearchNode) -> dict[str, list[str]]:
    search_text = " ".join(
        [
            node.title,
            node.metadata["description"],
            node.segments["hook"].text,
            node.segments["body"].text,
            node.segments["outro"].text,
        ]
    ).lower()
    extracted: dict[str, list[str]] = {}
    for category, patterns in TOPIC_PATTERNS.items():
        hits: list[str] = []
        for label, regexes in patterns.items():
            if any(re.search(regex, search_text) for regex in regexes):
                hits.append(label)
        extracted[category] = hits
    return extracted


def extract_monetisation_signals(text: str) -> list[dict[str, object]]:
    signals = []
    for keyword, signal_type in [
        ("course", "course_plug"),
        ("cohort", "cohort_offer"),
        ("community", "community_offer"),
        ("consulting", "consulting_offer"),
        ("retainer", "service_offer"),
    ]:
        match = re.search(rf"\b{re.escape(keyword)}\b", text.lower())
        if match:
            signals.append({"type": signal_type, "product": keyword, "timestamp": None})
    return signals


def _video_token_counter(node: ChannelResearchNode) -> tuple[Counter, int]:
    """Build a stopword-filtered token Counter from the full video text."""
    text = " ".join([
        node.title,
        node.segments["hook"].text,
        node.segments["body"].text,
        node.segments["outro"].text,
    ]).lower()
    tokens = [t for t in re.findall(r"\b[a-z0-9-]+\b", text) if t not in STOPWORDS]
    counts: Counter = Counter(tokens)
    return counts, max(sum(counts.values()), 1)


def compute_tf(node: ChannelResearchNode, extracted_topics: dict[str, list[str]]) -> dict[str, float]:
    """Return raw per-video TF for each detected topic; persisted to topic_tf for cross-corpus IDF."""
    counts, total = _video_token_counter(node)
    tf: dict[str, float] = {}
    for topic in sum(extracted_topics.values(), []):
        topic_tokens = re.findall(r"[a-z0-9]+", topic.lower())
        if not topic_tokens:
            tf[topic] = 0.0
            continue
        raw_count = sum(counts[t] for t in topic_tokens)
        tf[topic] = round(raw_count / total, 6)
    return tf


def compute_salience(node: ChannelResearchNode, extracted_topics: dict[str, list[str]]) -> dict[str, float]:
    """Score each detected topic using log-normalised TF × coverage; single-video approximation until IDF matures."""
    counts, total = _video_token_counter(node)
    scores: dict[str, float] = {}
    for topic in sum(extracted_topics.values(), []):
        topic_tokens = re.findall(r"[a-z0-9]+", topic.lower())
        if not topic_tokens:
            scores[topic] = 0.0
            continue
        raw_count = sum(counts[t] for t in topic_tokens)
        tf = raw_count / total
        coverage = sum(1 for t in topic_tokens if counts[t] > 0) / len(topic_tokens)
        log_tf = math.log(1 + tf * 100) / math.log(101)  # 0–1 normalised range
        scores[topic] = round(log_tf * coverage, 4)
    return scores


def build_topic_pairs(extracted_topics: dict[str, list[str]]) -> list[tuple[str, str]]:
    """Generate all unique topic co-occurrence pairs across categories for graph edge creation."""
    all_topics = sorted(set(sum(extracted_topics.values(), [])))
    return list(combinations(all_topics, 2))
