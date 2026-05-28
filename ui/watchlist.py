"""
Persistent watchlist backed by a JSON file.

The file is stored alongside this module so it survives server restarts.
Thread safety is not a concern for single-process development use.
"""

import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "watchlist.json")


def load() -> list[str]:
    """Return the current watchlist (uppercase tickers, insertion order)."""
    if not os.path.exists(_PATH):
        return []
    try:
        with open(_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def save(tickers: list[str]) -> None:
    with open(_PATH, "w") as f:
        json.dump(tickers, f, indent=2)


def add(ticker: str) -> None:
    ticker = ticker.upper().strip()
    tickers = load()
    if ticker not in tickers:
        tickers.append(ticker)
        save(tickers)


def remove(ticker: str) -> None:
    ticker = ticker.upper().strip()
    tickers = [t for t in load() if t != ticker]
    save(tickers)


def contains(ticker: str) -> bool:
    return ticker.upper().strip() in load()
