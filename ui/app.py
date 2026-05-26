"""
Flask UI server for the Investment Decision System.

Run from project root:
    python -m ui.app          (development)
    flask --app ui.app run    (alternative)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, abort, jsonify, request
from ui.mock_data import (
    get_all_stocks,
    get_stock,
    get_benchmark,
    get_replay_data,
    MODEL_VERSION,
    ANALYSIS_DATE,
)

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
            {"url": "/benchmark",  "label": "Benchmark"},
            {"url": "/replay",     "label": "Replay"},
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
                           avoid_count=avoid_count)


@app.route("/stock/<ticker>")
def stock_detail(ticker: str):
    stock = get_stock(ticker.upper())
    if stock is None:
        abort(404)
    gates_failed  = [g for g in stock["gates"] if g.passed is False]
    gates_unknown = [g for g in stock["gates"] if g.passed is None]
    gates_passed  = [g for g in stock["gates"] if g.passed is True]
    return render_template("stock.html",
                           stock=stock,
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


if __name__ == "__main__":
    app.run(debug=True, port=5050)
