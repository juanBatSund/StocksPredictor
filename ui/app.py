"""
Flask UI server for the Investment Decision System.

Run from project root:
    python -m ui.app          (development)
    flask --app ui.app run    (alternative)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, abort, jsonify, request, redirect, url_for
from ui.mock_data import (
    get_all_stocks,
    get_stock,
    get_benchmark,
    get_replay_data,
    MODEL_VERSION,
    ANALYSIS_DATE,
)
import ui.watchlist as wl
import ui.screener as screener
import ui.ai_settings as ai_cfg
from config.tickers import MARKET_LABELS, MARKET_TICKERS

app = Flask(__name__,
            template_folder="templates",
            static_folder="static")


# ── Context injected into every template ──────────────────────────────────────

@app.context_processor
def inject_globals():
    return {
        "model_version":   MODEL_VERSION,
        "analysis_date":   ANALYSIS_DATE,
        "nav_pages": [
            {"url": "/",           "label": "Dashboard"},
            {"url": "/watchlist",  "label": "Watchlist"},
            {"url": "/screener",   "label": "Screener"},
            {"url": "/benchmark",  "label": "Benchmark"},
            {"url": "/replay",     "label": "Replay"},
            {"url": "/settings",   "label": "AI Settings"},
        ],
    }


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    stocks = get_all_stocks()
    all_flags = []
    for s in stocks:
        for flag in s["uncertainty_flags"]:
            all_flags.append({"ticker": s["ticker"], "flag": flag})
    buy_count   = sum(1 for s in stocks if s["decision"] == "BUY")
    watch_count = sum(1 for s in stocks if s["decision"] == "WATCH")
    avoid_count = sum(1 for s in stocks if s["decision"] == "AVOID")
    return render_template("dashboard.html",
                           stocks=stocks,
                           all_flags=all_flags,
                           buy_count=buy_count,
                           watch_count=watch_count,
                           avoid_count=avoid_count,
                           wl_tickers=wl.load())


@app.route("/stock/<ticker>")
def stock_detail(ticker: str):
    ticker = ticker.upper()
    # ?market= lets the screener (and watchlist) pass the correct exchange context.
    # Without it, non-US tickers would be fetched without their exchange suffix
    # (e.g. ABB fetched as NYSE ADR instead of ABB.ST on Stockholm).
    market_code = request.args.get("market", "US").upper()
    from config.markets import MARKETS
    if market_code not in MARKETS:
        market_code = "US"

    stock = get_stock(ticker)

    if stock is None:
        # Fall back to live analysis for tickers not in mock data
        try:
            from ui.pipeline import analyze
            stock = analyze(ticker, market_code)
        except ValueError:
            abort(404)
        except Exception:
            abort(503)

    is_watched = wl.contains(ticker)
    gates_failed  = [g for g in stock["gates"] if g.passed is False]
    gates_unknown = [g for g in stock["gates"] if g.passed is None]
    gates_passed  = [g for g in stock["gates"] if g.passed is True]
    return render_template("stock.html",
                           stock=stock,
                           is_watched=is_watched,
                           gates_failed=gates_failed,
                           gates_unknown=gates_unknown,
                           gates_passed=gates_passed)


@app.route("/benchmark")
def benchmark():
    data = get_benchmark()
    return render_template("benchmark.html", **data)


@app.route("/replay")
@app.route("/replay/<ticker>")
def replay(ticker: str = "MSFT"):
    data = get_replay_data(ticker.upper())
    return render_template("replay.html", **data)


# ── Search ────────────────────────────────────────────────────────────────────

@app.route("/search")
def search():
    q = request.args.get("q", "").strip().upper()
    if not q:
        return redirect(url_for("dashboard"))
    return redirect(url_for("stock_detail", ticker=q))


# ── Watchlist ─────────────────────────────────────────────────────────────────

@app.route("/watchlist")
def watchlist():
    tickers = wl.load()
    # Build a lightweight item for each watched ticker
    items = []
    for t in tickers:
        stock = get_stock(t)  # use mock data if available
        if stock:
            items.append(stock)
        else:
            # Placeholder so the page still renders before the user clicks through
            items.append({
                "ticker": t,
                "name": t,
                "decision": None,
                "score": None,
                "confidence": None,
                "sector": "",
                "valuation_status": "",
                "quality_score": None,
                "growth_score": None,
                "dividend_score": None,
                "valuation_score": None,
            })
    return render_template("watchlist.html", items=items, watchlist_count=len(tickers))


@app.route("/watchlist/add", methods=["POST"])
def watchlist_add():
    ticker = request.form.get("ticker", "").strip().upper()
    if ticker:
        wl.add(ticker)
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/watchlist/remove", methods=["POST"])
def watchlist_remove():
    ticker = request.form.get("ticker", "").strip().upper()
    if ticker:
        wl.remove(ticker)
    return redirect(request.referrer or url_for("dashboard"))


# ── Screener ──────────────────────────────────────────────────────────────────

@app.route("/screener")
def screener_page():
    markets = MARKET_LABELS
    active_tab = request.args.get("tab", next(iter(markets))).upper()
    if active_tab not in markets:
        active_tab = next(iter(markets))
    initial_results = {code: screener.load_results(code) for code in markets}
    initial_states  = {code: screener.get_state(code).get("status", "idle") for code in markets}
    initial_summary = {code: screener.get_state(code) for code in markets}
    tickers_count   = {code: len(MARKET_TICKERS.get(code, [])) for code in markets}
    return render_template(
        "screener.html",
        markets=markets,
        active_tab=active_tab,
        initial_results=initial_results,
        initial_states=initial_states,
        initial_summary=initial_summary,
        tickers_count=tickers_count,
    )


@app.route("/screener/run/<market_code>", methods=["POST"])
def screener_run(market_code: str):
    market_code = market_code.upper()
    if market_code in MARKET_LABELS:
        screener.run_market(market_code)
    return redirect(url_for("screener_page", tab=market_code))


@app.route("/screener/status/<market_code>")
def screener_status(market_code: str):
    return jsonify(screener.get_state(market_code.upper()))


# ── JSON API (for JS-driven interactions) ─────────────────────────────────────

@app.route("/api/stocks")
def api_stocks():
    return jsonify(get_all_stocks())


@app.route("/api/stock/<ticker>")
def api_stock(ticker: str):
    stock = get_stock(ticker.upper())
    if stock is None:
        abort(404)
    return jsonify(stock)


@app.route("/api/replay/<ticker>")
def api_replay(ticker: str):
    return jsonify(get_replay_data(ticker.upper()))


# ── AI Settings ───────────────────────────────────────────────────────────────

@app.route("/settings", methods=["GET"])
def settings_page():
    cfg = ai_cfg.load()
    models = []
    if cfg.get("provider") == "ollama":
        models = ai_cfg.list_ollama_models(cfg.get("ollama_base_url", ""))
    return render_template(
        "ai_settings.html",
        cfg=cfg,
        providers=ai_cfg.PROVIDERS,
        models=models,
    )


@app.route("/settings", methods=["POST"])
def settings_save():
    provider = request.form.get("provider", "none")
    updates = {
        "provider": provider,
        "ollama_model": request.form.get("ollama_model", "").strip(),
        "ollama_base_url": request.form.get("ollama_base_url", "http://127.0.0.1:11434").strip(),
        "ollama_timeout": int(request.form.get("ollama_timeout", 120) or 120),
    }
    ai_cfg.save(updates)
    # Invalidate the analysis cache so next stock lookup uses the new model
    from ui.pipeline import _CACHE
    _CACHE.clear()
    return redirect(url_for("settings_page"))


@app.route("/api/ollama/models")
def api_ollama_models():
    base_url = request.args.get("base_url", "").strip()
    models = ai_cfg.list_ollama_models(base_url or None)
    return jsonify({"models": models, "count": len(models)})


@app.route("/api/ai/test")
def api_ai_test():
    """Probe the configured AI service with a minimal request."""
    from datetime import datetime, timezone
    from src.ai.models import NewsAnalysisRequest, NewsArticle
    from src.ai.service import AnalysisUnavailable, analyze_if_available

    service = ai_cfg.get_service()
    if service is None:
        return jsonify({"status": "disabled", "message": "No AI provider configured."})

    cfg = ai_cfg.load()
    now = datetime.now(timezone.utc)
    probe_article = NewsArticle(
        article_id="probe-1",
        ticker="TEST",
        headline="Company reports steady quarterly results in line with expectations.",
        publisher="Test Wire",
        url=None,
        published_at=now,
        available_at=now,
    )
    probe_request = NewsAnalysisRequest(
        ticker="TEST",
        decision_at=now,
        articles=[probe_article],
    )
    try:
        result = analyze_if_available(service, probe_request)
        if isinstance(result, AnalysisUnavailable):
            return jsonify({"status": "error", "message": result.reason})
        return jsonify({
            "status": "ok",
            "provider": result.provider,
            "model": result.model,
            "direction": result.analysis.overall_direction,
            "confidence": result.analysis.analysis_confidence,
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
