from __future__ import annotations

import re
from dataclasses import dataclass

from acis.models import ChannelResearchNode, HookProfile, IncomeClaim, SemanticGraphUpdate

# ---------------------------------------------------------------------------
# Taxonomy keyword patterns
# ---------------------------------------------------------------------------

# Each entry maps a taxonomy label to a list of regexes tested against the
# combined hook text (title + first-60s transcript).  First taxonomy with ≥1
# match wins primary; second distinct match (if any) wins secondary.
_TAXONOMY_PATTERNS: dict[str, list[str]] = {
    "MONEY": [
        r"\$[\d,]+(?:\.\d+)?(?:k|K|m|M)?",
        r"\b\d[\d,]*(?:\.\d+)?\s*(?:k|K|m|M)?\s*(?:per\s+(?:month|year|week|day)|a\s+month|MRR|ARR)\b",
        r"\b(?:mak(?:ing|e|es)|made|earn(?:ing|s|ed)?|generat(?:ing|ed?)|bring(?:ing|s)?)\s+(?:\$|money|revenue|income)\b",
        r"\b(?:six|seven|eight)[-\s]figure\b",
        r"\b(?:revenue|income|profit)\s+(?:of|from|in)\b",
    ],
    "ANTI_CORPORATE": [
        r"\bnobody\s+(?:shows?|talks?\s+about|tells?\s+you|teaches?|mentions?)\b",
        r"\bthey\s+(?:don['']t\s+want|won['']t\s+tell|hide|are\s+hiding)\b",
        r"\bstop\s+(?:using|doing|buying|following|trusting)\b",
        r"\b(?:the\s+)?truth\s+(?:about|behind|is)\b",
        r"\bwhat\s+(?:most|the)?\s*(?:tutorials?|creators?|gurus?|experts?)\s+(?:miss|get\s+wrong|don['']t|never)\b",
        r"\bmost\s+(?:ai|agent|automation|youtube)\s+(?:tutorials?|videos?|courses?)\s+(?:fail|are\s+wrong|miss|suck)\b",
    ],
    "STATUS": [
        r"\bafter\s+\d+\s+(?:months?|years?|weeks?|videos?|clients?|projects?|builds?)\b",
        r"\bi['']?(?:ve\s+)?(?:spent|used|tested|tried|built|deployed|shipped)\b",
        r"\bmy\s+(?:client|agency|company|team|stack|workflow|system|process)\b",
        r"\b(?:we|i)\s+(?:use|used|built|ship(?:ped)?|run|ran|close[sd]?)\b",
        r"\bcase\s+study\b",
        r"\bhere['']?s?\s+(?:my|our|the\s+exact)\b",
        r"\b(?:my|our)\s+(?:honest|real|actual)\s+(?:take|review|experience|results?)\b",
    ],
    "CURIOSITY_GAP": [
        r"\bhere['']?s?\s+(?:why|what|how|the\s+thing|the\s+reason)\b",
        r"\bthe\s+(?:secret|reason|truth|trick|hack|thing)\b",
        r"\bwait\s+(?:until|till)\s+you(?:['']ve)?\s+(?:see|hear|try)\b",
        r"\byou\s+(?:won['']t\s+believe|need\s+to|have\s+to)\s+(?:see|hear|know|try)\b",
        r"\bstay\s+(?:till|until|for)\s+the\s+end\b",
        r"\b(?:what|something)\s+(?:most\s+people|nobody|almost\s+nobody)\b",
    ],
    "TRANSFORMATION": [
        r"\bfrom\s+.{1,40}\s+to\b",
        r"\bhow\s+(?:i|we)\s+(?:went|got|turned|transformed|changed)\b",
        r"\bchanged\s+(?:everything|my|our|the\s+way)\b",
        r"\bused\s+to\b.{0,40}\bbut\s+(?:now|today|not\s+anymore)\b",
        r"\btransform(?:ed|ing|ation|s)?\b",
        r"\bgame[-\s]changer?\b",
    ],
    "TECHNICAL_AUTHORITY": [
        r"\bbenchmark(?:ed|ing|s)?\b",
        r"\b(?:tested|testing|compar(?:ed?|ing|ison)|vs\.?|versus)\b",
        r"\b(?:real|actual|measured?|raw)\s+(?:data|numbers?|results?|metrics?)\b",
        r"\b(?:step[-\s]by[-\s]step|full\s+(?:build|breakdown|tutorial|walkthrough|deep[-\s]dive))\b",
        r"\b(?:live|on[-\s]screen|demo(?:nstration)?)\b",
        r"\bi\s+(?:measured|profiled|instrumented|logged|traced)\b",
    ],
    "URGENCY": [
        r"\bright\s+now\b",
        r"\bdon['']t\s+(?:wait|miss|skip|delay)\b",
        r"\bbefore\s+(?:it['']?s\s+too\s+late|they?|you)\b",
        r"\b(?:today|this\s+(?:week|month)|immediately|urgent(?:ly)?)\b",
        r"\b(?:limited\s+(?:time|spots?)|running\s+out|won['']t\s+last|expires?)\b",
        r"\bwhile\s+(?:you\s+still\s+can|it['']?s\s+still\s+free)\b",
    ],
}

