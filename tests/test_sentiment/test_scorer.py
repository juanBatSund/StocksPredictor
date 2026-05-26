import pytest
from datetime import date

from src.sentiment.scorer import (
    HeadlineScore,
    SentimentResult,
    _ols_slope,
    _tokenize,
    score,
    score_headline,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _dated(text: str, d: date = date(2024, 1, 1)) -> tuple[date, str]:
    return (d, text)


# ── Tokeniser ─────────────────────────────────────────────────────────────────

class TestTokenize:
    def test_lowercases(self):
        assert _tokenize("Apple Beats ESTIMATES") == ["apple", "beats", "estimates"]

    def test_strips_punctuation(self):
        assert _tokenize("Q4'24 earnings: +8%") == ["q4", "24", "earnings", "8"]

    def test_hyphen_stripped(self):
        # "52-week" becomes two tokens — phrase list stores "52 week high"
        assert "52" in _tokenize("52-week high")
        assert "week" in _tokenize("52-week high")

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_whitespace_only(self):
        assert _tokenize("   ") == []


# ── Single-headline scoring ────────────────────────────────────────────────────

class TestScoreHeadlineBasic:
    def test_empty_headline_is_neutral(self):
        r = score_headline("")
        assert r.score == 0.0
        assert r.confidence == 0.0
        assert r.matched == []

    def test_no_lexicon_match_is_neutral(self):
        # Generic words, none in lexicon
        r = score_headline("The company announced its quarterly report today")
        assert r.score == 0.0
        assert r.confidence == 0.0

    def test_deterministic_same_input_same_output(self):
        h = "Company beats estimates and raises guidance for next quarter"
        r1 = score_headline(h)
        r2 = score_headline(h)
        assert r1.score == r2.score
        assert r1.confidence == r2.confidence
        assert len(r1.matched) == len(r2.matched)

    def test_note_is_nonempty_string(self):
        r = score_headline("Company reports strong profit")
        assert isinstance(r.note, str)
        assert len(r.note) > 0


class TestScoreHeadlinePhrases:
    def test_beats_estimates_is_bullish(self):
        r = score_headline("AAPL beats estimates for Q4")
        assert r.score > 0
        assert any(m.term == "beats estimates" for m in r.matched)

    def test_misses_estimates_is_bearish(self):
        r = score_headline("TSLA misses estimates on revenue")
        assert r.score < 0
        assert any(m.term == "misses estimates" for m in r.matched)

    def test_bankruptcy_filing_clamps_to_minus_one(self):
        r = score_headline("Company submits bankruptcy filing in Delaware court")
        assert r.score == pytest.approx(-1.0)

    def test_profit_warning_is_bearish(self):
        r = score_headline("Management issues a profit warning ahead of results")
        assert r.score < 0

    def test_raised_guidance_is_bullish(self):
        r = score_headline("Firm raised guidance for full year outlook")
        assert r.score > 0

    def test_record_losses_is_bearish(self):
        # Verifies the "record losses" phrase overrides the bullish "record" word.
        # Without the phrase, "record" (+0.40) and "losses" (-0.40) would cancel to 0.
        r = score_headline("Company reports record losses this quarter")
        assert r.score < 0
        assert any(m.term == "record losses" for m in r.matched)

    def test_phrase_prevents_double_counting(self):
        # "beats" consumed by phrase "beats estimates" — should not also match word "beats"
        r = score_headline("Company beats estimates this quarter")
        phrase_count = sum(1 for m in r.matched if m.term == "beats estimates")
        word_count = sum(1 for m in r.matched if m.term == "beats")
        assert phrase_count == 1
        assert word_count == 0


class TestScoreHeadlineWords:
    def test_single_bullish_word(self):
        r = score_headline("Company reports strong profit this quarter")
        assert r.score > 0

    def test_single_bearish_word(self):
        r = score_headline("Firm posts significant losses for the period")
        assert r.score < 0

    def test_score_clamped_at_plus_one(self):
        r = score_headline(
            "beats estimates record profit growth upgraded outperform approved bullish"
        )
        assert r.score <= 1.0

    def test_score_clamped_at_minus_one(self):
        r = score_headline(
            "bankruptcy fraud scandal losses layoffs crash plunges writedown default"
        )
        assert r.score >= -1.0

    def test_matched_terms_expose_base_and_applied_weight(self):
        r = score_headline("Company posts a loss this quarter")
        assert len(r.matched) > 0
        for m in r.matched:
            assert isinstance(m.base_weight, float)
            assert isinstance(m.applied_weight, float)


class TestNegation:
    def test_not_profitable_is_bearish(self):
        r_plain = score_headline("Company is profitable")
        r_neg = score_headline("Company is not profitable")
        assert r_plain.score > 0
        assert r_neg.score <= 0

    def test_negated_term_has_flag_set(self):
        r = score_headline("Company shows no growth this quarter")
        growth_match = next((m for m in r.matched if m.term == "growth"), None)
        assert growth_match is not None
        assert growth_match.negated is True
        assert growth_match.applied_weight < 0

    def test_negated_base_weight_sign_reversed(self):
        r = score_headline("No losses reported this period")
        loss_match = next((m for m in r.matched if m.term in ("loss", "losses")), None)
        if loss_match is not None:
            # "no" negates "losses" → applied_weight should be positive
            assert loss_match.negated is True
            assert loss_match.applied_weight > 0


class TestIntensity:
    def test_significantly_amplifies_bearish(self):
        r_plain = score_headline("Revenue declined this quarter")
        r_intense = score_headline("Revenue significantly declined this quarter")
        assert r_intense.score < r_plain.score

    def test_slightly_dampens_score(self):
        r_plain = score_headline("Company shows profit")
        r_mild = score_headline("Company shows slightly profit")
        # "slightly" is a 0.5× multiplier → absolute score should be lower
        assert abs(r_mild.score) <= abs(r_plain.score)

    def test_intensity_stored_on_matched_term(self):
        r = score_headline("Revenue dramatically declined")
        decline_match = next((m for m in r.matched if m.term in ("decline", "declined", "declines")), None)
        if decline_match is not None:
            assert decline_match.intensity == pytest.approx(1.50)


class TestConfidence:
    def test_confidence_zero_with_no_matches(self):
        r = score_headline("The results were announced on Tuesday afternoon")
        assert r.confidence == pytest.approx(0.0)

    def test_confidence_positive_with_matches(self):
        r = score_headline("Company beats estimates and raises guidance")
        assert r.confidence > 0

    def test_confidence_bounded_zero_to_one(self):
        r = score_headline(
            "beats estimates record earnings profit growth upgraded outperform approved"
        )
        assert 0.0 <= r.confidence <= 1.0

    def test_low_coverage_flag_when_no_matches(self):
        r = score_headline("The quarterly announcement was made on Tuesday")
        assert r.low_coverage is True

    def test_no_low_coverage_flag_with_strong_headline(self):
        r = score_headline("Company beats estimates and raises guidance and reports record earnings")
        assert r.low_coverage is False


# ── Aggregate scoring ──────────────────────────────────────────────────────────

class TestAggregation:
    def test_empty_headlines_returns_neutral(self):
        r = score("AAPL", [])
        assert r.score == 0.0
        assert r.status == "neutral"
        assert r.confidence == 0.0

    def test_aggregate_is_mean_of_headline_scores(self):
        headlines = [
            _dated("Company beats estimates", date(2024, 1, 1)),
            _dated("Company misses estimates", date(2024, 1, 2)),
        ]
        r = score("TEST", headlines)
        expected = (r.headline_scores[0].score + r.headline_scores[1].score) / 2
        assert r.score == pytest.approx(expected, abs=1e-4)

    def test_all_bullish_gives_positive_status(self):
        headlines = [
            _dated("Company beats estimates", date(2024, 1, 1)),
            _dated("Record earnings and raised guidance", date(2024, 1, 2)),
        ]
        r = score("TEST", headlines)
        assert r.status == "positive"

    def test_all_bearish_gives_negative_status(self):
        headlines = [
            _dated("Company misses estimates", date(2024, 1, 1)),
            _dated("Profit warning issued with lowered guidance", date(2024, 1, 2)),
        ]
        r = score("TEST", headlines)
        assert r.status == "negative"

    def test_neutral_when_no_lexicon_matches(self):
        r = score("TEST", [_dated("The quarterly announcement was made on Tuesday")])
        assert r.status == "neutral"

    def test_headline_count_matches_input(self):
        headlines = [
            _dated("Company beats estimates", date(2024, 1, 1)),
            _dated("Record profit reported", date(2024, 1, 2)),
            _dated("Strong results this quarter", date(2024, 1, 3)),
        ]
        r = score("AAPL", headlines)
        assert len(r.headline_scores) == 3

    def test_ticker_preserved(self):
        r = score("MSFT", [_dated("Company beats estimates")])
        assert r.ticker == "MSFT"

    def test_notes_has_three_entries(self):
        r = score("AAPL", [_dated("Company beats estimates")])
        assert len(r.notes) == 3

    def test_daily_scores_exposed(self):
        headlines = [
            _dated("Company beats estimates", date(2024, 1, 1)),
            _dated("Profit warning", date(2024, 1, 2)),
        ]
        r = score("TEST", headlines)
        assert len(r.daily_scores) == 2
        assert all(isinstance(ds[0], str) for ds in r.daily_scores)
        assert all(isinstance(ds[1], float) for ds in r.daily_scores)

    def test_multiple_headlines_same_day_collapsed_to_one_daily_point(self):
        headlines = [
            _dated("Company beats estimates", date(2024, 1, 1)),
            _dated("Record earnings this quarter", date(2024, 1, 1)),
            _dated("Profit warning issued", date(2024, 1, 2)),
        ]
        r = score("TEST", headlines)
        assert len(r.daily_scores) == 2  # two distinct dates


# ── Trend computation ──────────────────────────────────────────────────────────

class TestTrend:
    def test_single_date_trend_is_zero(self):
        r = score("TEST", [_dated("Company beats estimates")])
        assert r.trend == 0.0

    def test_empty_headlines_trend_is_zero(self):
        r = score("TEST", [])
        assert r.trend == 0.0

    def test_improving_trend_is_positive(self):
        headlines = [
            _dated("Company misses estimates and profit warning", date(2024, 1, 1)),
            _dated("Company beats estimates and raises guidance", date(2024, 1, 5)),
        ]
        r = score("TEST", headlines)
        assert r.trend > 0

    def test_worsening_trend_is_negative(self):
        headlines = [
            _dated("Company beats estimates and raises guidance", date(2024, 1, 1)),
            _dated("Company misses estimates and profit warning", date(2024, 1, 5)),
        ]
        r = score("TEST", headlines)
        assert r.trend < 0

    def test_flat_trend_near_zero(self):
        headlines = [
            _dated("Company beats estimates", date(2024, 1, 1)),
            _dated("Company beats estimates", date(2024, 1, 2)),
        ]
        r = score("TEST", headlines)
        assert r.trend == pytest.approx(0.0, abs=1e-4)

    def test_three_dates_trend_computed(self):
        headlines = [
            _dated("Company misses estimates", date(2024, 1, 1)),
            _dated("Company beats estimates", date(2024, 1, 2)),
            _dated("Record earnings raised guidance", date(2024, 1, 3)),
        ]
        r = score("TEST", headlines)
        assert r.trend > 0  # improving


# ── OLS slope ─────────────────────────────────────────────────────────────────

class TestOLSSlope:
    def test_perfect_positive_slope(self):
        xs = [0.0, 1.0, 2.0]
        ys = [0.0, 1.0, 2.0]
        assert _ols_slope(xs, ys) == pytest.approx(1.0)

    def test_perfect_negative_slope(self):
        xs = [0.0, 1.0, 2.0]
        ys = [2.0, 1.0, 0.0]
        assert _ols_slope(xs, ys) == pytest.approx(-1.0)

    def test_flat_returns_zero(self):
        xs = [0.0, 1.0, 2.0]
        ys = [0.5, 0.5, 0.5]
        assert _ols_slope(xs, ys) == pytest.approx(0.0)

    def test_constant_x_returns_zero(self):
        # denom = 0 when all x values are the same
        xs = [1.0, 1.0, 1.0]
        ys = [0.1, 0.5, 0.9]
        assert _ols_slope(xs, ys) == 0.0
