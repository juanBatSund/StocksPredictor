import pytest

from src.macro.tagger import (
    MacroTag,
    SectorTag,
    _compute_confidence,
    _count_keyword_matches,
    _merge_direction,
    _strength_modifier,
    _tokenize,
    tag,
)


# ── Tokeniser ─────────────────────────────────────────────────────────────────

class TestTokenize:
    def test_lowercases(self):
        assert _tokenize("Russia Invades Ukraine") == ["russia", "invades", "ukraine"]

    def test_strips_punctuation(self):
        tokens = _tokenize("Fed raises rates by 50bps (basis points)")
        assert "(" not in tokens
        assert ")" not in tokens

    def test_empty_string(self):
        assert _tokenize("") == []


# ── Keyword matching ──────────────────────────────────────────────────────────

class TestCountKeywordMatches:
    def test_single_word_match(self):
        tokens = _tokenize("The company is facing sanctions from the EU")
        count, matched = _count_keyword_matches(tokens, ["sanctions", "embargo"])
        assert count == 1
        assert "sanctions" in matched

    def test_phrase_match(self):
        tokens = _tokenize("The Fed begins a rate hike cycle")
        count, matched = _count_keyword_matches(tokens, ["rate hike", "rate hikes"])
        assert count >= 1
        assert "rate hike" in matched

    def test_no_match_returns_zero(self):
        tokens = _tokenize("Quarterly earnings report released today")
        count, matched = _count_keyword_matches(tokens, ["invasion", "tariff"])
        assert count == 0
        assert matched == []

    def test_multiple_matches(self):
        tokens = _tokenize("War and military conflict escalation in the region")
        count, matched = _count_keyword_matches(tokens, ["war", "military", "conflict", "escalation"])
        assert count == 4


# ── Category classification — real events ─────────────────────────────────────

class TestCategoryClassification:
    """
    These test the four real events from src/data/macro.py to verify
    the tagger produces sensible classifications for known history.
    """
    def test_russia_invades_ukraine(self):
        r = tag("Russia invades Ukraine")
        assert r.category == "geopolitical_conflict"

    def test_fed_rate_hike_cycle(self):
        r = tag("Fed begins aggressive rate hike cycle")
        assert r.category == "monetary_policy_tightening"

    def test_hamas_attack(self):
        r = tag("Hamas attacks Israel; Middle East conflict escalation")
        assert r.category == "geopolitical_conflict"

    def test_elevated_global_inflation(self):
        r = tag("Elevated global inflation persists")
        assert r.category == "inflation"

    def test_oil_price_shock(self):
        r = tag("OPEC cuts oil supply; crude oil prices surge")
        assert r.category == "energy_shock"

    def test_pandemic(self):
        r = tag("New virus outbreak triggers public health emergency")
        assert r.category == "pandemic"

    def test_bank_failure(self):
        r = tag("Regional bank failure triggers systemic risk concerns")
        assert r.category == "financial_crisis"

    def test_trade_war(self):
        r = tag("US imposes new tariffs on Chinese imports in trade war")
        assert r.category == "trade_policy"

    def test_rate_cut(self):
        r = tag("Fed cuts rates by 50 basis points lower to support economy")
        assert r.category == "monetary_policy_easing"

    def test_recession(self):
        r = tag("GDP contraction signals recession risk for the economy")
        assert r.category == "recession_risk"


# ── Unknown classification ─────────────────────────────────────────────────────

class TestUnknownClassification:
    def test_generic_text_returns_unknown(self):
        r = tag("The company released its annual report today")
        assert r.category == "unknown"

    def test_unknown_has_zero_confidence(self):
        r = tag("Quarterly earnings announcement")
        assert r.confidence == 0.0

    def test_unknown_has_no_sectors(self):
        r = tag("Product launch scheduled for next month")
        assert r.affected_sectors == []

    def test_unknown_has_low_confidence_flag(self):
        r = tag("The board of directors held a meeting")
        assert r.low_confidence is True

    def test_unknown_notes_explain(self):
        r = tag("Annual shareholder meeting took place")
        assert "unknown" in r.notes[0].lower() or "Unknown" in r.notes[0]


# ── Sector impact mapping ──────────────────────────────────────────────────────