# ---------------------------------------------------------------------------
# Emotional intensity signals
# ---------------------------------------------------------------------------

_INTENSITY_WORDS: frozenset[str] = frozenset({
    "amazing", "incredible", "insane", "massive", "huge", "explosive", "wild",
    "crazy", "mindblowing", "mind-blowing", "unbelievable", "shocking",
    "extraordinary", "revolutionary", "groundbreaking", "literally", "seriously",
    "completely", "absolutely", "10x", "100x", "2x", "3x", "5x",
})

# ---------------------------------------------------------------------------
# Certainty / hedge vocabulary
# ---------------------------------------------------------------------------

_CERTAINTY_MARKERS: frozenset[str] = frozenset({
    "will", "guaranteed", "always", "never", "must", "definitely",
    "certainly", "obviously", "absolutely", "proven",
})

_HEDGE_WORDS: frozenset[str] = frozenset({
    "could", "might", "may", "possibly", "perhaps", "maybe",
    "sometimes", "potentially", "likely", "seems", "appears",
})

# ---------------------------------------------------------------------------
# Income claim patterns — (regex, default_claim_type)
# ---------------------------------------------------------------------------

_INCOME_PATTERNS: list[tuple[str, str]] = [
    (r"\$[\d,]+(?:\.\d+)?(?:[kKmM])?", "self_verified"),
    (
        r"\b\d[\d,]*(?:\.\d+)?\s*(?:k|K|m|M)?\s*"
        r"(?:per\s+(?:month|year|week|day)|a\s+month|MRR|ARR)\b",
        "self_verified",
    ),
    (r"\b(?:six|seven|eight)[-\s]figure\b", "vague"),
    (r"\bhundreds?\s+of\s+(?:thousand|million)s?\b", "vague"),
]

_CLIENT_SIGNALS: list[str] = [r"\bmy\s+client", r"\bour\s+client", r"\bstudent", r"\buser"]
_HYPOTHETICAL_SIGNALS: list[str] = [r"\bif\s+you\b", r"\byou\s+could\b", r"\bimagine\b", r"\bpotential(?:ly)?\b"]

# Empirical validation markers reduce the hype score
_EMPIRICAL_MARKERS: list[str] = [
    r"\bbenchmark", r"\bA/B\s+test", r"\bactual\s+(?:number|metric|data|result)\b",
    r"\bscreenshot", r"\bproof\b", r"\bdemonstrat(?:e|ing|ed)\b",
    r"\bcode\b.{0,20}\blive\b", r"\blive\s+(?:build|demo|on\s+screen)\b",
]

# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _classify_taxonomies(text: str) -> tuple[str, str | None]:
    """Return (primary, secondary) taxonomy labels, scanning all categories in order."""
    lower = text.lower()
    matched: list[str] = []
    for taxonomy, patterns in _TAXONOMY_PATTERNS.items():
        if any(re.search(p, lower) for p in patterns):
            matched.append(taxonomy)
        if len(matched) >= 2:
            break
    primary = matched[0] if matched else "TECHNICAL_AUTHORITY"
    secondary = matched[1] if len(matched) >= 2 else None
    return primary, secondary


def _compute_emotional_intensity(text: str) -> int:
    """Return a 1–10 score derived from exclamations, intensity vocabulary, and ALL-CAPS words."""
    score = 0
    score += min(text.count("!") * 2, 4)
    tokens = set(re.findall(r"\b[\w-]+\b", text.lower()))
    score += min(len(tokens & _INTENSITY_WORDS) * 2, 4)
    caps_count = sum(1 for w in text.split() if w.isupper() and len(w) >= 2)
    score += min(caps_count, 2)
    return min(max(score + 1, 1), 10)


