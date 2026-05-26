"""
Deterministic macro event tagger.

Classifies a free-text event description (and optional supporting headlines)
into a macro category, maps that category to sector-level impacts, and
exposes every rule that fired so the result is fully auditable.

Public API
----------
tag(description, headlines=[]) -> MacroTag

Design decisions recorded in docs/MACRO_MODULE.md.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from src.logging.logger import log_input, log_result, log_warning
from src.macro.rules import (
    CATEGORY_KEYWORDS,
    CATEGORY_LABELS,
    LOW_CONFIDENCE_THRESHOLD,
    MIN_MATCHES_TO_CLASSIFY,
    SECTOR_IMPACTS,
    STRENGTH_MODIFIERS,
)

_MODULE = "macro.tagger"

_UNKNOWN = "unknown"


# ── Output types ───────────────────────────────────────────────────────────────

@dataclass
class SectorTag:
    sector: str
    direction: str          # "bullish" | "bearish" | "mixed"
    strength: float         # 0.0–1.0; higher = stronger expected impact
    reasoning: str          # causal explanation from the rule table


@dataclass
class MacroTag:
    description: str                      # original input text
    category: str                         # primary category key
    category_label: str                   # human-readable label
    secondary_category: Optional[str]     # second-highest match if ≥ 1 keyword matched
    secondary_label: Optional[str]
    affected_sectors: list[SectorTag]     # merged across primary + secondary; strength-sorted
    confidence: float                     # 0.0–1.0
    low_confidence: bool                  # True when confidence < LOW_CONFIDENCE_THRESHOLD
    triggered_rules: list[str]            # keywords that fired for primary category
    competing_categories: list[str]       # other categories with ≥ 1 match (excl. secondary)
    category_scores: dict[str, int]       # keyword match count per category (full audit trail)
    strength_modifier: float              # global multiplier applied to all sector strengths
    notes: list[str]                      # [category_note, confidence_note, sector_note]


# ── Public entry point ─────────────────────────────────────────────────────────

def tag(
    description: str,
    headlines: list[str] | None = None,
) -> MacroTag:
    """
    Tag a macro event description with a category, sector impacts, and confidence.

    Parameters
    ----------
    description : str
        Short event description. E.g. "Fed begins aggressive rate hike cycle".
    headlines : list[str], optional
        Supporting news headlines. Used only to boost category confidence —
        they do not override the description-derived primary category.

    Returns
    -------
    MacroTag with full breakdown of rules fired, sector impacts, and confidence.
    """
    headlines = headlines or []
    log_input(_MODULE, {
        "description": description,
        "headline_count": len(headlines),
    })

    desc_tokens = _tokenize(description)
    hl_tokens_all = [_tokenize(h) for h in headlines]

    # Score every category against description tokens
    desc_scores: dict[str, tuple[int, list[str]]] = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        count, matched = _count_keyword_matches(desc_tokens, keywords)
        desc_scores[cat] = (count, matched)

    # Rank categories by match count
    ranked = sorted(desc_scores.items(), key=lambda kv: kv[1][0], reverse=True)
    category_scores = {cat: data[0] for cat, data in ranked}

    primary_cat, (primary_count, primary_matched) = ranked[0]

    # Require at least one keyword match to classify
    if primary_count < MIN_MATCHES_TO_CLASSIFY:
        result = _unknown_result(description, category_scores)
        log_warning(_MODULE, "no_category_match", {"description": description})
        return result

    # Secondary category: second-ranked with at least 1 match (different from primary)
    secondary_cat: Optional[str] = None
    secondary_matched: list[str] = []
    for cat, (count, matched) in ranked[1:]:
        if count >= MIN_MATCHES_TO_CLASSIFY:
            secondary_cat = cat
            secondary_matched = matched
            break

    # All other categories with ≥1 match (excluding primary and secondary)
    competing = [
        cat for cat, (count, _) in ranked
        if count >= MIN_MATCHES_TO_CLASSIFY
        and cat not in (primary_cat, secondary_cat)
    ]

    # Headline corroboration: fraction of headlines containing ≥1 primary keyword
    hl_corroboration = _headline_corroboration(
        hl_tokens_all, CATEGORY_KEYWORDS[primary_cat]
    )

    confidence = _compute_confidence(
        primary_count=primary_count,
        secondary_count=desc_scores[secondary_cat][0] if secondary_cat else 0,
        competing_count=len(competing),
        hl_corroboration=hl_corroboration,
        has_headlines=len(headlines) > 0,
    )

    # Strength modifier from description text
    strength_mod = _strength_modifier(desc_tokens)

    # Build merged sector list
    sectors = _build_sectors(primary_cat, secondary_cat, strength_mod)

    low_conf = confidence < LOW_CONFIDENCE_THRESHOLD

    # Compose notes
    primary_count_str = f"{primary_count} keyword(s) matched"
    hl_str = (
        f", {hl_corroboration:.0%} of {len(headlines)} headline(s) corroborate"
        if headlines else ""
    )
    secondary_str = (
        f" | secondary: {CATEGORY_LABELS.get(secondary_cat, secondary_cat)} "
        f"({desc_scores[secondary_cat][0]} match(es))"
        if secondary_cat else ""
    )
    category_note = (
        f"Category: {CATEGORY_LABELS[primary_cat]} — {primary_count_str}"
        f"{secondary_str}"
    )
    confidence_note = (
        f"Confidence: {confidence:.2f}"
        + (" [low — treat with caution]" if low_conf else "")
        + (f" | {len(competing)} competing category(ies)" if competing else "")
        + hl_str
    )
    sector_note = (
        f"{len(sectors)} sector(s) affected"
        + (f" | strength modifier {strength_mod:.2f}×" if strength_mod != 1.0 else "")
        + " | strengths are empirically uncalibrated"
    )

    result = MacroTag(
        description=description,
        category=primary_cat,
        category_label=CATEGORY_LABELS[primary_cat],
        secondary_category=secondary_cat,
        secondary_label=CATEGORY_LABELS.get(secondary_cat) if secondary_cat else None,
        affected_sectors=sectors,
        confidence=round(confidence, 4),
        low_confidence=low_conf,
        triggered_rules=primary_matched,
        competing_categories=competing,
        category_scores=category_scores,
        strength_modifier=round(strength_mod, 4),
        notes=[category_note, confidence_note, sector_note],
    )

    log_result(_MODULE, {
        "description": description,
        "category": primary_cat,
        "secondary_category": secondary_cat,
        "confidence": result.confidence,
        "low_confidence": low_conf,
        "sector_count": len(sectors),
        "triggered_rules": primary_matched,
        "competing_count": len(competing),
        "strength_modifier": result.strength_modifier,
    })

    return result


# ── Internal helpers ───────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, return list of word tokens."""
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def _token_text(tokens: list[str]) -> str:
    """Join tokens into a single space-separated string for substring matching."""
    return " ".join(tokens)