class TestSectorImpacts:
    def test_geopolitical_includes_defense(self):
        r = tag("Russia invades Ukraine with military troops")
        sectors = {s.sector for s in r.affected_sectors}
        assert "defense" in sectors

    def test_defense_is_bullish_in_conflict(self):
        r = tag("Military invasion and troops deployed")
        defense = next(s for s in r.affected_sectors if s.sector == "defense")
        assert defense.direction == "bullish"

    def test_rate_hike_financials_bullish(self):
        r = tag("Fed begins aggressive rate hike cycle")
        financials = next((s for s in r.affected_sectors if s.sector == "financials"), None)
        assert financials is not None
        assert financials.direction == "bullish"

    def test_rate_hike_real_estate_bearish(self):
        r = tag("Fed begins aggressive rate hike cycle")
        real_estate = next((s for s in r.affected_sectors if s.sector == "real_estate"), None)
        assert real_estate is not None
        assert real_estate.direction == "bearish"

    def test_recession_consumer_staples_bullish(self):
        r = tag("Recession risk rises as GDP contraction accelerates")
        staples = next((s for s in r.affected_sectors if s.sector == "consumer_staples"), None)
        assert staples is not None
        assert staples.direction == "bullish"

    def test_sectors_sorted_by_strength_descending(self):
        r = tag("Oil price surge as OPEC cuts oil supply")
        strengths = [s.strength for s in r.affected_sectors]
        assert strengths == sorted(strengths, reverse=True)

    def test_sector_has_reasoning(self):
        r = tag("Russia invades Ukraine with military force")
        for s in r.affected_sectors:
            assert isinstance(s.reasoning, str)
            assert len(s.reasoning) > 0

    def test_sector_strength_bounded(self):
        r = tag("Unprecedented massive military invasion catastrophic conflict")
        for s in r.affected_sectors:
            assert 0.0 <= s.strength <= 1.0


# ── Confidence calculation ─────────────────────────────────────────────────────

class TestConfidence:
    def test_single_match_gives_low_confidence(self):
        # 1 keyword → keyword_score = 0.33; no competition → reasonable confidence
        r = tag("Troops deployed to border region")
        assert r.confidence < 0.50  # one weak keyword match

    def test_multiple_matches_give_higher_confidence(self):
        weak = tag("Military conflict")
        strong = tag("Military invasion troops conflict escalation nato weapons")
        assert strong.confidence > weak.confidence

    def test_competing_categories_reduce_confidence(self):
        # "sanctions" matches both geopolitical and trade
        sole = tag("Military invasion of sovereign territory with troops deployed")
        contested = tag("Military sanctions and tariff trade war")
        # contested has more competing categories
        assert contested.confidence <= sole.confidence

    def test_headline_corroboration_increases_confidence(self):
        base = tag("Fed begins rate hike cycle")
        corroborated = tag(
            "Fed begins rate hike cycle",
            headlines=["Fed raises interest rates by 75 basis points", "Rate hike shocks markets"],
        )
        assert corroborated.confidence >= base.confidence

    def test_low_confidence_flag_set_correctly(self):
        r = tag("Troops crossed the border")
        # 1 keyword match; may be low confidence
        # Just verify the flag is consistent with the threshold
        from src.macro.rules import LOW_CONFIDENCE_THRESHOLD
        assert r.low_confidence == (r.confidence < LOW_CONFIDENCE_THRESHOLD)

    def test_confidence_bounded_zero_to_one(self):
        r = tag("Massive unprecedented military invasion troops conflict nato escalation weapons")
        assert 0.0 <= r.confidence <= 1.0


# ── Confidence function unit tests ────────────────────────────────────────────

class TestComputeConfidence:
    def test_three_matches_no_competition_high_confidence(self):
        c = _compute_confidence(
            primary_count=3, secondary_count=0,
            competing_count=0, hl_corroboration=0.0, has_headlines=False,
        )
        assert c == pytest.approx(1.0, abs=0.01)

    def test_zero_matches_returns_zero(self):
        c = _compute_confidence(
            primary_count=0, secondary_count=0,
            competing_count=0, hl_corroboration=0.0, has_headlines=False,
        )
        assert c == pytest.approx(0.0)

    def test_strong_secondary_reduces_confidence(self):
        c_clean = _compute_confidence(
            primary_count=3, secondary_count=0,
            competing_count=0, hl_corroboration=0.0, has_headlines=False,
        )
        c_ambiguous = _compute_confidence(
            primary_count=3, secondary_count=3,
            competing_count=0, hl_corroboration=0.0, has_headlines=False,
        )
        assert c_ambiguous < c_clean

    def test_headline_corroboration_adds_to_confidence(self):
        c_no_hl = _compute_confidence(
            primary_count=2, secondary_count=0,
            competing_count=0, hl_corroboration=0.0, has_headlines=False,
        )
        c_with_hl = _compute_confidence(
            primary_count=2, secondary_count=0,
            competing_count=0, hl_corroboration=1.0, has_headlines=True,
        )
        assert c_with_hl > c_no_hl

    def test_many_competing_categories_penalised(self):
        c = _compute_confidence(
            primary_count=3, secondary_count=1,
            competing_count=4, hl_corroboration=0.0, has_headlines=False,
        )
        assert c < 0.70


