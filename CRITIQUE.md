# UI Critique — Four Perspectives

This document records the critique of the inspectable UI from four distinct viewpoints,
and documents the specific improvements applied in response to each.

---

## 1. Quant Researcher

### Critique

> "I need to verify the math, not trust a summary."

**Issues identified:**
- Score weights (40/25/20/15) were not visible on the dashboard — I had to hunt for them.
- Confidence breakdown weights (30/25/30/15) were in the code but absent from the UI.
- The gate thresholds (`SCORE_BUY = 75`, `_MACRO_DOWNGRADE_THRESHOLD = 0.60`) were not shown
  alongside the observed values in the gates table.
- Reasoning traces need to be copyable for offline audit.
- Model version must be visible on every page — weight or threshold changes are silent otherwise.
- `SCORE_WATCH_MIN = 60` was implicit in the "WATCH" zone description; it should be explicit.
- Confidence formula shows four components but doesn't state the individual weights in the UI.
- No way to see the raw input values (ROE, P/E, etc.) — only scores are shown.

**Improvements applied:**
- Footer on every page shows `BUY > 75 | WATCH 60–75 | AVOID < 60` and all weights explicitly.
- Model version + analysis date in site header on every page.
- Confidence breakdown table shows: component | weight | value | contribution | rationale.
- Gate table shows both `observed` and `required` side-by-side with threshold values.
- Macro downgrade threshold (0.60) is shown inline in the macro section.
- Missing field penalty (`−0.07 per field`) is stated in the confidence breakdown table.
- "Copy trace to clipboard" button on reasoning trace.

---

## 2. Retail Investor

### Critique

> "I don't know what a 'gate' is. What does this mean for my money?"