def _count_keyword_matches(
    tokens: list[str],
    keywords: list[str],
) -> tuple[int, list[str]]:
    """
    Count how many keywords from the list appear in the token string.
    Substring matching allows multi-word phrases.
    Returns (count, list_of_matched_keywords).
    """
    text = _token_text(tokens)
    matched = [kw for kw in keywords if kw in text]
    return len(matched), matched


def _headline_corroboration(
    hl_token_lists: list[list[str]],
    keywords: list[str],
) -> float:
    """
    Fraction of headlines that contain at least one keyword from the category.
    Returns 0.0 if no headlines provided.
    """
    if not hl_token_lists:
        return 0.0
    supporting = sum(
        1 for tokens in hl_token_lists
        if _count_keyword_matches(tokens, keywords)[0] >= 1
    )
    return supporting / len(hl_token_lists)


def _compute_confidence(
    primary_count: int,
    secondary_count: int,
    competing_count: int,
    hl_corroboration: float,
    has_headlines: bool,
) -> float:
    """
    Confidence = keyword score × specificity penalty × headline bonus.

    keyword_score   : min(1.0, primary_count / 3) — 3+ matches → saturates at 1.0
    specificity     : penalise when a strong secondary category also matched
    competing_pen   : −0.08 per additional competing category (beyond secondary)
    headline_bonus  : up to +0.20 from corroborating headlines

    Known limitation: this is a proxy metric, not a calibrated probability.
    High confidence means high keyword coverage and low ambiguity — not that
    the category assignment is objectively correct.
    """
    keyword_score = min(1.0, primary_count / 3.0)

    # Specificity: if secondary scored nearly as well, primary is less certain
    specificity = 1.0
    if secondary_count > 0:
        ratio = secondary_count / primary_count  # 0 to 1
        specificity = max(0.50, 1.0 - ratio * 0.40)

    # Penalty for each additional competing category (beyond secondary)
    competing_penalty = min(0.30, competing_count * 0.08)

    # Headline bonus — only applies when headlines are provided
    headline_bonus = hl_corroboration * 0.20 if has_headlines else 0.0

    raw = keyword_score * specificity - competing_penalty + headline_bonus
    return round(max(0.0, min(1.0, raw)), 4)