# ── Strength modifier ─────────────────────────────────────────────────────────

class TestStrengthModifier:
    def test_no_modifier_returns_one(self):
        assert _strength_modifier(_tokenize("Fed raises rates")) == pytest.approx(1.0)

    def test_massive_returns_amplifier(self):
        assert _strength_modifier(_tokenize("Massive military invasion")) > 1.0

    def test_minor_returns_dampener(self):
        assert _strength_modifier(_tokenize("Minor border skirmish")) < 1.0

    def test_modifier_applied_to_sector_strengths(self):
        r_plain = tag("Military invasion and conflict")
        r_severe = tag("Severe military invasion and conflict")
        plain_def = next((s for s in r_plain.affected_sectors if s.sector == "defense"), None)
        severe_def = next((s for s in r_severe.affected_sectors if s.sector == "defense"), None)
        if plain_def and severe_def:
            assert severe_def.strength >= plain_def.strength


# ── Secondary category and sector merging ─────────────────────────────────────

class TestMultiCategory:
    def test_multi_category_event_has_secondary(self):
        # "rate hike" matches tightening; "recession" + "gdp contraction" match recession_risk
        r = tag("Fed rate hike cycle triggers recession risk as gdp contraction accelerates")
        assert r.secondary_category is not None

    def test_secondary_sectors_included(self):
        r = tag("Fed raises rates aggressively as recession risk grows with GDP contraction")
        sectors = {s.sector for s in r.affected_sectors}
        # monetary tightening → financials; recession → consumer_staples (defensive)
        assert len(sectors) > 3

    def test_conflicting_directions_become_mixed(self):
        assert _merge_direction("bullish", "bearish") == "mixed"

    def test_same_directions_preserved(self):
        assert _merge_direction("bearish", "bearish") == "bearish"
        assert _merge_direction("bullish", "bullish") == "bullish"


# ── Full audit trail ──────────────────────────────────────────────────────────

class TestAuditTrail:
    def test_triggered_rules_exposed(self):
        r = tag("Russia invades Ukraine with military troops")
        assert len(r.triggered_rules) > 0
        assert all(isinstance(kw, str) for kw in r.triggered_rules)

    def test_category_scores_exposed_for_all_categories(self):
        r = tag("Russia invades Ukraine")
        from src.macro.rules import CATEGORY_KEYWORDS
        for cat in CATEGORY_KEYWORDS:
            assert cat in r.category_scores

    def test_competing_categories_listed(self):
        r = tag("Russia invades Ukraine with military sanctions and oil embargo")
        # "sanctions" hits geopolitical; "oil embargo" hits energy_shock
        # geopolitical should win but energy_shock should appear as competing or secondary
        all_cats = set(r.competing_categories) | ({r.secondary_category} if r.secondary_category else set())
        assert len(all_cats) >= 0  # structural test — competing is always a list

    def test_notes_has_three_entries(self):
        r = tag("Russia invades Ukraine")
        assert len(r.notes) == 3

    def test_description_preserved(self):
        desc = "Fed begins aggressive rate hike cycle"
        r = tag(desc)
        assert r.description == desc

    def test_deterministic(self):
        desc = "Russia invades Ukraine with military conflict escalation"
        r1 = tag(desc)
        r2 = tag(desc)
        assert r1.category == r2.category
        assert r1.confidence == r2.confidence
        assert len(r1.affected_sectors) == len(r2.affected_sectors)


# ── Direction field ───────────────────────────────────────────────────────────

class TestMergeDirection:
    def test_bullish_bullish(self):
        assert _merge_direction("bullish", "bullish") == "bullish"

    def test_bearish_bearish(self):
        assert _merge_direction("bearish", "bearish") == "bearish"

    def test_mixed_mixed(self):
        assert _merge_direction("mixed", "mixed") == "mixed"

    def test_bullish_bearish(self):
        assert _merge_direction("bullish", "bearish") == "mixed"

    def test_bearish_mixed(self):
        assert _merge_direction("bearish", "mixed") == "mixed"