def _compute_certainty_ratio(text: str) -> float:
    """Return certainty / (certainty + hedges); 0.5 when neither group is present."""
    tokens = set(re.findall(r"\b\w+\b", text.lower()))
    certainty = len(tokens & _CERTAINTY_MARKERS)
    hedges = len(tokens & _HEDGE_WORDS)
    if certainty + hedges == 0:
        return 0.5
    return round(certainty / (certainty + hedges), 4)


def _extract_income_claims(text: str) -> list[IncomeClaim]:
    """Detect income / revenue claims and classify them by speaker attribution."""
    claims: list[IncomeClaim] = []
    seen_spans: list[tuple[int, int]] = []

    for pattern, default_type in _INCOME_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # Deduplicate overlapping matches
            if any(s <= match.start() < e for s, e in seen_spans):
                continue
            seen_spans.append((match.start(), match.end()))

            raw = match.group(0)
            ctx_start = max(0, match.start() - 120)
            ctx_end = min(len(text), match.end() + 120)
            ctx = text[ctx_start:ctx_end]
            ctx_lower = ctx.lower()

            if any(re.search(p, ctx_lower) for p in _CLIENT_SIGNALS):
                claim_type = "client_attributed"
            elif any(re.search(p, ctx_lower) for p in _HYPOTHETICAL_SIGNALS):
                claim_type = "hypothetical"
            elif "vague" in default_type or not re.search(r"\d", raw):
                claim_type = "vague"
            else:
                claim_type = "self_verified"

            figure: float | None = None
            num_match = re.search(r"[\d,]+(?:\.\d+)?", raw)
            if num_match:
                try:
                    figure = float(num_match.group(0).replace(",", ""))
                    if re.search(r"[kK]\b", raw):
                        figure *= 1_000
                    elif re.search(r"[mM]\b", raw):
                        figure *= 1_000_000
                except ValueError:
                    figure = None

            claims.append(IncomeClaim(
                exact_quote=raw,
                figure=figure,
                claim_type=claim_type,
                context=ctx.strip(),
            ))
    return claims


def _has_empirical_validation(text: str) -> bool:
    """Return True when the text contains at least one concrete empirical signal."""
    lower = text.lower()
    return any(re.search(p, lower) for p in _EMPIRICAL_MARKERS)


def _has_outcome_exaggeration(claims: list[IncomeClaim]) -> bool:
    """Return True when any claim is vague or suspiciously large and round."""
    for c in claims:
        if c.claim_type == "vague":
            return True
        if c.figure is not None and c.figure >= 10_000 and c.figure % 1_000 == 0:
            return True
    return False


def _compute_hype_score(
    income_claims: list[IncomeClaim],
    certainty_ratio: float,
    has_empirical: bool,
    has_exaggeration: bool,
) -> float:
    """Composite hype score per FR-5.1: H ∈ [0, 1]."""
    income_density = min(len(income_claims) / 3.0, 1.0)
    H = (
        0.30 * income_density
        + 0.25 * certainty_ratio
        + 0.30 * (1.0 - float(has_empirical))
        + 0.15 * float(has_exaggeration)
    )
    return round(min(H, 1.0), 4)


# ---------------------------------------------------------------------------
# Agent 3 public class
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class HookAnalyzerAgent:
    """Agent 3: deterministic hook taxonomy classifier and persuasion scorer."""

    agent_id: str = "agent_3_hook_analyzer"

    def run(self, node: ChannelResearchNode, graph: SemanticGraphUpdate) -> HookProfile:
        hook_text = node.segments["hook"].text
        combined = f"{node.title} {hook_text}"

        primary, secondary = _classify_taxonomies(combined)

        # Promote secondary to TECHNICAL_AUTHORITY when graph contains empirical architectures
        empirical_archs = {"evaluation", "observability"}
        if secondary is None and primary != "TECHNICAL_AUTHORITY":
            if any(a in empirical_archs for a in graph.architectures):
                secondary = "TECHNICAL_AUTHORITY"

        emotional_intensity = _compute_emotional_intensity(combined)
        certainty_ratio = _compute_certainty_ratio(combined)
        income_claims = _extract_income_claims(combined)
        has_empirical = _has_empirical_validation(combined)
        has_exaggeration = _has_outcome_exaggeration(income_claims)
        hype_score = _compute_hype_score(income_claims, certainty_ratio, has_empirical, has_exaggeration)

        return HookProfile(
            video_id=node.video_id,
            primary_taxonomy=primary,
            secondary_taxonomy=secondary,
            emotional_intensity=emotional_intensity,
            certainty_ratio=certainty_ratio,
            income_claims=income_claims,
            hype_score=hype_score,
        )