**Issues identified:**
- The word "gate" is jargon. A non-technical user cannot intuit what "Gate 2: FAIL" means.
- The reasoning trace is 8 lines of technical notation — incomprehensible without context.
- Score 74.1/100 — is that good or bad? There's no reference frame.
- "Sentiment = negative but improving" — why is negative sentiment a *buy signal*? That's counterintuitive.
- "Confidence 0.61" — does that mean 61% chance of profit? (No, but that's the obvious misreading.)
- The dashboard's mini-breakdown (`Q 82 G 76 D 45 V 71`) is cryptic.

**Improvements applied:**
- **Plain-English Summary** section added to every stock detail page.
  - States in plain prose whether the stock passed/failed and why.
  - Explains the investment thesis in one paragraph without jargon.
- "Confidence ≠ probability of return" shown on every confidence display.
- Persistent disclaimer banner on every page (visible, not buried in footer).
- Legend cards on dashboard explain the BUY/WATCH/AVOID thresholds in bullet points.
- Mini-breakdown column headers use full words in tooltips (hover over `Q` shows "Quality ×40%").
- Contrarian philosophy explained in the Sentiment section: "negative but improving = market
  pessimism receding" is explicitly called out as a heuristic, not a law.
- "What Would Change This Decision?" section on stock detail tells the user concretely
  what conditions would flip the outcome.

---

## 3. Risk Manager

### Critique

> "The most important information is buried at the bottom."

**Issues identified:**
- Uncertainty flags appear below the score and gate sections — after the "good news."
  A risk manager needs to see failure modes *first*, before acting on the BUY signal.
- Confidence 0.73 looks authoritative. There is no prominent warning that it is not a probability.
- Missing fields (2 of 8) are shown as a small badge. They should be a red warning — missing data
  is a material risk to any score.
- "BUY downgraded to WATCH by macro" — this is buried in the reasoning trace and factor list.
  The headline should be visible without expanding anything.
- AVOID stocks may still have high dividend scores. The user shouldn't conclude the stock is
  "partially good" — the overall AVOID decision needs to dominate visually.
- Benchmark comparison lacks a risk-adjusted metric (no Sharpe ratio). The caveat must be explicit.
- No survivorship bias warning on the benchmark page.

**Improvements applied:**
- **Uncertainty flags moved to top of stock detail page** — appears immediately after the hero,
  before the score breakdown, gates, or any positive signals.
- "Read before acting" subtitle added to the uncertainty flags section header.
- Confidence disclaimer displayed in two places: hero area + confidence breakdown section.
- Missing fields shown with a prominent red badge in the hero (`⚠ 2 missing fields: pe_5y_avg, …`),
  not just a count in the table.
- On NVDA (macro downgrade), a banner in the Plain-English Summary explicitly states:
  "This stock passed all three gates. Decision downgraded from BUY by macro headwind."
- Benchmark limitations banner is always expanded (not collapsed) — risk managers must see caveats.
- Benchmark page includes survivorship bias as a known limitation.
- AVOID decision badge is visually dominant; sub-scores require deliberate expansion.

---

## 4. UX Designer

### Critique

> "The information hierarchy is inverted and the interaction model is inconsistent."

**Issues identified:**
- The densest technical content (reasoning trace, confidence breakdown) loads expanded,
  overwhelming first-time users. Most content should start collapsed.
- Red/green color coding for pass/fail is inaccessible for ~8% of users with red-green
  color blindness (deuteranopia/protanopia).
- Gate table: FAILed gates should appear first (most actionable), then UNKNOWNs, then PASSes.
  The original linear order hid failures at the end.
- Decision color coding (red=AVOID) clashes with "red = danger" on uncertainty flags — users
  might associate WATCH with a warning rather than a neutral hold.
- The score bar uses color alone to convey decision — needs a shape/text signal too.
- Replay page: no keyboard navigation; the slider alone is not discoverable.
- Benchmark CAGR bars have no baseline reference line — users can't tell what "good" looks like.

**Improvements applied:**
- **Color palette redesigned for colorblind safety:**
  - BUY: `#0077BB` (blue, distinct from red-green spectrum)
  - WATCH: `#EE7733` (orange, distinct from both blue and red)
  - AVOID: `#BB2200` (red-orange, not pure green)
  - Colorblind-safe palette follows the Bang Wong / Okabe-Ito standards.
- **Shape + text + color for all decision indicators:**
  - BUY = `▲` (triangle up) + text + blue
  - WATCH = `■` (square) + text + orange
  - AVOID = `▼` (triangle down) + text + red-orange
- **Gates reordered:** FAIL → UNKNOWN → PASS in the display table.
  Auto-expand gate panel when failures exist.
- **Progressive disclosure:** most panels start collapsed; score breakdown auto-expands
  because it's the most immediately useful context.
- **Keyboard shortcuts on replay:** ← / → arrow keys step through snapshots.
- CAGR bar group includes a `cagr-scale-note` ("scaled to 20% = 100%") so bars have
  an explicit reference frame.
- `toolbar-hint` on dashboard ("Click any row to inspect full reasoning") makes the
  interaction model explicit.

---

## Summary Matrix

| Issue                          | Perspective | Applied Fix |
|-------------------------------|-------------|-------------|
| Weights/thresholds not visible | Quant       | Footer, confidence table |
| Model version not shown        | Quant       | Site header, every page |
| Confidence misread as probability | Risk / Retail | Disclaimer in 3 places |
| Uncertainty flags buried       | Risk        | Moved to top of stock detail |
| Missing fields not prominent   | Risk        | Red badge in hero |
| Jargon in reasoning trace      | Retail      | Plain-English Summary section |
| Gate order hides failures      | UX          | FAIL → UNKNOWN → PASS ordering |
| Color-only decision signals    | UX          | Shape + text + color system |
| No keyboard nav on replay      | UX          | ← / → arrow key support |
| Survivorship bias unmentioned  | Risk        | Benchmark limitations |
| Macro downgrade not prominent  | Risk / Retail | Summary section explains explicitly |
| "What changes this decision?"  | Retail      | Dedicated section on stock detail |