def _strength_modifier(tokens: list[str]) -> float:
    """
    Return a global strength multiplier from intensity words in the description.
    Searches for modifier words in token list; applies the strongest one found.
    Returns 1.0 if no modifier words present.
    """
    text = _token_text(tokens)
    best = 1.0
    for word, multiplier in STRENGTH_MODIFIERS.items():
        if word in text:
            # Use the furthest-from-1.0 modifier (most extreme wins)
            if abs(multiplier - 1.0) > abs(best - 1.0):
                best = multiplier
    return best


def _merge_direction(dir_a: str, dir_b: str) -> str:
    """
    Merge two direction signals for the same sector from different categories.
    Same direction → keep it. Conflicting → "mixed".
    """
    if dir_a == dir_b:
        return dir_a
    return "mixed"


def _build_sectors(
    primary_cat: str,
    secondary_cat: Optional[str],
    strength_mod: float,
) -> list[SectorTag]:
    """
    Build the merged list of SectorTags from primary (and optionally secondary)
    category impact tables. When both categories affect the same sector:
      - Same direction → take max strength, keep direction.
      - Opposite directions → direction = "mixed", strength = abs difference.
    All strengths are clamped to [0.0, 1.0] and multiplied by strength_mod.
    Sorted descending by strength.
    """
    primary_impacts = SECTOR_IMPACTS.get(primary_cat, {})
    secondary_impacts = SECTOR_IMPACTS.get(secondary_cat, {}) if secondary_cat else {}

    merged: dict[str, tuple[str, float, str]] = {}  # sector → (direction, strength, reasoning)

    for sector, rule in primary_impacts.items():
        merged[sector] = (rule.direction, rule.strength, rule.reasoning)

    for sector, rule in secondary_impacts.items():
        if sector not in merged:
            merged[sector] = (rule.direction, rule.strength, f"[secondary] {rule.reasoning}")
        else:
            existing_dir, existing_str, existing_reason = merged[sector]
            new_dir = _merge_direction(existing_dir, rule.direction)
            if new_dir == "mixed":
                new_str = abs(existing_str - rule.strength)
                new_reason = (
                    f"{existing_reason} | conflicting signal from secondary: "
                    f"{rule.reasoning}"
                )
            else:
                new_str = max(existing_str, rule.strength)
                new_reason = (
                    f"{existing_reason} | reinforced by secondary: {rule.reasoning}"
                )
            merged[sector] = (new_dir, new_str, new_reason)

    result = []
    for sector, (direction, strength, reasoning) in merged.items():
        final_strength = round(min(1.0, strength * strength_mod), 4)
        result.append(SectorTag(
            sector=sector,
            direction=direction,
            strength=final_strength,
            reasoning=reasoning,
        ))

    result.sort(key=lambda s: s.strength, reverse=True)
    return result


def _unknown_result(description: str, category_scores: dict[str, int]) -> MacroTag:
    return MacroTag(
        description=description,
        category=_UNKNOWN,
        category_label=CATEGORY_LABELS[_UNKNOWN],
        secondary_category=None,
        secondary_label=None,
        affected_sectors=[],
        confidence=0.0,
        low_confidence=True,
        triggered_rules=[],
        competing_categories=[],
        category_scores=category_scores,
        strength_modifier=1.0,
        notes=[
            "Category: Unknown — no keywords matched any category",
            "Confidence: 0.0 — no classification possible",
            "0 sectors affected — extend CATEGORY_KEYWORDS to handle this event type",
        ],
    )
